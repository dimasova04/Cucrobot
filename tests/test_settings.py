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
    assert (s.start_crystals, s.bonus_free_amount, s.bonus_free_hours) == (3, 3, 24)
    assert (s.bonus_sub_amount, s.bonus_sub_hours) == (10, 24)
    assert (s.cost_base, s.cost_premium) == (1, 3)
    assert s.model_base_air == "bytedance:seedream@4.5"
    assert s.model_premium_air == "google:4@3"
    assert s.model_base_max_refs == 14 and s.model_premium_max_refs == 14


def test_dotenv_file_is_loaded(tmp_path, monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.delenv("ADMIN_IDS", raising=False)
    env = tmp_path / ".env"
    env.write_text("BOT_TOKEN=from-file\nADMIN_IDS=1,2\n", encoding="utf-8")
    s = Settings(_env_file=env)
    assert s.bot_token == "from-file" and s.admin_ids == [1, 2]


def test_frame_size_per_model(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "x")
    s = Settings(_env_file=None)
    assert s.frame_size("base", "portrait") == (1664, 2496)
    assert s.frame_size("base", "landscape") == (2496, 1664)
    assert s.frame_size("premium", "portrait") == (832, 1248)
    w, h = s.frame_size("base", "portrait")
    assert 3_686_400 <= w * h <= 16_777_216  # лимит Seedream 4.5
