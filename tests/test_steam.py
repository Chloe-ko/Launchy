import pytest
from pathlib import Path
import launchy.steam as steam_module
from launchy.steam import (
    _acf_field,
    _find_steam_root,
    _header_only_image,
    _header_image,
    select_best_proton_id,
    get_steam_launch_env,
    get_steam_launch_wrappers,
    get_steam_launch_args,
)


def _v(name, vid=None, binary="/usr/bin/proton"):
    return {"name": name, "id": vid or name, "binary": binary}


class TestSelectBestProtonId:
    def test_empty_list_returns_empty(self):
        assert select_best_proton_id([]) == ""

    def test_no_binary_skipped(self):
        assert select_best_proton_id([_v("Proton 9", binary=None)]) == ""

    def test_prefers_cachyos_latest(self):
        versions = [_v("Proton 9"), _v("GE-Proton9"), _v("CachyOS-Proton Latest")]
        assert select_best_proton_id(versions) == "CachyOS-Proton Latest"

    def test_prefers_cachyos_over_ge_latest(self):
        versions = [_v("GE-Proton Latest"), _v("CachyOS Proton")]
        assert select_best_proton_id(versions) == "CachyOS Proton"

    def test_prefers_ge_latest_over_plain_ge(self):
        versions = [_v("GE-Proton9"), _v("GE-Proton Latest")]
        assert select_best_proton_id(versions) == "GE-Proton Latest"

    def test_prefers_ge_over_experimental(self):
        versions = [_v("Proton Experimental"), _v("GE-Proton9")]
        assert select_best_proton_id(versions) == "GE-Proton9"

    def test_prefers_experimental_over_numbered(self):
        versions = [_v("Proton 9"), _v("Proton Experimental")]
        assert select_best_proton_id(versions) == "Proton Experimental"

    def test_falls_back_to_numbered(self):
        versions = [_v("Proton 9"), _v("Proton 8")]
        assert select_best_proton_id(versions) == "Proton 9"

    def test_falls_back_to_any(self):
        versions = [_v("My Custom Tool", vid="custom-tool")]
        assert select_best_proton_id(versions) == "custom-tool"

    def test_skips_no_binary_prefers_next(self):
        versions = [
            _v("CachyOS-Proton Latest", binary=None),
            _v("Proton 9"),
        ]
        assert select_best_proton_id(versions) == "Proton 9"

    def test_launchy_itself_excluded(self):
        versions = [
            {"name": "Launchy", "id": "launchy", "binary": "/usr/bin/launchy"},
            _v("Proton 9"),
        ]
        # launchy is filtered by get_available_proton_versions, not select_best
        # so here it would be treated as any other candidate
        result = select_best_proton_id([_v("Proton 9")])
        assert result == "Proton 9"


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


class TestVdfEscapedQuotes:
    """LaunchOptions values with VDF-escaped quotes (e.g. WINEDLLOVERRIDES=\"...\")."""

    def test_env_with_quoted_value(self, tmp_path, monkeypatch):
        root = _make_steam_root(tmp_path)
        monkeypatch.setattr(steam_module, "STEAM_ROOT", root)
        # VDF stores: "LaunchOptions" "WINEDLLOVERRIDES=\"winmm.dll=n,b\" %command%"
        _make_localconfig(root, "1001", "12345",
                          r'WINEDLLOVERRIDES=\"winmm.dll=n,b\" %command%')
        result = get_steam_launch_env("12345")
        assert result == {"WINEDLLOVERRIDES": "winmm.dll=n,b"}

    def test_env_with_quoted_value_and_wrappers(self, tmp_path, monkeypatch):
        root = _make_steam_root(tmp_path)
        monkeypatch.setattr(steam_module, "STEAM_ROOT", root)
        _make_localconfig(root, "1001", "12345",
                          r'WINEDLLOVERRIDES=\"winmm.dll=n,b\" PROTON_USE_NTSYNC=1 mangohud game-performance %command%')
        env = get_steam_launch_env("12345")
        assert env["WINEDLLOVERRIDES"] == "winmm.dll=n,b"
        assert env["PROTON_USE_NTSYNC"] == "1"
        assert "mangohud" not in env

    def test_wrappers_with_preceding_quoted_env(self, tmp_path, monkeypatch):
        root = _make_steam_root(tmp_path)
        monkeypatch.setattr(steam_module, "STEAM_ROOT", root)
        _make_localconfig(root, "1001", "12345",
                          r'WINEDLLOVERRIDES=\"winmm.dll=n,b\" mangohud game-performance %command%')
        result = get_steam_launch_wrappers("12345")
        assert "mangohud" in result
        assert "game-performance" in result
        assert "WINEDLLOVERRIDES" not in result

    def test_multiple_escaped_env_vars(self, tmp_path, monkeypatch):
        root = _make_steam_root(tmp_path)
        monkeypatch.setattr(steam_module, "STEAM_ROOT", root)
        _make_localconfig(root, "1001", "12345",
                          r'FOO=\"a=b\" BAR=\"c,d\" %command%')
        result = get_steam_launch_env("12345")
        assert result == {"FOO": "a=b", "BAR": "c,d"}


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


class TestFindSteamRoot:
    def test_finds_native_steam(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        native = tmp_path / ".local" / "share" / "Steam"
        (native / "steamapps").mkdir(parents=True)
        assert _find_steam_root() == native

    def test_finds_flatpak_steam(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        flatpak = tmp_path / ".var" / "app" / "com.valvesoftware.Steam" / "data" / "Steam"
        (flatpak / "steamapps").mkdir(parents=True)
        assert _find_steam_root() == flatpak

    def test_native_steam_preferred_over_flatpak(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        native = tmp_path / ".local" / "share" / "Steam"
        (native / "steamapps").mkdir(parents=True)
        flatpak = tmp_path / ".var" / "app" / "com.valvesoftware.Steam" / "data" / "Steam"
        (flatpak / "steamapps").mkdir(parents=True)
        assert _find_steam_root() == native

    def test_returns_none_when_nothing_found(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        assert _find_steam_root() is None
