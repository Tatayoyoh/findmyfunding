from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_path: str = "data/findmyfundings.db"
    scrape_interval_days: int = 30
    excel_path: str = "data/Cartographie des financements.xlsx"

    # Firecrawl self-host
    firecrawl_api_url: str = "http://localhost:3002"
    firecrawl_api_key: str = ""  # optional for self-host

    # DeepSeek (used by excel_import for date extraction; same key used by Firecrawl)
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def db_path(self) -> Path:
        return Path(self.database_path)


settings = Settings()
