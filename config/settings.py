from functools import lru_cache
import os
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import EnvSettingsSource


class CustomEnvSettingsSource(EnvSettingsSource):
    def decode_complex_value(self, field_name: str, field, value: str) -> Any:
        if field_name == "admin_ids" and isinstance(value, str):
            # Parse CSV directly without JSON decoding
            return [int(x.strip()) for x in value.split(",") if x.strip()]
        return super().decode_complex_value(field_name, field, value)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    admin_ids: list[int] = []
    database_url: str = "sqlite+aiosqlite:///./cucrobot.db"
    redis_url: str = ""

    runware_api_key: str = ""
    model_base_air: str = "runware:400@2"
    model_premium_air: str = "google:4@3"
    model_base_max_refs: int = 4
    model_premium_max_refs: int = 14

    tribute_api_key: str = ""
    tribute_webhook_path: str = "/webhooks/tribute"
    webhook_port: int = 8080
    tribute_pack_50_url: str = ""
    tribute_pack_50_id: str = ""
    tribute_pack_100_url: str = ""
    tribute_pack_100_id: str = ""
    tribute_pack_300_url: str = ""
    tribute_pack_300_id: str = ""
    tribute_sub_week_url: str = ""
    tribute_sub_week_id: str = ""
    tribute_sub_month_url: str = ""
    tribute_sub_month_id: str = ""
    tribute_sub_3month_url: str = ""
    tribute_sub_3month_id: str = ""
    tribute_buy_stars_url: str = ""

    stars_pack_50: int = 250
    stars_pack_100: int = 450
    stars_pack_300: int = 1200
    stars_sub_week: int = 300
    stars_sub_month: int = 900
    stars_sub_3month: int = 2200

    start_crystals: int = 3
    bonus_free_amount: int = 3
    bonus_free_hours: int = 48
    bonus_sub_amount: int = 10
    bonus_sub_hours: int = 24
    cost_base: int = 1
    cost_premium: int = 3
    session_ttl_min: int = 30
    gen_timeout_sec: int = 90

    @classmethod
    def _settings_build_values(cls, sources, init_kwargs):
        # Replace EnvSettingsSource with our CustomEnvSettingsSource
        new_sources = []
        for source in sources:
            if isinstance(source, EnvSettingsSource) and not isinstance(source, CustomEnvSettingsSource):
                # Replace with our custom version
                new_sources.append(CustomEnvSettingsSource(cls))
            else:
                new_sources.append(source)

        # Build values from all sources
        d = {}
        for source in new_sources:
            d.update(source())
        return d

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids

    def tribute_url(self, product_code: str) -> str:
        return getattr(self, f"tribute_{product_code}_url", "")

    def tribute_id(self, product_code: str) -> str:
        return getattr(self, f"tribute_{product_code}_id", "")

    def stars_price(self, product_code: str) -> int:
        return getattr(self, f"stars_{product_code}")


@lru_cache
def get_settings() -> Settings:
    return Settings()
