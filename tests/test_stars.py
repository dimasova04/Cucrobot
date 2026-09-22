import pytest

from config.settings import Settings
from services.payments import stars


def test_invoice_params():
    s = Settings(_env_file=None, bot_token="x")
    p = stars.invoice_params("pack_50", s)
    assert p["currency"] == "XTR" and p["provider_token"] == "" and p["payload"] == "pack_50"
    assert p["prices"][0].amount == 250
    with pytest.raises(ValueError):
        stars.invoice_params("nope", s)


def test_parse_payload():
    assert stars.parse_payload("sub_month") == "sub_month"
    assert stars.parse_payload("garbage") is None
