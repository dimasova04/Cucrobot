from bot import texts
from bot.flow import request_from_state, scene_label, summary, validate_custom_scene, validate_detail


def test_validators():
    assert validate_detail("зимой, в пальто") is None
    assert validate_detail("x" * 101) == texts.DETAIL_TOO_LONG
    assert validate_detail("голые") == texts.TEXT_REJECTED
    assert validate_custom_scene("y" * 200) is None
    assert validate_custom_scene("y" * 201) == texts.CUSTOM_SCENE_TOO_LONG


def test_scene_label_and_summary():
    d = {"people": ["a", "b"], "actors": [1], "scene_id": None, "custom_text": "on mars", "custom_file_id": None, "detail": None}
    assert scene_label(d, None) == texts.CUSTOM_SCENE_LABEL_TEXT
    d2 = {**d, "custom_text": None, "custom_file_id": "f"}
    assert scene_label(d2, None) == texts.CUSTOM_SCENE_LABEL_PHOTO
    assert scene_label({**d, "scene_id": 3}, "Яхта") == "Яхта"
    s = summary(d, ["Стэйтем"], texts.CUSTOM_SCENE_LABEL_TEXT, "base", 1, 7)
    assert "Людей: 2" in s and "Стэйтем" in s and "Деталь: нет" in s and "Спишется 1" in s and "Баланс: 7" in s


def test_request_from_state():
    d = {"people": ["a"], "actors": [1, 2], "scene_id": 5, "custom_text": None, "custom_file_id": None, "detail": "x"}
    r = request_from_state(9, d, "premium")
    assert r.user_id == 9 and r.actor_ids == [1, 2] and r.scene_id == 5 and r.tier == "premium" and r.detail == "x"


def test_is_complete():
    from bot.flow import empty_data, is_complete

    d = empty_data()
    assert not is_complete(d)
    d.update(people=["a"], actors=[1], scene_id=2)
    assert is_complete(d)
    d.update(scene_id=None, custom_text="on mars")
    assert is_complete(d)
    d.update(actors=[])
    assert not is_complete(d)
