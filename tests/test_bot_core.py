from types import SimpleNamespace

from bot import keyboards, texts
from bot.middlewares import needs_rules
from database.models import User


def _msg(text):
    return SimpleNamespace(text=text, data=None)


def _cb(data):
    return SimpleNamespace(text=None, data=data)


def test_needs_rules():
    u = User(id=1)
    assert needs_rules(u, _msg("привет"))
    assert not needs_rules(u, _msg("/start"))
    assert not needs_rules(u, _msg("/start ref123"))
    assert not needs_rules(u, _cb("rules:accept"))
    assert needs_rules(u, _cb("shop:open"))
    u.rules_accepted_at = __import__("datetime").datetime(2026, 1, 1)
    assert not needs_rules(u, _msg("привет"))


def test_grid_layout_and_extra_rows():
    kb = keyboards.grid([("A", "a"), ("B", "b"), ("C", "c")], cols=2, extra_rows=[[("Назад", "back")]])
    rows = kb.inline_keyboard
    assert [len(r) for r in rows] == [2, 1, 1]
    assert rows[0][0].text == "A" and rows[0][0].callback_data == "a"
    assert rows[2][0].callback_data == "back"


def test_main_menu_has_five_buttons():
    kb = keyboards.main_menu()
    btn_texts = [b.text for row in kb.keyboard for b in row]
    assert len(btn_texts) == 5 and "📸 Создать фото" in btn_texts


def test_cancel_row():
    assert keyboards.cancel_row() == [(texts.BTN_CANCEL, "gen:cancel")]
