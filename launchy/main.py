import logging
import os
import sys
from pathlib import Path

_LOG_FILE = Path.home() / ".local" / "share" / "launchy" / "launchy.log"


def _setup_log():
    _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(_LOG_FILE),
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(message)s",
        force=True,
    )


def _ensure_global_defaults():
    from launchy.config import get_global_config, save_global_config
    cfg = get_global_config()
    if cfg.get("general", {}).get("proton"):
        return
    from launchy.steam import get_available_proton_versions, select_best_proton_id
    best = select_best_proton_id(get_available_proton_versions())
    if best:
        if "general" not in cfg:
            cfg["general"] = {}
        cfg["general"]["proton"] = best
        save_global_config(cfg)
        logging.debug("auto-selected proton: %s", best)


def main():
    _setup_log()
    args = sys.argv[1:]
    logging.debug("argv: %s", sys.argv)
    logging.debug("DISPLAY=%s WAYLAND_DISPLAY=%s XDG_RUNTIME_DIR=%s SteamAppId=%s",
                  os.environ.get("DISPLAY"), os.environ.get("WAYLAND_DISPLAY"),
                  os.environ.get("XDG_RUNTIME_DIR"), os.environ.get("SteamAppId"))
    _ensure_global_defaults()

    if not args or args[0] in ("-h", "--help"):
        _print_help()
        return

    if args[0] in ("install", "install-compat-tool"):
        from launchy.install import install_compat_tool
        install_compat_tool()
        return

    if args[0] in ("uninstall", "uninstall-compat-tool"):
        from launchy.install import uninstall_compat_tool
        uninstall_compat_tool()
        return

    if args[0] == "settings":
        appid = args[1] if len(args) >= 2 else ""
        _open_settings(appid or "0", is_global=not bool(appid))
        return

    # Internal subcommand: GTK UI runs here, inside a clean subprocess
    if args[0] == "--run-ui" and len(args) >= 2:
        result = _run_ui_inprocess(args[1])
        sys.exit(0 if result == "launch" else 1)

    if args[0] == "--show-error" and len(args) >= 2:
        _show_error_inprocess(args[1])
        return

    verb = args[0]
    game_cmd = args[1:]
    appid = os.environ.get("SteamAppId", "0")

    # Passthrough verbs that should not trigger UI
    if verb in ("runinprefix", "getcompatpath", "getnativepath") or not game_cmd:
        if game_cmd:
            os.execvp(game_cmd[0], game_cmd)
        return

    has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))

    from launchy.steam import get_available_proton_versions
    if not get_available_proton_versions():
        msg = "No Proton version found. Please install Proton via Steam first."
        logging.error("no Proton versions found, aborting launch")
        print(f"Error: {msg}", file=sys.stderr)
        if has_display:
            _show_error_subprocess(msg)
        sys.exit(1)
    # Skip UI for appid "0" — pre-game housekeeping calls (d3ddriverquery64, etc.)
    show_ui = has_display and appid != "0"

    result = _run_ui_subprocess(appid) if show_ui else "launch"

    if result == "cancel":
        sys.exit(0)

    from launchy.config import get_merged_config
    from launchy.steam import find_proton_binary, find_steam_runtime_entry_point
    config = get_merged_config(appid)

    env = os.environ.copy()
    env.update(config.get("env", {}))

    proton_id = config.get("general", {}).get("proton", "")
    proton_bin = find_proton_binary(proton_id) if proton_id else None
    if not proton_bin:
        proton_bin = _fallback_proton_binary()

    pre = config.get("wrappers", [])
    args = config.get("args", [])

    wrapper_tokens: list[str] = []
    for w in pre:
        wrapper_tokens.extend(w.split())

    final_cmd: list[str] = []
    if proton_bin:
        proton_dir = Path(proton_bin).parent
        runtime = find_steam_runtime_entry_point(proton_dir)
        logging.debug("runtime entry point: %s", runtime)
        if runtime:
            final_cmd.extend(wrapper_tokens)
            final_cmd.extend([runtime, "--"])
        else:
            final_cmd.extend(wrapper_tokens)
        final_cmd.extend([proton_bin, verb])
    else:
        # Native Linux game — wrappers run outside any container
        final_cmd.extend(wrapper_tokens)

    final_cmd.extend(game_cmd)
    final_cmd.extend(args)

    if final_cmd:
        os.execvpe(final_cmd[0], final_cmd, env)


def _fallback_proton_binary() -> str | None:
    from launchy.steam import get_available_proton_versions, select_best_proton_id, find_proton_binary
    versions = get_available_proton_versions()
    best_id = select_best_proton_id(versions)
    return find_proton_binary(best_id) if best_id else None


def _show_error_subprocess(message: str):
    import subprocess
    env = {k: os.environ[k] for k in _SUBPROCESS_KEEP if k in os.environ}
    try:
        subprocess.run(
            [sys.executable, "-m", "launchy", "--show-error", message],
            env=env,
        )
    except Exception as e:
        logging.warning("could not show error dialog: %s", e)


def _show_error_inprocess(message: str):
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw
    except (ImportError, ValueError) as e:
        logging.warning("GTK unavailable for error dialog: %s", e)
        return

    app = Adw.Application(application_id="io.github.chloe_ko.Launchy.error")

    def on_activate(_app):
        dialog = Adw.AlertDialog(heading="No Proton Found", body=message)
        dialog.add_response("ok", "OK")
        dialog.connect("response", lambda d, r: _app.quit())
        dialog.present(None)

    app.connect("activate", on_activate)
    app.run([])


def _open_settings(appid: str, is_global: bool):
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
    except (ImportError, ValueError) as e:
        print(f"Error: GTK4/Adwaita unavailable: {e}", file=sys.stderr)
        sys.exit(1)
    from launchy.ui.settings_window import SettingsApplication
    app = SettingsApplication(appid=appid, is_global=is_global)
    sys.exit(app.run(sys.argv[:1]))


_SUBPROCESS_KEEP = frozenset({
    "HOME", "USER", "LOGNAME", "PATH",
    "DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR",
    "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CONFIG_DIRS", "XDG_DATA_DIRS",
    "DBUS_SESSION_BUS_ADDRESS",
    "LANG", "LANGUAGE", "LC_ALL", "LC_MESSAGES", "LC_CTYPE",
})


def _run_ui_subprocess(appid: str) -> str:
    """Spawn the GTK UI in a subprocess with a minimal clean environment.

    Steam sets dozens of env vars (LD_LIBRARY_PATH, GTK_PATH, GDK_MODULE_DIR,
    STEAM_RUNTIME, …) that collectively corrupt GTK4 GType registration.
    An allowlist is safer than trying to strip individual variables.
    """
    import subprocess

    env = {k: os.environ[k] for k in _SUBPROCESS_KEEP if k in os.environ}

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "launchy", "--run-ui", appid],
            env=env, stderr=subprocess.PIPE,
        )
        if proc.stderr:
            logging.debug("UI subprocess stderr: %s", proc.stderr.decode(errors="replace").strip())
        logging.debug("UI subprocess exited with code %s", proc.returncode)
        return "launch" if proc.returncode == 0 else "cancel"
    except Exception as e:
        logging.exception("UI subprocess failed: %s — launching without UI", e)
        return "launch"


def _run_ui_inprocess(appid: str) -> str:
    """Run the GTK UI directly. Called only from the clean subprocess."""
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
    except (ImportError, ValueError) as e:
        logging.warning("GTK4/Adwaita unavailable: %s — launching without UI", e)
        return "launch"

    try:
        from launchy.steam import get_game_info
        from launchy.config import get_merged_config, bootstrap_game_config, get_game_config
        from launchy.ui.launch_window import LaunchApplication

        bootstrap_game_config(appid)

        if get_game_config(appid).get("general", {}).get("skip_countdown", False):
            return "launch"

        game_info = get_game_info(appid)
        config = get_merged_config(appid)

        app = LaunchApplication(appid=appid, game_cmd=[], game_info=game_info, config=config)
        exit_code = app.run(sys.argv[:1])
        logging.debug("GTK app exited with code %s, result=%s, window_shown=%s",
                      exit_code, app.result, app.window_shown)

        if not app.window_shown:
            logging.warning("Window was never shown — falling through to launch")
            return "launch"

        return app.result
    except Exception as e:
        logging.exception("UI error: %s — launching without UI", e)
        return "launch"


def _print_help():
    print(
        "Launchy — Steam compatibility tool wrapper\n"
        "\n"
        "Usage:\n"
        "  launchy install              Install as Steam compat tool\n"
        "  launchy uninstall            Remove Steam compat tool entry\n"
        "  launchy settings             Open global settings\n"
        "  launchy settings <appid>     Open per-game settings\n"
        "  launchy <verb> [cmd...]      Called automatically by Steam\n"
    )
