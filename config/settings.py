from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    admin_ids: Annotated[list[int], NoDecode] = []
    database_url: str = "sqlite+aiosqlite:///./cucrobot.db"
    redis_url: str = ""

    runware_api_key: str = ""
    model_base_air: str = "bytedance:seedream@4.5"
    model_premium_air: str = "google:4@3"
    model_base_max_refs: int = 14
    model_premium_max_refs: int = 14
    # Размеры кадра по модели: Seedream 4.5 требует >= 3.69 Мпикс, Nano Banana 2 работает с 1K.
    model_base_portrait: str = "1664x2496"
    model_base_landscape: str = "2496x1664"
    model_premium_portrait: str = "832x1248"
    model_premium_landscape: str = "1248x832"

    tribute_api_key: str = ""
    tribute_webhook_path: str = "/webhooks/tribute"
    webhook_port: int = 8080
    # Публичный адрес мини-приложения; пусто — кнопки «Кабинет» просто не будет.
    webapp_url: str = ""
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

    stars_pack_50: int = 199
    stars_pack_100: int = 349
    stars_pack_300: int = 899
    stars_sub_week: int = 229
    stars_sub_month: int = 469
    stars_sub_3month: int = 999
    # Цены в рублях только для показа в боте; реальную цену берёт Tribute. 0 = не показывать.
    price_rub_pack_50: int = 0
    price_rub_pack_100: int = 0
    price_rub_pack_300: int = 0
    price_rub_sub_week: int = 290
    price_rub_sub_month: int = 590
    price_rub_sub_3month: int = 1290

    start_crystals: int = 3
    bonus_free_amount: int = 3
    bonus_free_hours: int = 24
    bonus_sub_amount: int = 10
    bonus_sub_hours: int = 24
    cost_base: int = 1
    cost_premium: int = 3
    session_ttl_min: int = 30
    gen_timeout_sec: int = 90

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, v):
        if isinstance(v, str):
            return [int(x) for x in v.split(",") if x.strip()]
        return v

    def frame_size(self, tier: str, orientation: str) -> tuple[int, int]:
        raw = getattr(self, f"model_{tier}_{orientation}")
        w, h = raw.lower().split("x")
        return int(w), int(h)

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids

    def tribute_url(self, product_code: str) -> str:
        return getattr(self, f"tribute_{product_code}_url", "")

    def tribute_id(self, product_code: str) -> str:
        return getattr(self, f"tribute_{product_code}_id", "")

    def stars_price(self, product_code: str) -> int:
        return getattr(self, f"stars_{product_code}")

    def rub_price(self, product_code: str) -> int:
        return getattr(self, f"price_rub_{product_code}", 0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
