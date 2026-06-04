"""Install Launchy as a Steam compatibility tool."""

import shutil
import stat
import sys
from pathlib import Path

_COMPAT_VDF = """\
"compatibilitytools"
{
  "compat_tools"
  {
    "Proton-Launchy"
    {
      "install_path" "."
      "display_name"  "Launchy"
      "from_oslist"   "windows"
      "to_oslist"     "linux"
    }
  }
}
"""

# toolmanifest.vdf is what Steam actually reads to find the commandline.
# Modelled after STL's manifest — explicit verbs, no Steam Runtime dependency.
_TOOL_MANIFEST = """\
"manifest"
{
  "version"                  "2"
  "commandline"              "/launchy %verb%"
  "use_sessions"             "1"
  "compatmanager_layer_name" "proton"
}
"""


def _wrapper_script(launchy_bin: str) -> str:
    return f'#!/usr/bin/env bash\nexec "{launchy_bin}" "$@"\n'


def install_compat_tool():
    launchy_bin = shutil.which("launchy")
    if not launchy_bin:
        print("Error: 'launchy' not found on PATH. Run 'make install' first.", file=sys.stderr)
        sys.exit(1)
    launchy_bin = str(Path(launchy_bin).resolve())

    steam_root = _find_steam_root()
    if not steam_root:
        print("Error: Steam installation not found.", file=sys.stderr)
        sys.exit(1)

    target = steam_root / "compatibilitytools.d" / "launchy"
    target.mkdir(parents=True, exist_ok=True)

    (target / "compatibilitytool.vdf").write_text(_COMPAT_VDF, encoding="utf-8")
    (target / "toolmanifest.vdf").write_text(_TOOL_MANIFEST, encoding="utf-8")

    launcher = target / "launchy"
    launcher.write_text(_wrapper_script(launchy_bin), encoding="utf-8")
    launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    print(f"Using binary:  {launchy_bin}")
    print(f"Installed to:  {target}")
    print("Restart Steam, then select 'Launchy' as the compatibility tool for a game.")


def uninstall_compat_tool():
    steam_root = _find_steam_root()
    if not steam_root:
        print("Steam installation not found.", file=sys.stderr)
        return
    target = steam_root / "compatibilitytools.d" / "launchy"
    if target.exists():
        shutil.rmtree(target)
        print(f"Removed {target}")
    else:
        print("Launchy compat tool not installed.")


def _find_steam_root():
    for p in [
        Path.home() / ".steam" / "root",
        Path.home() / ".steam" / "steam",
        Path.home() / ".local" / "share" / "Steam",
    ]:
        if (p / "steamapps").exists():
            return p
    return None
