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
    assert (s.start_crystals, s.invite_crystals, s.bonus_free_amount, s.bonus_free_hours) == (3, 3, 3, 48)
    assert (s.bonus_sub_amount, s.bonus_sub_hours) == (10, 24)
    assert (s.stars_pack_15, s.stars_pack_50, s.stars_pack_100, s.stars_pack_300, s.stars_pack_1000) == (120, 350, 650, 1800, 4500)
    assert (s.stars_sub_week, s.stars_sub_month, s.stars_sub_3month) == (350, 990, 2490)
    assert (s.price_rub_sub_week, s.price_rub_sub_month, s.price_rub_sub_3month) == (450, 1290, 3290)
    assert (s.price_rub_pack_15, s.price_rub_pack_50, s.price_rub_pack_100, s.price_rub_pack_300, s.price_rub_pack_1000) == (150, 450, 850, 1990, 4990)
    assert s.tribute_pack_15_url == "https://web.tribute.tg/p/GVw"
    assert s.tribute_pack_50_url == "https://web.tribute.tg/p/FpD"
    assert s.tribute_pack_100_url == "https://web.tribute.tg/p/G6d"
    assert s.tribute_pack_300_url == "https://web.tribute.tg/p/G6e"
    assert s.tribute_pack_1000_url == "https://web.tribute.tg/p/GVz"
    assert (s.tribute_pack_15_id, s.tribute_pack_50_id, s.tribute_pack_100_id, s.tribute_pack_300_id, s.tribute_pack_1000_id) == ("GVw", "FpD", "G6d", "G6e", "GVz")
    assert (s.cost_base, s.cost_premium, s.cost_video) == (1, 3, 3)
    assert s.video_model == "bytedance/seedance-1-lite"
    assert s.video_seconds == 5 and s.video_resolution == "720p"
    assert s.replicate_api_token == ""
    assert s.model_base_air == "runware:108@22"
    assert s.model_base_family == "qwen"
    assert s.model_base_steps == 28 and s.model_base_cfg == 5.0
    assert s.sdxl_face_weight == 1.2 and s.sdxl_place_weight == 0.0
    assert s.sdxl_edit_strength == 0.32
    assert s.model_premium_air == "google:4@3"
    assert s.model_base_max_refs == 3 and s.model_premium_max_refs == 14


def test_dotenv_file_is_loaded(tmp_path, monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.delenv("ADMIN_IDS", raising=False)
    env = tmp_path / ".env"
    env.write_text("BOT_TOKEN=from-file\nADMIN_IDS=1,2\n", encoding="utf-8")
    s = Settings(_env_file=env)
    assert s.bot_token == "from-file" and s.admin_ids == [1, 2]


def test_scheduler_quotes_from_env_are_stripped(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "x")
    monkeypatch.setenv("MODEL_BASE_SCHEDULER", '"DPM++ 2M Karras"')
    s = Settings(_env_file=None)
    assert s.model_base_scheduler == "DPM++ 2M Karras"


def test_frame_size_per_model(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "x")
    s = Settings(_env_file=None)
    assert s.frame_size("base", "portrait") == (1024, 1536)
    assert s.frame_size("base", "landscape") == (1536, 1024)
    assert s.frame_size("premium", "portrait") == (1696, 2528)
    assert s.frame_size("premium", "landscape") == (2528, 1696)
    w, h = s.frame_size("base", "portrait")
    assert 512 <= w <= 2048 and 512 <= h <= 2048 and w % 8 == 0 and h % 8 == 0
