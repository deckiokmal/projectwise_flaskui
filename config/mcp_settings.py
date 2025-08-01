import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


load_dotenv()


# .env absolute path
env_path = Path(__file__).resolve().parent.parent / ".env"


class MCPSettings(BaseSettings):
    # Konfigurasi Model
    model_config = SettingsConfigDict(env_file=str(env_path), env_file_encoding="utf-8")

    # MCP Server Endpoint
    mcp_server_url: str = "http://localhost:5000/projectwise/mcp"

    # Kunci API dan host model
    openai_api_key: str = str(os.getenv("OPENAI_API_KEY"))
    ollama_host: str = "http://localhost:11434"

    # Model dan parameter LLM
    llm_model: str = "gpt-4o-mini"
    embed_model: str = "text-embedding-3-small"
    llm_temperature: float = 0.0
