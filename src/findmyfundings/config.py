from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_path: str = "data/findmyfundings.db"
    anthropic_api_key: str = ""
    scrape_interval_days: int = 30
    excel_path: str = "data/Cartographie des financements.xlsx"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def db_path(self) -> Path:
        return Path(self.database_path)


settings = Settings()
