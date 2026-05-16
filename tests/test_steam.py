import pytest
from pathlib import Path
import launchy.steam as steam_module
from launchy.steam import (
    _acf_field,
    _header_only_image,
    _header_image,
    get_steam_launch_env,
    get_steam_launch_wrappers,
    get_steam_launch_args,
)


def _make_steam_root(tmp_path: Path) -> Path:
    root = tmp_path / "steam"
    (root / "steamapps").mkdir(parents=True)
    (root / "appcache" / "librarycache").mkdir(parents=True)
    return root


class TestAcfField:
    def test_reads_field(self, tmp_path):
        f = tmp_path / "app.acf"
        f.write_text('"name"\t"Half-Life 2"')
        assert _acf_field(f, "name") == "Half-Life 2"

    def test_missing_field_returns_none(self, tmp_path):
        f = tmp_path / "app.acf"
        f.write_text('"name"\t"Half-Life 2"')
        assert _acf_field(f, "installdir") is None

    def test_case_insensitive(self, tmp_path):
        f = tmp_path / "app.acf"
        f.write_text('"InstallDir"\t"hl2"')
        assert _acf_field(f, "installdir") == "hl2"

    def test_missing_file_returns_none(self, tmp_path):
        assert _acf_field(tmp_path / "nope.acf", "name") is None

    def test_empty_value(self, tmp_path):
        f = tmp_path / "app.acf"
        f.write_text('"proton"\t""')
        assert _acf_field(f, "proton") == ""


class TestHeaderOnlyImage:
    def test_flat_appid_dir(self, tmp_path, monkeypatch):
        root = _make_steam_root(tmp_path)
        monkeypatch.setattr(steam_module, "STEAM_ROOT", root)
        cache = root / "appcache" / "librarycache"
        appid_dir = cache / "12345"
        appid_dir.mkdir()
        img = appid_dir / "library_header.jpg"
        img.write_bytes(b"fake")
        assert _header_only_image("12345") == img

    def test_hash_subdir(self, tmp_path, monkeypatch):
        root = _make_steam_root(tmp_path)
        monkeypatch.setattr(steam_module, "STEAM_ROOT", root)
        cache = root / "appcache" / "librarycache"
        subdir = cache / "12345" / "abc123hash"
        subdir.mkdir(parents=True)
        img = subdir / "library_header.jpg"
        img.write_bytes(b"fake")
        assert _header_only_image("12345") == img

    def test_old_flat_format(self, tmp_path, monkeypatch):
        root = _make_steam_root(tmp_path)
        monkeypatch.setattr(steam_module, "STEAM_ROOT", root)
        cache = root / "appcache" / "librarycache"
        img = cache / "12345_header.jpg"
        img.write_bytes(b"fake")
        assert _header_only_image("12345") == img

    def test_not_found_returns_none(self, tmp_path, monkeypatch):
        root = _make_steam_root(tmp_path)
        monkeypatch.setattr(steam_module, "STEAM_ROOT", root)
        assert _header_only_image("99999") is None

    def test_no_steam_root_returns_none(self, monkeypatch):
        monkeypatch.setattr(steam_module, "STEAM_ROOT", None)
        assert _header_only_image("12345") is None

    def test_prefers_appid_dir_over_old_flat(self, tmp_path, monkeypatch):
        root = _make_steam_root(tmp_path)
        monkeypatch.setattr(steam_module, "STEAM_ROOT", root)
        cache = root / "appcache" / "librarycache"
        appid_dir = cache / "12345"
        appid_dir.mkdir()
        new_img = appid_dir / "library_header.jpg"
        new_img.write_bytes(b"new")
        old_img = cache / "12345_header.jpg"
        old_img.write_bytes(b"old")
        assert _header_only_image("12345") == new_img


class TestHeaderImage:
    def test_prefers_hero(self, tmp_path, monkeypatch):
        root = _make_steam_root(tmp_path)
        monkeypatch.setattr(steam_module, "STEAM_ROOT", root)
        cache = root / "appcache" / "librarycache"
        appid_dir = cache / "12345"
        appid_dir.mkdir()
        hero = appid_dir / "library_hero.jpg"
        hero.write_bytes(b"hero")
        header = appid_dir / "library_header.jpg"
        header.write_bytes(b"header")
        assert _header_image("12345") == hero

    def test_falls_back_to_header(self, tmp_path, monkeypatch):
        root = _make_steam_root(tmp_path)
        monkeypatch.setattr(steam_module, "STEAM_ROOT", root)
        cache = root / "appcache" / "librarycache"
        appid_dir = cache / "12345"
        appid_dir.mkdir()
        header = appid_dir / "library_header.jpg"
        header.write_bytes(b"header")
        assert _header_image("12345") == header

    def test_old_flat_hero_format(self, tmp_path, monkeypatch):
        root = _make_steam_root(tmp_path)
        monkeypatch.setattr(steam_module, "STEAM_ROOT", root)
        cache = root / "appcache" / "librarycache"
        img = cache / "12345_library_hero.jpg"
        img.write_bytes(b"hero")
        assert _header_image("12345") == img

    def test_not_found_returns_none(self, tmp_path, monkeypatch):
        root = _make_steam_root(tmp_path)
        monkeypatch.setattr(steam_module, "STEAM_ROOT", root)
        assert _header_image("99999") is None

    def test_no_steam_root_returns_none(self, monkeypatch):
        monkeypatch.setattr(steam_module, "STEAM_ROOT", None)
        assert _header_image("12345") is None


def _make_localconfig(steam_root: Path, userid: str, appid: str, launch_opts: str):
    user_cfg = steam_root / "userdata" / userid / "config"
    user_cfg.mkdir(parents=True)
    lcv = user_cfg / "localconfig.vdf"
    lcv.write_text(
        f'"UserLocalConfigStore"\n{{\n'
        f'  "Software"\n  {{\n'
        f'    "apps"\n    {{\n'
        f'      "{appid}"\n      {{\n'
        f'        "LaunchOptions"\t"{launch_opts}"\n'
        f'      }}\n'
        f'    }}\n'
        f'  }}\n'
        f'}}\n'
    )
    return lcv


class TestGetSteamLaunchEnv:
    def test_parses_env_vars(self, tmp_path, monkeypatch):
        root = _make_steam_root(tmp_path)
        monkeypatch.setattr(steam_module, "STEAM_ROOT", root)
        _make_localconfig(root, "1001", "12345", "FOO=bar BAZ=qux %command%")
        result = get_steam_launch_env("12345")
        assert result == {"FOO": "bar", "BAZ": "qux"}

    def test_stops_at_command(self, tmp_path, monkeypatch):
        root = _make_steam_root(tmp_path)
        monkeypatch.setattr(steam_module, "STEAM_ROOT", root)
        _make_localconfig(root, "1001", "12345", "FOO=bar %command% AFTER=nope")
        result = get_steam_launch_env("12345")
        assert "AFTER" not in result
        assert result.get("FOO") == "bar"

    def test_no_launch_options_returns_empty(self, tmp_path, monkeypatch):
        root = _make_steam_root(tmp_path)
        monkeypatch.setattr(steam_module, "STEAM_ROOT", root)
        assert get_steam_launch_env("99999") == {}

    def test_no_steam_root_returns_empty(self, monkeypatch):
        monkeypatch.setattr(steam_module, "STEAM_ROOT", None)
        assert get_steam_launch_env("12345") == {}

    def test_skips_non_env_tokens(self, tmp_path, monkeypatch):
        root = _make_steam_root(tmp_path)
        monkeypatch.setattr(steam_module, "STEAM_ROOT", root)
        _make_localconfig(root, "1001", "12345", "mangohud FOO=bar %command%")
        result = get_steam_launch_env("12345")
        assert "mangohud" not in result


class TestGetSteamLaunchWrappers:
    def test_extracts_wrapper(self, tmp_path, monkeypatch):
        root = _make_steam_root(tmp_path)
        monkeypatch.setattr(steam_module, "STEAM_ROOT", root)
        _make_localconfig(root, "1001", "12345", "mangohud gamescope %command%")
        result = get_steam_launch_wrappers("12345")
        assert "mangohud" in result
        assert "gamescope" in result

    def test_skips_env_before_wrapper(self, tmp_path, monkeypatch):
        root = _make_steam_root(tmp_path)
        monkeypatch.setattr(steam_module, "STEAM_ROOT", root)
        _make_localconfig(root, "1001", "12345", "FOO=bar mangohud %command%")
        result = get_steam_launch_wrappers("12345")
        assert "FOO" not in result
        assert "mangohud" in result

    def test_no_command_returns_empty(self, tmp_path, monkeypatch):
        root = _make_steam_root(tmp_path)
        monkeypatch.setattr(steam_module, "STEAM_ROOT", root)
        _make_localconfig(root, "1001", "12345", "mangohud")
        assert get_steam_launch_wrappers("12345") == ""

    def test_no_steam_root_returns_empty(self, monkeypatch):
        monkeypatch.setattr(steam_module, "STEAM_ROOT", None)
        assert get_steam_launch_wrappers("12345") == ""


class TestGetSteamLaunchArgs:
    def test_args_after_command(self, tmp_path, monkeypatch):
        root = _make_steam_root(tmp_path)
        monkeypatch.setattr(steam_module, "STEAM_ROOT", root)
        _make_localconfig(root, "1001", "12345", "%command% --windowed --width 1920")
        result = get_steam_launch_args("12345")
        assert result == "--windowed --width 1920"

    def test_no_command_returns_full_string(self, tmp_path, monkeypatch):
        root = _make_steam_root(tmp_path)
        monkeypatch.setattr(steam_module, "STEAM_ROOT", root)
        _make_localconfig(root, "1001", "12345", "--some-arg")
        result = get_steam_launch_args("12345")
        assert result == "--some-arg"

    def test_empty_after_command(self, tmp_path, monkeypatch):
        root = _make_steam_root(tmp_path)
        monkeypatch.setattr(steam_module, "STEAM_ROOT", root)
        _make_localconfig(root, "1001", "12345", "FOO=bar %command%")
        assert get_steam_launch_args("12345") == ""

    def test_no_steam_root_returns_empty(self, monkeypatch):
        monkeypatch.setattr(steam_module, "STEAM_ROOT", None)
        assert get_steam_launch_args("12345") == ""
