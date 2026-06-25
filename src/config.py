from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_path: str = "data/findmyfundings.db"
    scrape_interval_days: int = 30
    excel_path: str = "data/Cartographie des financements.xlsx"

    # Turso (libSQL) — durable remote DB. When set, all queries go to the remote
    # primary (no local file). Required in production: FastAPI Cloud has an
    # ephemeral filesystem and spins up multiple replicas, so a local SQLite file
    # is not shared nor persisted. When empty, falls back to the local file at
    # database_path (dev).
    turso_database_url: str = ""
    turso_auth_token: str = ""

    # DeepSeek — LLM extraction (scraper) + Excel date parsing (excel_import).
    # OpenAI-compatible API.
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-v4-pro"

    # Thinking mode (https://api-docs.deepseek.com/guides/thinking_mode)
    deepseek_thinking: bool = True
    deepseek_reasoning_effort: str = "high"  # "high" | "max"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def deepseek_thinking_extra_body(self) -> dict:
        """extra_body payload enabling DeepSeek thinking mode (empty if disabled)."""
        if not self.deepseek_thinking:
            return {}
        return {"thinking": {"type": "enabled"}}

    @property
    def db_path(self) -> Path:
        return Path(self.database_path)

    @property
    def use_remote_db(self) -> bool:
        """True when a Turso remote DB is configured (production)."""
        return bool(self.turso_database_url)


settings = Settings()
