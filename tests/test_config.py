from backend import config


class TestReidConfig:
    def test_sim_threshold(self):
        assert config.REID_SIM_THRESHOLD == 0.55

    def test_max_embeddings(self):
        assert config.REID_MAX_EMBEDDINGS == 30

    def test_max_age_days(self):
        # 0 — авто-удаление старых личностей отключено («навсегда»)
        assert config.REID_MAX_AGE_DAYS == 0

    def test_gallery_path_exists(self):
        assert config.REID_GALLERY_PATH is not None

    def test_embedding_ttl_defaults(self):
        # Затухание памяти по времени включено по умолчанию (положительный TTL),
        # настраивается через env REID_EMB_MAX_AGE_DAYS.
        assert config.REID_EMB_MAX_AGE_DAYS > 0
        assert config.REID_EMB_CLEAN_INTERVAL > 0

    def test_body_persistence_defaults(self):
        # Дескрипторы тела: короткий TTL (одежда устаревает) + периодический флаш.
        assert config.REID_BODY_MAX_AGE_DAYS > 0
        assert config.REID_FLUSH_INTERVAL > 0


class TestDetectModes:
    def test_keys_exist(self):
        assert 'people' in config.DETECT_MODES
        assert 'ppe' in config.DETECT_MODES
        assert 'faces' in config.DETECT_MODES

    def test_values_are_booleans(self):
        assert isinstance(config.DETECT_MODES['people'], bool)
        assert isinstance(config.DETECT_MODES['ppe'], bool)
        assert isinstance(config.DETECT_MODES['faces'], bool)


class TestDetectionConfig:
    def test_conf_thresh(self):
        assert config.CONF_THRESH == 0.75

    def test_font_sizes(self):
        assert config.FONT_SIZE_SMALL == 14
        assert config.FONT_SIZE_NORMAL == 18
        assert config.FONT_SIZE_LARGE == 22


class TestCameraManagement:
    def test_cameras_config_is_dict(self):
        assert isinstance(config.CAMERAS, dict)
        assert len(config.CAMERAS) > 0


class TestConstants:
    def test_track_expiry(self):
        from backend.core.state import TRACK_EXPIRY
        assert TRACK_EXPIRY == 60.0

    def test_class_names_contains_ppe(self):
        assert "Каска" in config.CLASS_NAMES.values()
        assert "Человек" in config.CLASS_NAMES.values()
        assert "Без каски" in config.CLASS_NAMES.values()
