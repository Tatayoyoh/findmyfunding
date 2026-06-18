from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_path: str = "data/findmyfundings.db"
    scrape_interval_days: int = 30
    excel_path: str = "data/Cartographie des financements.xlsx"

    # DeepSeek — LLM extraction (scraper) + Excel date parsing (excel_import).
    # OpenAI-compatible API.
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def db_path(self) -> Path:
        return Path(self.database_path)


settings = Settings()
