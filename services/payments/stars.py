from aiogram.types import LabeledPrice

from bot import texts
from services.billing.products import PRODUCTS, get_product


def invoice_params(product_code: str, settings) -> dict:
    product = get_product(product_code)
    if product is None:
        raise ValueError(f"unknown product {product_code}")
    amount = settings.stars_price(product_code)
    if amount <= 0:
        raise ValueError(f"no stars price for {product_code}")
    desc = (
        texts.INVOICE_DESC_PACK.format(n=product.crystals)
        if product.kind == "pack"
        else texts.INVOICE_DESC_SUB.format(days=product.days)
    )
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
