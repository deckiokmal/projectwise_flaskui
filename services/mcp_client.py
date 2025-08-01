from __future__ import annotations
import asyncio
from typing import Any, Dict, List, Optional
from contextlib import AsyncExitStack, suppress

import json
import uuid
import time
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


class MCPClient:
    def __init__(self, model: str = settings.llm_model):
        self.model = model
        self.llm = AsyncOpenAI()
        self.memory_mgr = Mem0Manager()
        self.settings = settings
        self.session: Optional[ClientSession] = None
        self._keep_alive_task: Optional[asyncio.Task] = None
        self._exit_stack: Optional[AsyncExitStack] = None
        self._connected = False
        self.tools: List[Dict[str, Any]] = []
        self._http_context = None
        self.tool_cache: List[Dict[str, Any]] = []
        self._tools_update_task: Optional[asyncio.Task] = None
        self._auto_reconnect: bool = True
        logger.info("MCPClient initialized with HTTP transport")

    def is_connected(self) -> bool:
        return self.session is not None and self._connected

    async def ensure_session_alive(self) -> None:
        if not self.is_connected():
            logger.warning("MCP session lost, reconnecting...")
            asyncio.create_task(self.connect())

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
        # 1. Jika manual‐disconnected, tolak panggilan
        if not self._auto_reconnect and not self.is_connected():
            raise RuntimeError("Session manually disconnected")

        # 2. Jika session mati, coba reconnect sekali, tunggu selesai
        if not self.is_connected():
            logger.warning("Session lost → reconnecting before call_tool()")
            await self.connect()

        # 3. Panggil tool
        try:
            result = await self.session.call_tool(name, args)  # type: ignore
            return result.content[0].text  # type: ignore
        except Exception as e:
            logger.error(f"Tool call {name} failed: {e}", exc_info=True)
            # tandai disconnect, inform front‐end via exception
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
        self, query: str, user_id: str = "default", max_turns: int = 20
    ) -> str:
        trace = uuid.uuid4().hex[:8]
        start = time.perf_counter()
        logger.info(f"[{trace}] Processing query: {query}")

        intent = "other"
        for i in range(3):
            try:
                route = await classify_intent(self.llm, query, self.model)
                if route.confidence_score >= 0.7:
                    intent = route.intent
                logger.info(
                    f"[{trace}] Intent: {intent} (conf={route.confidence_score:.2f})"
                )
                break
            except Exception as e:
                logger.error(f"[{trace}] classify_intent attempt {i + 1} failed: {e}")
                if i == 2:
                    logger.warning(f"[{trace}] Falling back to 'other'")
                await asyncio.sleep(2**i)

        try:
            if intent == "generate_document":
                return await self._run_docgen(trace, query, user_id, max_turns)
            else:
                return await self._run_other(trace, query, user_id, max_turns)
        finally:
            duration = time.perf_counter() - start
            logger.info(f"[{trace}] Total latency: {duration:.2f}s")

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

    async def _run_other(self, trace_id: str, query: str, user_id: str, max_turns: int):
        # ambil memori relevan
        try:
            memories = await self.memory_mgr.get_memories(query, limit=5)
        except Exception as e:
            logger.error(f"[{trace_id}] mem0 search error: {e}")
            memories = []

        mem_block = (
            "\n".join(f"- {truncate_by_tokens(m)}" for m in memories) or "[Tidak ada]"
        )
        system_mem = {
            "role": "system",
            "content": (
                "Memori historis relevan:\n"
                f"{mem_block}\n\n"
                "Gunakan memori di atas jika membantu."
            ),
        }
        messages = [
            system_mem,
            {
                "role": "system",
                "content": "Anda adalah “ProjectWise”, asisten virtual untuk tim Presales & PM.",
            },
            {"role": "user", "content": query},
        ]

        # Ambil tools atau gunakan cache
        tools = await self.get_tools()
        final_answer = None

        try:
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

                if not assistant_msg.tool_calls:  # ▶ Jawaban final
                    final_answer = assistant_msg.content or "Tidak ada jawaban."
                    break

                # ─ Jalankan setiap tool call (parallel → gather) ─
                async def _exec(tc):
                    fname = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments)
                        logger.info(
                            f"[{trace_id}]  · tool '{fname}' args={safe_args(args)}"
                        )
                        return await asyncio.wait_for(
                            self.call_tool(fname, args), timeout=TOOL_TIMEOUT_SEC
                        )
                    except asyncio.TimeoutError:
                        logger.error(f"[{trace_id}] tool {fname} TIMEOUT")
                        return f"TIMEOUT executing {fname}"
                    except Exception as e:
                        logger.error(f"[{trace_id}] tool {fname} error: {e}")
                        return f"Error executing {fname}: {e}"

                results = await asyncio.gather(
                    *[_exec(tc) for tc in assistant_msg.tool_calls]
                )
                # masukkan hasil ke messages
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
                logger.warning(f"[{trace_id}] Batas {max_turns} turn tercapai.")
                final_answer = (
                    "Maaf, saya belum bisa menyelesaikan permintaan dalam batas waktu."
                )

        finally:
            answer_to_save = final_answer or "Maaf, terjadi kegagalan internal."
            # commit memori apa pun hasilnya
            await self.memory_mgr.add_conversation(
                [
                    {"role": "user", "content": query},
                    {"role": "assistant", "content": answer_to_save},
                ],
                user_id=user_id,
            )

        return answer_to_save
