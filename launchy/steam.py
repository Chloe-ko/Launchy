import os
import re
from pathlib import Path
from typing import Optional


def _find_steam_root() -> Optional[Path]:
    for p in [
        Path.home() / ".steam" / "root",
        Path.home() / ".steam" / "steam",
        Path.home() / ".local" / "share" / "Steam",
        Path("/usr/share/steam"),
    ]:
        if (p / "steamapps").exists():
            return p
    return None


STEAM_ROOT: Optional[Path] = _find_steam_root()


# ---------------------------------------------------------------------------
# Game info
# ---------------------------------------------------------------------------

def get_game_info(appid: str) -> dict:
    info = {
        "appid": appid,
        "name": f"App {appid}",
        "image_path": None,
        "game_dir": None,
        "prefix": os.environ.get("STEAM_COMPAT_DATA_PATH"),
    }

    if STEAM_ROOT:
        manifest = _find_manifest(appid)
        if manifest:
            name = _acf_field(manifest, "name")
            install_dir = _acf_field(manifest, "installdir")
            if name:
                info["name"] = name
            if install_dir:
                # Derive game_dir from the manifest's own library, not STEAM_ROOT
                d = manifest.parent / "common" / install_dir
                if d.exists():
                    info["game_dir"] = str(d)
            # Prefix lives next to the steamapps dir that holds the manifest
            compatdata = manifest.parent / "compatdata" / appid
            if compatdata.exists():
                info["prefix"] = str(compatdata)

        img = _header_image(appid)
        if img:
            info["image_path"] = str(img)

    return info


def _find_manifest(appid: str) -> Optional[Path]:
    if not STEAM_ROOT:
        return None
    main = STEAM_ROOT / "steamapps" / f"appmanifest_{appid}.acf"
    if main.exists():
        return main
    lf = STEAM_ROOT / "steamapps" / "libraryfolders.vdf"
    if lf.exists():
        for m in re.finditer(r'"path"\s+"([^"]+)"', lf.read_text(errors="replace")):
            p = Path(m.group(1)) / "steamapps" / f"appmanifest_{appid}.acf"
            if p.exists():
                return p
    return None


def _acf_field(path: Path, field: str) -> Optional[str]:
    try:
        m = re.search(
            rf'"{re.escape(field)}"\s+"([^"]*)"',
            path.read_text(errors="replace"),
            re.IGNORECASE,
        )
        return m.group(1) if m else None
    except Exception:
        return None


def _header_image(appid: str) -> Optional[Path]:
    if not STEAM_ROOT:
        return None
    cache = STEAM_ROOT / "appcache" / "librarycache"

    # New format: librarycache/<appid>/<hash>/<name>.jpg
    appid_dir = cache / appid
    if appid_dir.is_dir():
        for name in ("library_header.jpg", "library_hero.jpg", "library_capsule.jpg"):
            for sub in appid_dir.iterdir():
                candidate = sub / name
                if candidate.exists():
                    return candidate

    # Old flat format: librarycache/<appid>_header.jpg
    for name in (f"{appid}_header.jpg", f"{appid}_header.png", f"{appid}_library_hero.jpg"):
        p = cache / name
        if p.exists():
            return p

    return None


# ---------------------------------------------------------------------------
# Proton / compat-tool discovery
# ---------------------------------------------------------------------------

def get_available_proton_versions() -> list:
    """Return [{"name": display_name, "id": internal_id, "binary": path_or_None}, ...]."""
    versions = [{"name": "Steam Default", "id": "", "binary": None}]
    if not STEAM_ROOT:
        return versions

    seen_ids: set = set()

    def _add(tool_dir: Path, vdf_path: Path):
        iname = _vdf_field(vdf_path, "internal_name") or tool_dir.name
        dname = _vdf_field(vdf_path, "display_name") or tool_dir.name
        if iname.lower() == "launchy" or iname in seen_ids:
            return
        seen_ids.add(iname)
        binary = _proton_binary(tool_dir)
        versions.append({"name": dname, "id": iname, "binary": binary})

    common = STEAM_ROOT / "steamapps" / "common"
    if common.exists():
        for d in sorted(common.iterdir()):
            if d.is_dir() and d.name.startswith("Proton"):
                vdf = d / "compatibilitytool.vdf"
                if vdf.exists():
                    _add(d, vdf)

    compat = STEAM_ROOT / "compatibilitytools.d"
    if compat.exists():
        for d in sorted(compat.iterdir()):
            if d.is_dir():
                vdf = d / "compatibilitytool.vdf"
                if vdf.exists():
                    _add(d, vdf)

    return versions


def find_proton_binary(proton_id: str) -> Optional[str]:
    """Return the path to the 'proton' script for the given internal tool ID."""
    if not proton_id:
        return None
    for v in get_available_proton_versions():
        if v["id"] == proton_id:
            return v["binary"]
    return None


def find_steam_runtime_entry_point() -> Optional[str]:
    """Find the SteamLinuxRuntime _v2-entry-point across all Steam library folders.

    Prefers Sniper (used by Proton 7+), falls back to Soldier.
    """
    for runtime in ("SteamLinuxRuntime_sniper", "SteamLinuxRuntime_soldier"):
        ep = _find_in_all_libraries(f"common/{runtime}/_v2-entry-point")
        if ep:
            return str(ep)
    return None


def get_proc_launch_env(appid: str) -> dict:
    """Return env vars added by Steam specifically for this game launch.

    Strategy: find the Steam client process (parent of the reaper process that
    launched us), read its environment as a baseline, then return vars that are
    new or changed in our own environment — minus known Steam infrastructure
    prefixes. What remains is what the user set in launch options (including via
    client mods like Millennium that inject global launch options).
    Returns {} when called outside a Steam context.
    """
    steam_pid = _find_steam_client_pid()
    if not steam_pid:
        return {}
    try:
        steam_env = _read_proc_environ(steam_pid)
    except Exception:
        return {}

    _INFRA_PREFIXES = ("STEAM_", "LD_", "PRESSURE_VESSEL_")
    _INFRA_VARS = frozenset({
        "SteamAppId", "SteamGameId", "SteamClientLaunch",
        "DBUS_SESSION_BUS_ADDRESS",
    })

    result = {}
    for k, v in os.environ.items():
        if k in _INFRA_VARS or any(k.startswith(p) for p in _INFRA_PREFIXES):
            continue
        if k not in steam_env or steam_env[k] != v:
            result[k] = v
    return result


def _find_steam_client_pid() -> int:
    """Walk up the process tree to find the Steam client PID (parent of reaper)."""
    import logging
    pid = os.getpid()
    visited: set = set()
    while pid and pid not in visited:
        visited.add(pid)
        try:
            parts = (Path(f"/proc/{pid}/cmdline")
                     .read_bytes().decode(errors="replace").split("\0"))
            parts = [p for p in parts if p]
            logging.debug("proc walk pid=%s cmdline=%s", pid, parts[:4])
            if parts and os.path.basename(parts[0]) == "reaper" and "SteamLaunch" in parts:
                m = re.search(r"^PPid:\s+(\d+)",
                              Path(f"/proc/{pid}/status").read_text(), re.MULTILINE)
                if m:
                    return int(m.group(1))
                return 0
            m = re.search(r"^PPid:\s+(\d+)",
                          Path(f"/proc/{pid}/status").read_text(), re.MULTILINE)
            pid = int(m.group(1)) if m else 0
        except Exception:
            break
    return 0


def _read_proc_environ(pid: int) -> dict:
    data = Path(f"/proc/{pid}/environ").read_bytes()
    env: dict = {}
    for entry in data.split(b"\0"):
        if b"=" in entry:
            k, _, v = entry.partition(b"=")
            env[k.decode(errors="replace")] = v.decode(errors="replace")
    return env


def _find_in_all_libraries(relative: str) -> Optional[Path]:
    if not STEAM_ROOT:
        return None
    roots = [STEAM_ROOT / "steamapps"]
    lf = STEAM_ROOT / "steamapps" / "libraryfolders.vdf"
    if lf.exists():
        for m in re.finditer(r'"path"\s+"([^"]+)"', lf.read_text(errors="replace")):
            roots.append(Path(m.group(1)) / "steamapps")
    for r in roots:
        p = r / relative
        if p.exists() and os.access(p, os.X_OK):
            return p
    return None


def _proton_binary(tool_dir: Path) -> Optional[str]:
    candidate = tool_dir / "proton"
    if candidate.exists() and os.access(candidate, os.X_OK):
        return str(candidate)
    return None


def _vdf_field(path: Path, field: str) -> Optional[str]:
    try:
        m = re.search(rf'"{re.escape(field)}"\s+"([^"]+)"', path.read_text(errors="replace"))
        return m.group(1) if m else None
    except Exception:
        return None


