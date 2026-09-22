from types import SimpleNamespace

import pytest

from bot import bonus_card, texts
from config.settings import Settings
from database.base import utcnow
from database.models import User


class _FakeBot:
    def __init__(self):
        self.calls = []

    async def send_photo(self, chat_id, photo, caption=None, reply_markup=None):
        self.calls.append((chat_id, photo, caption, reply_markup))
        return SimpleNamespace(photo=[SimpleNamespace(file_id="cached")])


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch):
    monkeypatch.setattr(bonus_card, "_cached_file_id", None)


async def test_send_bonus_card_sends_and_caches_file_id():
    settings = Settings(_env_file=None, bot_token="x")
    user = User(id=1, crystals=0, last_bonus_at=None)
    bot = _FakeBot()

    await bonus_card.send_bonus_card(bot, user.id, user, settings)

    assert len(bot.calls) == 1
    chat_id, photo, caption, reply_markup = bot.calls[0]
    assert chat_id == user.id
    assert caption == texts.BONUS_CARD.format(n=settings.bonus_free_amount)
    buttons = [b for row in reply_markup.inline_keyboard for b in row]
    assert len(buttons) == 1
    assert buttons[0].callback_data == "bonus:claim"
    assert bonus_card._cached_file_id == "cached"

    # второй вызов переиспользует закэшированный file_id вместо повторной загрузки
    await bonus_card.send_bonus_card(bot, user.id, user, settings)
    assert len(bot.calls) == 2
    assert bot.calls[1][1] == "cached"


async def test_send_bonus_card_skips_when_not_ready():
    settings = Settings(_env_file=None, bot_token="x")
    user = User(id=2, crystals=0, last_bonus_at=utcnow())
    bot = _FakeBot()

    await bonus_card.send_bonus_card(bot, user.id, user, settings)

    assert bot.calls == []
