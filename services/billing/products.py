from dataclasses import dataclass

from bot.texts import PRODUCT_TITLES


@dataclass(frozen=True)
class Product:
    code: str
    kind: str  # pack / sub
    title: str
    crystals: int = 0
    days: int = 0


PACKS = [
    Product("pack_50", "pack", PRODUCT_TITLES["pack_50"], crystals=50),
    Product("pack_100", "pack", PRODUCT_TITLES["pack_100"], crystals=100),
    Product("pack_300", "pack", PRODUCT_TITLES["pack_300"], crystals=300),
]
SUBS = [
    # crystals у подписки — разовый подарок при покупке/продлении, сверх ежедневного бонуса
    Product("sub_week", "sub", PRODUCT_TITLES["sub_week"], crystals=5, days=7),
    Product("sub_month", "sub", PRODUCT_TITLES["sub_month"], crystals=20, days=30),
    Product("sub_3month", "sub", PRODUCT_TITLES["sub_3month"], crystals=60, days=90),
]
PRODUCTS = {p.code: p for p in PACKS + SUBS}


def get_product(code: str) -> Product | None:
    return PRODUCTS.get(code)
