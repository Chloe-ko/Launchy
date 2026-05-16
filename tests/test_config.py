import tomllib
import uuid
import pytest
from pathlib import Path

import launchy.config as cfg_module
from launchy.config import _merge, _expand_with_deps
from launchy.utils import toml_dumps


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_toml(path: Path, data: dict):
    path.write_text(toml_dumps(data))


def _setup_dirs(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    games_dir = config_dir / "games"
    sets_dir = config_dir / "sets"
    config_dir.mkdir(); games_dir.mkdir(); sets_dir.mkdir()
    monkeypatch.setattr(cfg_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cfg_module, "GAMES_DIR", games_dir)
    monkeypatch.setattr(cfg_module, "SETS_DIR", sets_dir)
    return config_dir, games_dir, sets_dir


def _write_set(sets_dir: Path, sid: str, name="Test Set", requires=None, **extra):
    data = {"general": {"name": name, "requires": requires or []}, **extra}
    _write_toml(sets_dir / f"{sid}.toml", data)


# ---------------------------------------------------------------------------
# _merge
# ---------------------------------------------------------------------------

class TestMerge:
    def test_scalar_override_wins(self):
        assert _merge({"a": 1}, {"a": 2})["a"] == 2

    def test_base_key_preserved_when_not_overridden(self):
        result = _merge({"a": 1, "b": 2}, {"a": 99})
        assert result["b"] == 2

    def test_new_key_in_override_added(self):
        assert _merge({"a": 1}, {"b": 2})["b"] == 2

    def test_nested_dicts_merged_recursively(self):
        base = {"general": {"countdown": 5, "proton": ""}}
        over = {"general": {"proton": "GE-Proton"}}
        result = _merge(base, over)
        assert result["general"]["countdown"] == 5
        assert result["general"]["proton"] == "GE-Proton"

    def test_deeply_nested(self):
        base = {"a": {"b": {"c": 1, "d": 2}}}
        over = {"a": {"b": {"c": 99}}}
        result = _merge(base, over)
        assert result["a"]["b"]["c"] == 99
        assert result["a"]["b"]["d"] == 2

    def test_non_dict_override_replaces_dict(self):
        result = _merge({"a": {"x": 1}}, {"a": "scalar"})
        assert result["a"] == "scalar"

    def test_empty_base(self):
        assert _merge({}, {"a": 1}) == {"a": 1}

    def test_empty_override(self):
        assert _merge({"a": 1}, {}) == {"a": 1}


# ---------------------------------------------------------------------------
# _expand_with_deps
# ---------------------------------------------------------------------------

class TestExpandWithDeps:
    def test_no_deps_unchanged(self, tmp_path, monkeypatch):
        _, _, sets_dir = _setup_dirs(tmp_path, monkeypatch)
        _write_set(sets_dir, "a")
        assert _expand_with_deps({"a"}, ["a"]) == {"a"}

    def test_direct_dep_added(self, tmp_path, monkeypatch):
        _, _, sets_dir = _setup_dirs(tmp_path, monkeypatch)
        _write_set(sets_dir, "a", requires=["b"])
        _write_set(sets_dir, "b")
        result = _expand_with_deps({"a"}, ["a", "b"])
        assert "b" in result

    def test_transitive_deps_added(self, tmp_path, monkeypatch):
        _, _, sets_dir = _setup_dirs(tmp_path, monkeypatch)
        _write_set(sets_dir, "a", requires=["b"])
        _write_set(sets_dir, "b", requires=["c"])
        _write_set(sets_dir, "c")
        result = _expand_with_deps({"a"}, ["a", "b", "c"])
        assert result == {"a", "b", "c"}

    def test_dep_not_in_valid_set_ignored(self, tmp_path, monkeypatch):
        _, _, sets_dir = _setup_dirs(tmp_path, monkeypatch)
        _write_set(sets_dir, "a", requires=["phantom"])
        result = _expand_with_deps({"a"}, ["a"])  # "phantom" not in valid list
        assert "phantom" not in result

    def test_circular_deps_safe(self, tmp_path, monkeypatch):
        _, _, sets_dir = _setup_dirs(tmp_path, monkeypatch)
        _write_set(sets_dir, "a", requires=["b"])
        _write_set(sets_dir, "b", requires=["a"])
        result = _expand_with_deps({"a"}, ["a", "b"])
        assert result == {"a", "b"}

    def test_empty_enabled_returns_empty(self, tmp_path, monkeypatch):
        _setup_dirs(tmp_path, monkeypatch)
        assert _expand_with_deps(set(), ["a", "b"]) == set()


# ---------------------------------------------------------------------------
# get_games_with_skip_countdown
# ---------------------------------------------------------------------------

class TestGetGamesWithSkipCountdown:
    def test_no_games_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cfg_module, "GAMES_DIR", tmp_path / "nonexistent")
        assert cfg_module.get_games_with_skip_countdown() == []

    def test_empty_games_dir(self, tmp_path, monkeypatch):
        games_dir = tmp_path / "games"
        games_dir.mkdir()
        monkeypatch.setattr(cfg_module, "GAMES_DIR", games_dir)
        assert cfg_module.get_games_with_skip_countdown() == []

    def test_game_without_flag_excluded(self, tmp_path, monkeypatch):
        games_dir = tmp_path / "games"
        games_dir.mkdir()
        monkeypatch.setattr(cfg_module, "GAMES_DIR", games_dir)
        _write_toml(games_dir / "12345.toml", {"general": {"skip_countdown": False}})
        assert cfg_module.get_games_with_skip_countdown() == []

    def test_game_with_no_flag_excluded(self, tmp_path, monkeypatch):
        games_dir = tmp_path / "games"
        games_dir.mkdir()
        monkeypatch.setattr(cfg_module, "GAMES_DIR", games_dir)
        _write_toml(games_dir / "12345.toml", {"general": {}})
        assert cfg_module.get_games_with_skip_countdown() == []

    def test_game_with_flag_included(self, tmp_path, monkeypatch):
        games_dir = tmp_path / "games"
        games_dir.mkdir()
        monkeypatch.setattr(cfg_module, "GAMES_DIR", games_dir)
        _write_toml(games_dir / "12345.toml", {"general": {"skip_countdown": True}})
        assert "12345" in cfg_module.get_games_with_skip_countdown()

    def test_mixed_games(self, tmp_path, monkeypatch):
        games_dir = tmp_path / "games"
        games_dir.mkdir()
        monkeypatch.setattr(cfg_module, "GAMES_DIR", games_dir)
        _write_toml(games_dir / "111.toml", {"general": {"skip_countdown": True}})
        _write_toml(games_dir / "222.toml", {"general": {"skip_countdown": False}})
        _write_toml(games_dir / "333.toml", {"general": {}})
        result = cfg_module.get_games_with_skip_countdown()
        assert "111" in result
        assert "222" not in result
        assert "333" not in result


# ---------------------------------------------------------------------------
# get_merged_config
# ---------------------------------------------------------------------------

class TestGetMergedConfig:
    def test_uses_global_defaults_when_no_game_config(self, tmp_path, monkeypatch):
        config_dir, _, _ = _setup_dirs(tmp_path, monkeypatch)
        _write_toml(config_dir / "config.toml", {
            "general": {"countdown": 7, "proton": "proton-a"},
            "env": {"FOO": "1"},
        })
        result = cfg_module.get_merged_config("99999")
        assert result["general"]["countdown"] == 7
        assert result["env"]["FOO"] == "1"

    def test_per_game_proton_overrides_global(self, tmp_path, monkeypatch):
        config_dir, games_dir, _ = _setup_dirs(tmp_path, monkeypatch)
        _write_toml(config_dir / "config.toml", {"general": {"countdown": 5, "proton": "global-proton"}})
        _write_toml(games_dir / "111.toml", {"general": {"proton": "game-proton"}})
        assert cfg_module.get_merged_config("111")["general"]["proton"] == "game-proton"

    def test_empty_per_game_proton_inherits_global(self, tmp_path, monkeypatch):
        config_dir, games_dir, _ = _setup_dirs(tmp_path, monkeypatch)
        _write_toml(config_dir / "config.toml", {"general": {"countdown": 5, "proton": "global-proton"}})
        _write_toml(games_dir / "111.toml", {"general": {"proton": ""}})
        assert cfg_module.get_merged_config("111")["general"]["proton"] == "global-proton"

    def test_per_game_env_overrides_global(self, tmp_path, monkeypatch):
        config_dir, games_dir, _ = _setup_dirs(tmp_path, monkeypatch)
        _write_toml(config_dir / "config.toml", {"general": {"countdown": 5}, "env": {"FOO": "global", "BAR": "1"}})
        _write_toml(games_dir / "111.toml", {"env": {"FOO": "override"}})
        result = cfg_module.get_merged_config("111")
        assert result["env"]["FOO"] == "override"
        assert result["env"]["BAR"] == "1"

    def test_global_ignore_blocks_env_key(self, tmp_path, monkeypatch):
        config_dir, games_dir, _ = _setup_dirs(tmp_path, monkeypatch)
        _write_toml(config_dir / "config.toml", {"general": {"countdown": 5}, "env": {"FOO": "1", "BAR": "2"}})
        _write_toml(games_dir / "111.toml", {"global_ignore": {"env": ["FOO"]}})
        result = cfg_module.get_merged_config("111")
        assert "FOO" not in result["env"]
        assert result["env"]["BAR"] == "2"

    def test_global_args_in_extra(self, tmp_path, monkeypatch):
        config_dir, games_dir, _ = _setup_dirs(tmp_path, monkeypatch)
        _write_toml(config_dir / "config.toml", {"general": {"countdown": 5}, "args": {"extra": ["--global-arg"]}})
        _write_toml(games_dir / "111.toml", {"args": {"game_args": ["--game-arg"]}})
        result = cfg_module.get_merged_config("111")
        assert "--global-arg" in result["args"]["extra"]
        assert "--game-arg" in result["args"]["game_args"]

    def test_set_env_applied(self, tmp_path, monkeypatch):
        config_dir, games_dir, sets_dir = _setup_dirs(tmp_path, monkeypatch)
        sid = str(uuid.uuid4())
        _write_set(sets_dir, sid, env={"SET_VAR": "hello"})
        _write_toml(config_dir / "config.toml", {"general": {"countdown": 5}, "sets": {"order": [sid]}})
        _write_toml(games_dir / "111.toml", {"sets": {"enabled": [sid]}})
        assert cfg_module.get_merged_config("111")["env"]["SET_VAR"] == "hello"

    def test_high_priority_set_wins_env_conflict(self, tmp_path, monkeypatch):
        config_dir, games_dir, sets_dir = _setup_dirs(tmp_path, monkeypatch)
        s_high, s_low = str(uuid.uuid4()), str(uuid.uuid4())
        _write_set(sets_dir, s_high, env={"FOO": "high"})
        _write_set(sets_dir, s_low, env={"FOO": "low"})
        _write_toml(config_dir / "config.toml", {"general": {"countdown": 5}, "sets": {"order": [s_high, s_low]}})
        _write_toml(games_dir / "111.toml", {"sets": {"enabled": [s_high, s_low]}})
        assert cfg_module.get_merged_config("111")["env"]["FOO"] == "high"

    def test_per_game_env_overrides_set_env(self, tmp_path, monkeypatch):
        config_dir, games_dir, sets_dir = _setup_dirs(tmp_path, monkeypatch)
        sid = str(uuid.uuid4())
        _write_set(sets_dir, sid, env={"FOO": "from-set"})
        _write_toml(config_dir / "config.toml", {"general": {"countdown": 5}, "sets": {"order": [sid]}})
        _write_toml(games_dir / "111.toml", {"sets": {"enabled": [sid]}, "env": {"FOO": "from-game"}})
        assert cfg_module.get_merged_config("111")["env"]["FOO"] == "from-game"

    def test_wrapper_dedup_high_priority_wins(self, tmp_path, monkeypatch):
        config_dir, games_dir, sets_dir = _setup_dirs(tmp_path, monkeypatch)
        s_high, s_low = str(uuid.uuid4()), str(uuid.uuid4())
        _write_set(sets_dir, s_high, wrappers=["mangohud --dlsym"])
        _write_set(sets_dir, s_low, wrappers=["mangohud"])
        _write_toml(config_dir / "config.toml", {"general": {"countdown": 5}, "sets": {"order": [s_high, s_low]}})
        _write_toml(games_dir / "111.toml", {"sets": {"enabled": [s_high, s_low]}})
        wrappers = cfg_module.get_merged_config("111")["wrappers"]
        mangohud_entries = [w for w in wrappers if w.split()[0] == "mangohud"]
        assert len(mangohud_entries) == 1
        assert mangohud_entries[0] == "mangohud --dlsym"

    def test_set_args_included(self, tmp_path, monkeypatch):
        config_dir, games_dir, sets_dir = _setup_dirs(tmp_path, monkeypatch)
        sid = str(uuid.uuid4())
        _write_set(sets_dir, sid, args={"extra": ["--from-set"]})
        _write_toml(config_dir / "config.toml", {"general": {"countdown": 5}, "sets": {"order": [sid]}})
        _write_toml(games_dir / "111.toml", {"sets": {"enabled": [sid]}})
        assert "--from-set" in cfg_module.get_merged_config("111")["args"]["extra"]

    def test_disabled_set_not_applied(self, tmp_path, monkeypatch):
        config_dir, games_dir, sets_dir = _setup_dirs(tmp_path, monkeypatch)
        sid = str(uuid.uuid4())
        _write_set(sets_dir, sid, env={"SECRET": "yes"})
        _write_toml(config_dir / "config.toml", {"general": {"countdown": 5}, "sets": {"order": [sid]}})
        _write_toml(games_dir / "111.toml", {"sets": {"enabled": []}})
        assert "SECRET" not in cfg_module.get_merged_config("111")["env"]


# ---------------------------------------------------------------------------
# bootstrap_game_config
# ---------------------------------------------------------------------------

class TestBootstrapGameConfig:
    def test_no_op_if_file_exists(self, tmp_path, monkeypatch):
        config_dir, games_dir, sets_dir = _setup_dirs(tmp_path, monkeypatch)
        _write_toml(config_dir / "config.toml", {"general": {"countdown": 5}})
        _write_toml(games_dir / "111.toml", {"general": {"proton": "sentinel"}})
        cfg_module.bootstrap_game_config("111")
        loaded = tomllib.loads((games_dir / "111.toml").read_text())
        assert loaded["general"]["proton"] == "sentinel"

    def test_creates_file_with_default_enabled_sets(self, tmp_path, monkeypatch):
        config_dir, games_dir, sets_dir = _setup_dirs(tmp_path, monkeypatch)
        sid = str(uuid.uuid4())
        _write_set(sets_dir, sid, enabled_by_default_in_general=True)
        # enabled_by_default is under general.enabled_by_default
        _write_toml(sets_dir / f"{sid}.toml", {"general": {"name": "Default Set", "enabled_by_default": True}})
        _write_toml(config_dir / "config.toml", {"general": {"countdown": 5}, "sets": {"order": [sid]}})
        cfg_module.bootstrap_game_config("222")
        assert (games_dir / "222.toml").exists()
        loaded = tomllib.loads((games_dir / "222.toml").read_text())
        assert sid in loaded.get("sets", {}).get("enabled", [])

    def test_no_file_created_when_no_sets_default(self, tmp_path, monkeypatch):
        config_dir, games_dir, sets_dir = _setup_dirs(tmp_path, monkeypatch)
        sid = str(uuid.uuid4())
        _write_toml(sets_dir / f"{sid}.toml", {"general": {"name": "Non-default", "enabled_by_default": False}})
        _write_toml(config_dir / "config.toml", {"general": {"countdown": 5}, "sets": {"order": [sid]}})
        cfg_module.bootstrap_game_config("333")
        assert not (games_dir / "333.toml").exists()
