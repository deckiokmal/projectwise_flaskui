from __future__ import annotations
import asyncio
import json
import uuid
import time
from contextlib import AsyncExitStack, suppress
from typing import Any, Dict, List, Optional

import sqlalchemy as sa
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from anyio import ClosedResourceError
from dotenv import load_dotenv

from utils.logger import get_logger
from utils.helper import safe_args, truncate_by_tokens, infer_kak_md, best_match
from config.mcp_settings import MCPSettings
from openai import AsyncOpenAI
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from .mem0ai import Mem0Manager
from .routing_workflow_intent import classify_intent
from .pipeline_product_proposal import run as run_docgen_pipeline

TOOL_TIMEOUT_SEC = 30
PIPE_TIMEOUT_SEC = 180

load_dotenv()
settings = MCPSettings()
logger = get_logger("MCPClient")


# SQLAlchemy setup for short-term memory
Base = declarative_base()


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = sa.Column(sa.Integer, primary_key=True)
    user_id = sa.Column(sa.String(64), unique=True, nullable=False)


class Message(Base):
    __tablename__ = "messages"
    id = sa.Column(sa.Integer, primary_key=True)
    user_id = sa.Column(
        sa.String(64), sa.ForeignKey("chat_sessions.user_id"), nullable=False
    )
    role = sa.Column(sa.String(16), nullable=False)
    content = sa.Column(sa.Text, nullable=False)
    timestamp = sa.Column(sa.DateTime, server_default=sa.func.now())


class MCPClient:
    def __init__(
        self,
        model: str = settings.llm_model,
        memory_db: str = "sqlite:///chat_memory.sqlite",
    ):
        # LLM and MCP settings
        self.model = model
        self.llm = AsyncOpenAI()
        self.memory_mgr = Mem0Manager()
        self.settings = settings
        self.session: Optional[ClientSession] = None
        self._connected = False

        # Short-term memory DB init
        engine = sa.create_engine(memory_db, connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        self.DBSession = sessionmaker(bind=engine)

        # Async tasks and caches
        self._exit_stack: Optional[AsyncExitStack] = None
        self._keep_alive_task: Optional[asyncio.Task] = None
        self._tools_update_task: Optional[asyncio.Task] = None
        self.tool_cache: List[Dict[str, Any]] = []
        self._auto_reconnect = True
        self._reconnect_lock = asyncio.Lock()

        logger.info("MCPClient initialized with short-term memory support")

    def _save_short_term(self, user_id: str, role: str, content: str) -> None:
        db = self.DBSession()
        # Ensure session exists
        if not db.query(ChatSession).filter_by(user_id=user_id).first():
            db.add(ChatSession(user_id=user_id))
            db.commit()
        db.add(Message(user_id=user_id, role=role, content=content))
        db.commit()
        db.close()

    def _get_short_term(self, user_id: str, limit: int = 20) -> List[Dict[str, str]]:
        db = self.DBSession()
        q = (
            db.query(Message)
            .filter_by(user_id=user_id)
            .order_by(Message.id.desc())
            .limit(limit)
        )
        msgs = q.all()[::-1]  # reverse to chronological
        db.close()
        result = [{"role": m.role, "content": m.content} for m in msgs]
        return result  # type: ignore

    def is_connected(self) -> bool:
        return self.session is not None and self._connected

    async def ensure_session_alive(self) -> None:
        if not self.is_connected() and self._auto_reconnect:
            # hanya satu coroutine boleh reconnect pada satu waktu
            async with self._reconnect_lock:
                if not self.is_connected():
                    logger.warning("MCP session lost, reconnecting now...")
                    await self.connect()

    async def keep_alive_loop(self, interval: int = 30) -> None:
        try:
            while True:
                await asyncio.sleep(interval)
                await self.call_tool("heartbeat", {})
        except asyncio.CancelledError:
            logger.info("keep_alive_loop cancelled")
        except BaseExceptionGroup as eg:
            filtered = []
            for exc in eg.exceptions:
                if isinstance(exc, GeneratorExit):
                    logger.debug(
                        "keep_alive_loop: GeneratorExit dari streamablehttp_client diabaikan."
                    )
                else:
                    filtered.append(exc)
            if filtered:
                raise BaseExceptionGroup("Errors in keep_alive_loop", filtered)
        except Exception as e:
            logger.warning(f"Heartbeat failed: {e}")
            asyncio.create_task(self.cleanup())
            asyncio.create_task(self.connect())

    async def _periodic_tools_update(self) -> None:
        """Fetch list_tools() tiap 60 detik dan simpan di cache."""
        while True:
            await asyncio.sleep(60)
            if not self.is_connected():
                continue
            try:
                tools_result = await self.session.list_tools()  # type: ignore
                self.tool_cache = [
                    {
                        "type": "function",
                        "function": {
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.inputSchema,
                        },
                    }
                    for t in tools_result.tools
                ]
                logger.debug("Tool cache updated")
            except Exception as e:
                logger.warning(f"Failed to update tool cache: {e}")

    async def connect(self, endpoint: Optional[str] = None) -> bool:
        url = endpoint or self.settings.mcp_server_url
        if self._connected:
            return True

        # 1) Buat stack baru
        self._exit_stack = AsyncExitStack()
        await self._exit_stack.__aenter__()

        try:
            # 2) Masuk HTTP transport
            http_ctx = streamablehttp_client(url)
            read_s, write_s, _ = await self._exit_stack.enter_async_context(http_ctx)

            # 3) Masuk MCP ClientSession
            session_ctx = ClientSession(read_s, write_s)
            self.session = await self._exit_stack.enter_async_context(session_ctx)

            # 4) Inisialisasi & heartbeat
            await self.session.initialize()
            self._connected = True
            self._keep_alive_task = asyncio.create_task(self.keep_alive_loop())
            if not self._tools_update_task:
                self._tools_update_task = asyncio.create_task(
                    self._periodic_tools_update()
                )

            # 5) Inisialisasi Mem0
            try:
                await self.memory_mgr.init()
            except Exception as e:
                logger.warning(f"Mem0 init failed: {e}")

            # 6) List tools
            self.tools = await self.get_tools()
            logger.info(
                f"Available tools: {[t['function']['name'] for t in self.tools]}"
            )

            return True

        except Exception:
            # kalau gagal, tutup stack
            await self._exit_stack.aclose()
            self._connected = False
            return False

    async def call_tool(self, name: str, args: Dict[str, Any]) -> str:
        # respect manual‐disconnect
        if not self._auto_reconnect and not self.is_connected():
            raise RuntimeError("Session manually disconnected")

        # pastikan sesi hidup, tunggu reconnect jika perlu
        await self.ensure_session_alive()

        # sekarang coba kirim
        try:
            result = await self.session.call_tool(name, args)  # type: ignore
            return result.content[0].text  # type: ignore

        except ClosedResourceError:
            # write‐stream closed, reconnect + retry sekali
            logger.warning(
                f"Write stream closed on tool '{name}', reconnecting and retrying..."
            )
            async with self._reconnect_lock:
                # bersihkan dulu state, new connect
                await self.cleanup()
                ok = await self.connect()
                if not ok:
                    raise RuntimeError("Reconnect failed before retrying call_tool()")

                # retry
                result = await self.session.call_tool(name, args)  # type: ignore
                return result.content[0].text  # type: ignore

        except Exception as e:
            logger.error(f"Tool call {name} failed: {e}", exc_info=True)
            # tandai disconnect agar next call trigger reconnect
            self._connected = False
            raise

    async def get_tools(self) -> List[Dict[str, Any]]:
        # Jika belum ada cache, fetch sekali
        if not self.tool_cache:
            try:
                result = await self.session.list_tools()  # type: ignore
                self.tool_cache = [
                    {
                        "type": "function",
                        "function": {
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.inputSchema,
                        },
                    }
                    for t in result.tools
                ]
            except Exception as e:
                logger.error(f"Initial get_tools() failed: {e}", exc_info=True)
        return self.tool_cache

    async def process_query(
        self,
        query: str,
        user_id: str = "default",
        max_turns: int = 20,
    ) -> str:
        trace = uuid.uuid4().hex[:8]
        start = time.perf_counter()
        logger.info(f"[{trace}] Processing query: {query}")

        # 1) Load recent short-term memory as context
        history = self._get_short_term(user_id, limit=10)
        # messages: List[Dict[str, str]] = [
        #     {"role": msg["role"], "content": msg["content"]} for msg in history
        # ]
        # Truncate tiap pesan maksimal 150 token
        messages = [
            {
                "role": m["role"],
                "content": truncate_by_tokens(m["content"], max_tokens=150),
            }
            for m in history
        ]

        # 2) Append user message
        messages.append({"role": "user", "content": query})
        self._save_short_term(user_id, "user", query)

        # 3) Classify intent
        intent = "other"
        for attempt in range(3):
            try:
                route = await classify_intent(self.llm, query, self.model)
                if route.confidence_score >= 0.7:
                    intent = route.intent
                logger.info(
                    f"[{trace}] Intent: {intent} (conf={route.confidence_score:.2f})"
                )
                break
            except Exception as e:
                logger.error(f"[{trace}] classify_intent error: {e}")
                await asyncio.sleep(2**attempt)

        # 4) Route to handler
        if intent == "generate_document":
            answer = await self._run_docgen(trace, query, user_id, max_turns)
        else:
            answer = await self._run_other(trace, messages, user_id, max_turns)

        # 5) Save assistant response
        self._save_short_term(user_id, "assistant", answer)

        duration = time.perf_counter() - start
        logger.info(f"[{trace}] Total latency: {duration:.2f}s")
        return answer

    async def cleanup(self):
        # cancel heartbeat
        if self._keep_alive_task:
            self._keep_alive_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._keep_alive_task

        # close exit stack
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except Exception as e:
                # Abaikan error “generator didn’t stop…” atau cancel‐scope mismatch
                logger.debug(f"Ignored error during exit_stack.aclose(): {e}")

        self._connected = False
        self.session = None
        self._exit_stack = None
        logger.info("MCPClient disconnected")

    async def _run_docgen(
        self, trace_id: str, query: str, user_id: str, max_turns: int
    ):
        slug = infer_kak_md(query)

        try:
            files_json = await self.call_tool("list_kak_files", {})
            all_files = json.loads(files_json)
        except Exception:
            all_files = []
        kak_md = best_match(all_files, slug) or slug  # type: ignore

        try:
            result = await asyncio.wait_for(
                run_docgen_pipeline(
                    client=self,
                    project_name=kak_md,  # type: ignore
                    user_query=query,
                    override_template=None,
                    max_turns=max_turns,
                ),
                timeout=PIPE_TIMEOUT_SEC,
            )
            reply = f"Proposal berhasil dibuat untuk proyek “{kak_md}”.\n\nLokasi file: {result}"
        except asyncio.TimeoutError:
            logger.error(f"[{trace_id}] run_docgen_pipeline TIMEOUT")
            reply = "Maaf, pembuatan proposal melebihi batas waktu."
        except Exception as e:
            logger.error(f"[{trace_id}] run_docgen_pipeline error: {e}")
            reply = f"Terjadi kesalahan saat generate proposal: {e}"

        await self.memory_mgr.add_conversation(
            [
                {"role": "user", "content": query},
                {"role": "assistant", "content": reply},
            ],
            user_id=user_id,
        )
        return reply

    async def _run_other(
        self,
        trace_id: str,
        messages: List[Dict[str, str]],
        user_id: str,
        max_turns: int,
    ) -> str:
        # Fetch relevant mem0ai if needed
        try:
            raw_mems = await self.memory_mgr.get_memories(
                messages[-1]["content"], limit=5
            )
            mem_block = (
                "\n".join(f"- {truncate_by_tokens(m)}" for m in raw_mems)
                or "[Tidak ada]"
            )
            system_mem = {
                "role": "system",
                "content": f"Memori historis relevan:\n{mem_block}\n\nGunakan memori di atas jika membantu.",
            }
            messages.insert(0, system_mem)
        except Exception as e:
            logger.error(f"[{trace_id}] mem0 search error: {e}")

        # Retrieve tools
        tools = await self.get_tools()
        final_answer: Optional[str] = None

        for turn in range(max_turns):
            logger.info(f"[{trace_id}] - Turn {turn + 1}/{max_turns}")
            response = await self.llm.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore
                tools=tools,  # type: ignore
                tool_choice="auto",
            )
            assistant_msg = response.choices[0].message
            messages.append(assistant_msg.model_dump())

            # No tool calls -> final answer
            if not assistant_msg.tool_calls:
                final_answer = assistant_msg.content or ""
                break

            # Execute tool calls
            async def exec_tool(tc):
                fname = tc.function.name
                args = json.loads(tc.function.arguments)
                logger.info(
                    f"[{trace_id}] · Executing tool {fname} args={safe_args(args)}"
                )
                try:
                    return await asyncio.wait_for(
                        self.call_tool(fname, args), timeout=TOOL_TIMEOUT_SEC
                    )
                except Exception as e:
                    logger.error(f"[{trace_id}] tool {fname} error: {e}")
                    return f"Error executing {fname}: {e}"

            results = await asyncio.gather(
                *[exec_tool(tc) for tc in assistant_msg.tool_calls]
            )
            for tc, out in zip(assistant_msg.tool_calls, results):
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.function.name,
                        "content": out,
                    }
                )

        if not final_answer:
            logger.warning(f"[{trace_id}] max turns reached without final answer.")
            final_answer = (
                "Maaf, saya belum bisa menyelesaikan permintaan dalam batas waktu."
            )

        return final_answer
