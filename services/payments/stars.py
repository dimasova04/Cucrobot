from aiogram.types import LabeledPrice

from services.billing.products import PRODUCTS, get_product


def invoice_params(product_code: str, settings) -> dict:
    product = get_product(product_code)
    if product is None:
        raise ValueError(f"unknown product {product_code}")
    amount = settings.stars_price(product_code)
    if amount <= 0:
        raise ValueError(f"no stars price for {product_code}")
    desc = f"+{product.crystals} кристалликов" if product.kind == "pack" else f"{product.days} дней подписки"
    return {
        "title": product.title,
        "description": desc,
        "payload": product_code,
        "provider_token": "",
        "currency": "XTR",
        "prices": [LabeledPrice(label=product.title, amount=amount)],
    }


def parse_payload(payload: str) -> str | None:
    return payload if payload in PRODUCTS else None
