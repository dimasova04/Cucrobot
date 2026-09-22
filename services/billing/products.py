from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    code: str
    kind: str  # pack / sub
    title: str
    crystals: int = 0
    days: int = 0


PACKS = [
    Product("pack_50", "pack", "50 кристалликов", crystals=50),
    Product("pack_100", "pack", "100 кристалликов", crystals=100),
    Product("pack_300", "pack", "300 кристалликов", crystals=300),
]
SUBS = [
    Product("sub_week", "sub", "Подписка на неделю", days=7),
    Product("sub_month", "sub", "Подписка на месяц", days=30),
    Product("sub_3month", "sub", "Подписка на 3 месяца", days=90),
]
PRODUCTS = {p.code: p for p in PACKS + SUBS}


def get_product(code: str) -> Product | None:
    return PRODUCTS.get(code)
