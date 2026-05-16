import stat
from pathlib import Path

import launchy.install as install_module
from launchy.install import _find_all_steam_roots, _flatpak_wrapper_script, _wrapper_script, _runner_script


class TestFindAllSteamRoots:
    def test_finds_native_steam(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        native = tmp_path / ".local" / "share" / "Steam"
        (native / "steamapps").mkdir(parents=True)
        assert native in _find_all_steam_roots()

    def test_finds_flatpak_steam(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        flatpak = tmp_path / ".var" / "app" / "com.valvesoftware.Steam" / "data" / "Steam"
        (flatpak / "steamapps").mkdir(parents=True)
        assert flatpak in _find_all_steam_roots()

    def test_finds_both_when_both_present(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        native = tmp_path / ".local" / "share" / "Steam"
        (native / "steamapps").mkdir(parents=True)
        flatpak = tmp_path / ".var" / "app" / "com.valvesoftware.Steam" / "data" / "Steam"
        (flatpak / "steamapps").mkdir(parents=True)
        roots = _find_all_steam_roots()
        assert native in roots
        assert flatpak in roots
        assert len(roots) == 2

    def test_empty_when_none_found(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        assert _find_all_steam_roots() == []

    def test_deduplicates_symlinked_paths(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        real = tmp_path / ".local" / "share" / "Steam"
        (real / "steamapps").mkdir(parents=True)
        steam_dir = tmp_path / ".steam"
        steam_dir.mkdir()
        (steam_dir / "root").symlink_to(real)
        roots = _find_all_steam_roots()
        assert len(roots) == 1


class TestWrapperScripts:
    def test_native_wrapper_contains_binary_path(self):
        script = _wrapper_script("/usr/local/bin/launchy")
        assert '"/usr/local/bin/launchy"' in script
        assert script.startswith("#!/usr/bin/env bash")
        assert '"$@"' in script

    def test_runner_script_contains_runner_path(self):
        runner = Path("/home/user/.local/share/launchy/runner")
        script = _runner_script(runner)
        assert str(runner) in script
        assert script.startswith("#!/usr/bin/env bash")
        assert '"$@"' in script

    def test_flatpak_wrapper_uses_flatpak_spawn(self):
        script = _flatpak_wrapper_script("io.github.chloe_ko.Launchy")
        assert "flatpak-spawn --host" in script
        assert "flatpak run" in script
        assert "io.github.chloe_ko.Launchy" in script
        assert "--command=launchy" in script
        assert '"$@"' in script

    def test_flatpak_wrapper_starts_with_shebang(self):
        script = _flatpak_wrapper_script("io.github.chloe_ko.Launchy")
        assert script.startswith("#!/usr/bin/env bash")


class TestInstallCompatTool:
    def test_installs_vdf_files(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("FLATPAK_ID", raising=False)
        native = tmp_path / ".local" / "share" / "Steam"
        (native / "steamapps").mkdir(parents=True)
        monkeypatch.setattr(install_module, "_find_all_steam_roots", lambda: [native])
        import shutil
        monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/launchy")

        install_module.install_compat_tool()

        target = native / "compatibilitytools.d" / "launchy"
        assert (target / "compatibilitytool.vdf").exists()
        assert (target / "toolmanifest.vdf").exists()
        launcher = target / "launchy"
        assert launcher.exists()
        assert launcher.stat().st_mode & stat.S_IEXEC

    def test_native_install_writes_binary_wrapper(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("FLATPAK_ID", raising=False)
        native = tmp_path / ".local" / "share" / "Steam"
        (native / "steamapps").mkdir(parents=True)
        monkeypatch.setattr(install_module, "_find_all_steam_roots", lambda: [native])
        import shutil
        monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/launchy")

        install_module.install_compat_tool()

        script = (native / "compatibilitytools.d" / "launchy" / "launchy").read_text()
        assert "flatpak-spawn" not in script
        assert "launchy" in script

    def test_flatpak_install_copies_runner_and_writes_wrapper(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("FLATPAK_ID", "io.github.chloe_ko.Launchy")
        native = tmp_path / ".local" / "share" / "Steam"
        (native / "steamapps").mkdir(parents=True)
        monkeypatch.setattr(install_module, "_find_all_steam_roots", lambda: [native])

        # Provide a fake bundled runner
        fake_runner_src = tmp_path / "fake_app_runner"
        fake_runner_src.write_bytes(b"\x7fELF fake binary")
        monkeypatch.setattr(install_module, "_FLATPAK_RUNNER_SRC", fake_runner_src)

        runner_dest = tmp_path / ".local" / "share" / "launchy" / "runner"
        monkeypatch.setattr(install_module, "_RUNNER_DEST", runner_dest)

        install_module.install_compat_tool()

        # Runner should be copied to home
        assert runner_dest.exists()
        assert runner_dest.stat().st_mode & stat.S_IEXEC

        # Wrapper should point to runner, not use flatpak-spawn
        script = (native / "compatibilitytools.d" / "launchy" / "launchy").read_text()
        assert "flatpak-spawn" not in script
        assert str(runner_dest) in script

    def test_flatpak_install_falls_back_to_flatpak_spawn_when_no_runner(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("FLATPAK_ID", "io.github.chloe_ko.Launchy")
        native = tmp_path / ".local" / "share" / "Steam"
        (native / "steamapps").mkdir(parents=True)
        monkeypatch.setattr(install_module, "_find_all_steam_roots", lambda: [native])

        # No runner bundle present
        missing = tmp_path / "nonexistent_runner"
        monkeypatch.setattr(install_module, "_FLATPAK_RUNNER_SRC", missing)

        install_module.install_compat_tool()

        script = (native / "compatibilitytools.d" / "launchy" / "launchy").read_text()
        assert "flatpak-spawn --host" in script
        assert "io.github.chloe_ko.Launchy" in script

    def test_installs_into_all_roots(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("FLATPAK_ID", raising=False)
        native = tmp_path / ".local" / "share" / "Steam"
        (native / "steamapps").mkdir(parents=True)
        flatpak = tmp_path / ".var" / "app" / "com.valvesoftware.Steam" / "data" / "Steam"
        (flatpak / "steamapps").mkdir(parents=True)
        monkeypatch.setattr(install_module, "_find_all_steam_roots", lambda: [native, flatpak])
        import shutil
        monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/launchy")

        install_module.install_compat_tool()

        assert (native / "compatibilitytools.d" / "launchy" / "launchy").exists()
        assert (flatpak / "compatibilitytools.d" / "launchy" / "launchy").exists()


class TestUninstallCompatTool:
    def test_removes_compat_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        native = tmp_path / ".local" / "share" / "Steam"
        target = native / "compatibilitytools.d" / "launchy"
        target.mkdir(parents=True)
        (target / "launchy").write_text("#!/bin/bash\n")
        monkeypatch.setattr(install_module, "_find_all_steam_roots", lambda: [native])
        monkeypatch.setattr(install_module, "_RUNNER_DEST", tmp_path / "nonexistent")

        install_module.uninstall_compat_tool()

        assert not target.exists()

    def test_removes_runner_binary(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(install_module, "_find_all_steam_roots", lambda: [])
        runner = tmp_path / "runner"
        runner.write_bytes(b"binary")
        monkeypatch.setattr(install_module, "_RUNNER_DEST", runner)

        install_module.uninstall_compat_tool()

        assert not runner.exists()

    def test_removes_from_all_roots(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        native = tmp_path / ".local" / "share" / "Steam"
        flatpak = tmp_path / ".var" / "app" / "com.valvesoftware.Steam" / "data" / "Steam"
        for root in (native, flatpak):
            t = root / "compatibilitytools.d" / "launchy"
            t.mkdir(parents=True)
            (t / "launchy").write_text("#!/bin/bash\n")
        monkeypatch.setattr(install_module, "_find_all_steam_roots", lambda: [native, flatpak])
        monkeypatch.setattr(install_module, "_RUNNER_DEST", tmp_path / "nonexistent")

        install_module.uninstall_compat_tool()

        assert not (native / "compatibilitytools.d" / "launchy").exists()
        assert not (flatpak / "compatibilitytools.d" / "launchy").exists()
