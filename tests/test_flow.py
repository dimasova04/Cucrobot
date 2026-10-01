from types import SimpleNamespace

from bot import texts
from bot.flow import effective_tier, request_from_state, result_buttons, scene_label, validate_custom_scene, validate_detail


def test_validators():
    assert validate_detail("зимой, в пальто") is None
    assert validate_detail("надень на неё белый купальник") is None
    assert validate_detail("x" * 300) is None
    assert validate_detail("x" * 301) == texts.DETAIL_TOO_LONG
    assert validate_detail("голые") == texts.TEXT_REJECTED
    assert validate_custom_scene("y" * 200) is None
    assert validate_custom_scene("y" * 201) == texts.CUSTOM_SCENE_TOO_LONG


def test_new_scene_drops_previous_detail():
    from bot.flow import apply_catalog_scene, apply_custom_scene

    data = {"scene_id": 1, "custom_text": "старое", "custom_file_id": "f", "detail": "белый купальник"}
    apply_catalog_scene(data, 8)
    assert data["scene_id"] == 8 and data["detail"] is None
    assert data["custom_text"] is None and data["custom_file_id"] is None
    apply_custom_scene(data, text="на крыше")
    assert data["scene_id"] is None and data["custom_text"] == "на крыше" and data["detail"] is None


def test_scene_label():
    d = {"people": ["a", "b"], "actors": [1], "scene_id": None, "custom_text": "on mars", "custom_file_id": None, "detail": None}
    assert scene_label(d, None) == texts.CUSTOM_SCENE_LABEL_TEXT
    d2 = {**d, "custom_text": None, "custom_file_id": "f"}
    assert scene_label(d2, None) == texts.CUSTOM_SCENE_LABEL_PHOTO
    assert scene_label({**d, "scene_id": 3}, "Яхта") == "Яхта"


def test_result_buttons_one_actor():
    d = {"people": ["a"], "actors": [1], "last_generation_id": 7}
    cbs = [cb for _, cb in result_buttons(d)]
    assert cbs == [
        "gen:more",
        "gen:change_scene",
        "gen:change_actor",
        "gen:add_actor",
        "gen:detail",
        "gen:hd:7",
        "gen:new",
    ]


def test_result_buttons_two_actors_hide_add_actor():
    d = {"people": ["a"], "actors": [1, 2], "last_generation_id": 7}
    cbs = [cb for _, cb in result_buttons(d)]
    assert cbs == ["gen:more", "gen:change_scene", "gen:change_actor", "gen:detail", "gen:hd:7", "gen:new"]


def test_result_buttons_hero_hides_add_actor():
    d = {"people": ["a"], "actors": [], "hero_file_id": "h1", "last_generation_id": 7}
    cbs = [cb for _, cb in result_buttons(d)]
    assert cbs == ["gen:more", "gen:change_scene", "gen:change_actor", "gen:detail", "gen:hd:7", "gen:new"]


def test_result_buttons_without_generation_id_have_no_hd():
    cbs = [cb for _, cb in result_buttons({"people": ["a"], "actors": [1]})]
    assert not [c for c in cbs if c.startswith("gen:hd")]


def test_result_kb_puts_new_photo_on_its_own_row():
    from bot import keyboards

    kb = keyboards.result_kb({"people": ["a"], "actors": [1], "last_generation_id": 7})
    rows = kb.inline_keyboard
    assert [len(r) for r in rows] == [2, 2, 2, 1]
    assert rows[-1][0].callback_data == "gen:new"


def test_request_from_state():
    d = {"people": ["a"], "actors": [1, 2], "scene_id": 5, "custom_text": None, "custom_file_id": None, "detail": "x"}
    r = request_from_state(9, d, "premium")
    assert r.user_id == 9 and r.actor_ids == [1, 2] and r.scene_id == 5 and r.tier == "premium" and r.detail == "x"
    assert r.hero_file_id is None


def test_request_from_state_with_hero():
    d = {"people": ["a"], "actors": [], "hero_file_id": "h1", "scene_id": 5, "custom_text": None, "custom_file_id": None, "detail": None}
    r = request_from_state(9, d, "base")
    assert r.actor_ids == [] and r.hero_file_id == "h1"


def test_is_complete():
    from bot.flow import empty_data, is_complete

    d = empty_data()
    assert "tier" not in d
    assert not is_complete(d)
    d.update(people=["a"], actors=[1], scene_id=2)
    assert is_complete(d)
    d.update(scene_id=None, custom_text="on mars")
    assert is_complete(d)
    d.update(actors=[])
    assert not is_complete(d)
    # «свой герой» заменяет актёра из каталога
    d.update(hero_file_id="h1")
    assert is_complete(d)


def test_paginate():
    from bot.flow import paginate

    items = list(range(25))
    assert paginate(items, 0, 10) == (items[:10], False, True)
    assert paginate(items, 1, 10) == (items[10:20], True, True)
    assert paginate(items, 2, 10) == (items[20:], True, False)
    # выход за границы зажимается к последней странице
    assert paginate(items, 99, 10) == (items[20:], True, False)
    assert paginate(items, -5, 10) == (items[:10], False, True)
    # одна страница целиком
    assert paginate([1, 2], 0, 10) == ([1, 2], False, False)
    assert paginate([], 0, 10) == ([], False, False)


def test_effective_tier():
    from datetime import timedelta

    from database.base import utcnow

    subscribed_premium = SimpleNamespace(preferred_tier="premium", sub_until=utcnow() + timedelta(days=1))
    assert effective_tier(subscribed_premium) == "premium"

    lapsed_premium = SimpleNamespace(preferred_tier="premium", sub_until=None)
    assert effective_tier(lapsed_premium) == "base"

    expired_premium = SimpleNamespace(preferred_tier="premium", sub_until=utcnow() - timedelta(days=1))
    assert effective_tier(expired_premium) == "base"

    subscribed_base = SimpleNamespace(preferred_tier="base", sub_until=utcnow() + timedelta(days=1))
    assert effective_tier(subscribed_base) == "base"
