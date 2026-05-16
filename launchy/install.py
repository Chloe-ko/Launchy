"""Install Launchy as a Steam compatibility tool."""

import os
import shutil
import stat
import sys
from pathlib import Path

_COMPAT_VDF = """\
"compatibilitytools"
{
  "compat_tools"
  {
    "launchy"
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
  "commandline"                    "/launchy run"
  "commandline_waitforexitandrun"  "/launchy waitforexitandrun"
  "commandline_runinprefix"        "/launchy runinprefix"
  "commandline_getcompatpath"      "/launchy getcompatpath"
  "commandline_getnativepath"      "/launchy getnativepath"
}
"""


def _wrapper_script(launchy_bin: str) -> str:
    return f'#!/usr/bin/env bash\nexec "{launchy_bin}" "$@"\n'


def _flatpak_wrapper_script(flatpak_id: str) -> str:
    # flatpak-spawn --host escapes Steam's Flatpak sandbox to run launchy on the host.
    return (
        "#!/usr/bin/env bash\n"
        f'exec flatpak-spawn --host flatpak run --command=launchy {flatpak_id} "$@"\n'
    )


def install_compat_tool():
    flatpak_id = os.environ.get("FLATPAK_ID", "")

    if not flatpak_id:
        launchy_bin = shutil.which("launchy")
        if not launchy_bin:
            print("Error: 'launchy' not found on PATH. Run 'make install' first.", file=sys.stderr)
            sys.exit(1)
        launchy_bin = str(Path(launchy_bin).resolve())
    else:
        launchy_bin = None

    roots = _find_all_steam_roots()
    if not roots:
        print("Error: Steam installation not found.", file=sys.stderr)
        sys.exit(1)

    for root in roots:
        target = root / "compatibilitytools.d" / "launchy"
        target.mkdir(parents=True, exist_ok=True)

        (target / "compatibilitytool.vdf").write_text(_COMPAT_VDF, encoding="utf-8")
        (target / "toolmanifest.vdf").write_text(_TOOL_MANIFEST, encoding="utf-8")

        launcher = target / "launchy"
        script = _flatpak_wrapper_script(flatpak_id) if flatpak_id else _wrapper_script(launchy_bin)
        launcher.write_text(script, encoding="utf-8")
        launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

        if flatpak_id:
            print(f"Using Flatpak:  {flatpak_id}")
        else:
            print(f"Using binary:   {launchy_bin}")
        print(f"Installed to:   {target}")

    print("Restart Steam, then select 'Launchy' as the compatibility tool for a game.")


def uninstall_compat_tool():
    roots = _find_all_steam_roots()
    if not roots:
        print("Steam installation not found.", file=sys.stderr)
        return
    removed_any = False
    for root in roots:
        target = root / "compatibilitytools.d" / "launchy"
        if target.exists():
            shutil.rmtree(target)
            print(f"Removed {target}")
            removed_any = True
    if not removed_any:
        print("Launchy compat tool not installed.")


def _find_all_steam_roots() -> list[Path]:
    """Return all found Steam root directories, deduplicating symlinked paths."""
    candidates = [
        Path.home() / ".steam" / "root",
        Path.home() / ".steam" / "steam",
        Path.home() / ".local" / "share" / "Steam",
        Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / "data" / "Steam",
    ]
    seen: set[str] = set()
    roots: list[Path] = []
    for p in candidates:
        if not (p / "steamapps").exists():
            continue
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            roots.append(p)
    return roots
