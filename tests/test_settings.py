from config.settings import Settings


def test_admin_ids_parsed_from_csv(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "x")
    monkeypatch.setenv("ADMIN_IDS", "607396740, 470057063")
    s = Settings(_env_file=None)
    assert s.admin_ids == [607396740, 470057063]
    assert s.is_admin(607396740)
    assert not s.is_admin(1)


def test_economy_defaults(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "x")
    s = Settings(_env_file=None)
    assert (s.start_crystals, s.bonus_free_amount, s.bonus_free_hours) == (3, 3, 48)
    assert (s.bonus_sub_amount, s.bonus_sub_hours) == (10, 24)
    assert (s.cost_base, s.cost_premium) == (1, 3)
    assert s.model_base_air == "runware:400@2"
    assert s.model_premium_air == "google:4@3"
    assert s.model_base_max_refs == 4 and s.model_premium_max_refs == 14
