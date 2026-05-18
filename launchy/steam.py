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

        header = _header_only_image(appid)
        if header:
            info["header_image_path"] = str(header)

        logo = _logo_image(appid)
        if logo:
            info["logo_path"] = str(logo)

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


def _logo_image(appid: str) -> Optional[Path]:
    if not STEAM_ROOT:
        return None
    cache = STEAM_ROOT / "appcache" / "librarycache"
    appid_dir = cache / appid
    if appid_dir.is_dir():
        candidate = appid_dir / "logo.png"
        if candidate.exists():
            return candidate
        for sub in appid_dir.iterdir():
            if sub.is_dir():
                candidate = sub / "logo.png"
                if candidate.exists():
                    return candidate
    return None


def _header_only_image(appid: str) -> Optional[Path]:
    """Return library_header.jpg specifically (not hero/capsule fallbacks)."""
    if not STEAM_ROOT:
        return None
    cache = STEAM_ROOT / "appcache" / "librarycache"
    appid_dir = cache / appid
    if appid_dir.is_dir():
        candidate = appid_dir / "library_header.jpg"
        if candidate.exists():
            return candidate
        for sub in appid_dir.iterdir():
            if sub.is_dir():
                candidate = sub / "library_header.jpg"
                if candidate.exists():
                    return candidate
    for name in (f"{appid}_header.jpg", f"{appid}_header.png"):
        p = cache / name
        if p.exists():
            return p
    return None


def _header_image(appid: str) -> Optional[Path]:
    if not STEAM_ROOT:
        return None
    cache = STEAM_ROOT / "appcache" / "librarycache"

    appid_dir = cache / appid
    if appid_dir.is_dir():
        for name in ("library_hero.jpg", "library_header.jpg", "library_600x900.jpg", "library_capsule.jpg"):
            # Flat: librarycache/<appid>/<name>.jpg
            candidate = appid_dir / name
            if candidate.exists():
                return candidate
            # Hash-subdir: librarycache/<appid>/<hash>/<name>.jpg
            for sub in appid_dir.iterdir():
                if sub.is_dir():
                    candidate = sub / name
                    if candidate.exists():
                        return candidate

    # Old flat format: librarycache/<appid>_header.jpg
    for name in (f"{appid}_library_hero.jpg", f"{appid}_header.jpg", f"{appid}_header.png"):
        p = cache / name
        if p.exists():
            return p

    return None


# ---------------------------------------------------------------------------
# Proton / compat-tool discovery
# ---------------------------------------------------------------------------

def get_available_proton_versions() -> list:
    """Return [{"name": display_name, "id": internal_id, "binary": path_or_None}, ...]."""
    versions: list = []
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


def select_best_proton_id(versions: list) -> str:
    """Return the ID of the best available Proton version per preference order."""
    candidates = [v for v in versions if v.get("binary")]

    def _match(v: dict, *keywords: str) -> bool:
        hay = (v["name"] + " " + v["id"]).lower()
        return all(k in hay for k in keywords)

    for predicate in [
        lambda v: _match(v, "cachyos", "latest"),
        lambda v: _match(v, "cachyos"),
        lambda v: _match(v, "ge", "latest"),
        lambda v: _match(v, "ge-proton") or _match(v, "proton-ge"),
        lambda v: _match(v, "experimental"),
        lambda v: bool(re.search(r"\d", v["name"])),
        lambda v: True,
    ]:
        hit = next((v for v in candidates if predicate(v)), None)
        if hit:
            return hit["id"]
    return ""


def find_proton_binary(proton_id: str) -> Optional[str]:
    """Return the path to the 'proton' script for the given internal tool ID."""
    if not proton_id:
        return None
    for v in get_available_proton_versions():
        if v["id"] == proton_id:
            return v["binary"]
    return None


def find_steam_runtime_entry_point(proton_dir: Optional[Path] = None) -> Optional[str]:
    """Find the _v2-entry-point for the given Proton installation.

    If proton_dir is provided and its toolmanifest.vdf declares require_tool_appid,
    the runtime matching that Steam app ID is used (e.g. SteamLinuxRuntime_4 for
    Proton 11+). Falls back to scanning for Sniper then Soldier.
    """
    if proton_dir:
        appid = _vdf_field(proton_dir / "toolmanifest.vdf", "require_tool_appid")
        if appid:
            ep = _find_runtime_entry_by_appid(appid)
            if ep:
                return str(ep)
    for runtime in ("SteamLinuxRuntime_sniper", "SteamLinuxRuntime_soldier"):
        ep = _find_in_all_libraries(f"common/{runtime}/_v2-entry-point")
        if ep:
            return str(ep)
    return None


def _find_runtime_entry_by_appid(appid: str) -> Optional[Path]:
    """Find the _v2-entry-point for a runtime by its Steam app ID."""
    if not STEAM_ROOT:
        return None
    roots = [STEAM_ROOT / "steamapps"]
    lf = STEAM_ROOT / "steamapps" / "libraryfolders.vdf"
    if lf.exists():
        for m in re.finditer(r'"path"\s+"([^"]+)"', lf.read_text(errors="replace")):
            roots.append(Path(m.group(1)) / "steamapps")
    for r in roots:
        manifest = r / f"appmanifest_{appid}.acf"
        if not manifest.exists():
            continue
        installdir = _acf_field(manifest, "installdir")
        if not installdir:
            continue
        ep = r / "common" / installdir / "_v2-entry-point"
        if ep.exists() and os.access(ep, os.X_OK):
            return ep
    return None


def get_steam_launch_env(appid: str) -> dict:
    """Return env vars parsed from the game's Steam launch options in localconfig.vdf.

    Parses KEY=VALUE tokens that appear before %command% in the launch options string.
    Returns {} if no launch options found or no env vars set.
    """
    opts = _get_localconfig_launch_options(appid)
    if not opts:
        return {}
    import shlex
    env = {}
    try:
        tokens = shlex.split(opts)
    except Exception:
        return {}
    for token in tokens:
        if token == "%command%":
            break
        if "=" in token:
            k, _, v = token.partition("=")
            if k and k.replace("_", "").isalnum():
                env[k] = v
    return env


def get_steam_launch_wrappers(appid: str) -> str:
    """Return wrapper tokens from Steam launch options (between env vars and %command%).

    Tokens before %command% that are not KEY=VALUE are wrapper commands + their args.
    Returns empty string if no %command% or no wrapper tokens found.
    """
    opts = _get_localconfig_launch_options(appid)
    if not opts or "%command%" not in opts:
        return ""
    before = opts.split("%command%", 1)[0].strip()
    if not before:
        return ""
    import shlex
    try:
        tokens = shlex.split(before)
    except Exception:
        return before
    i = 0
    while i < len(tokens):
        k = tokens[i].partition("=")[0]
        if "=" in tokens[i] and k and k.replace("_", "").isalnum():
            i += 1
        else:
            break
    wrapper_tokens = tokens[i:]
    if not wrapper_tokens:
        return ""
    return shlex.join(wrapper_tokens)


def get_steam_launch_args(appid: str) -> str:
    """Return game args from Steam launch options.

    Everything after %command%, or the full string if %command% is absent.
    Returns empty string if no launch options or nothing to return.
    """
    opts = _get_localconfig_launch_options(appid)
    if not opts:
        return ""
    if "%command%" in opts:
        return opts.split("%command%", 1)[1].strip()
    return opts.strip()


def _get_localconfig_launch_options(appid: str) -> str:
    if not STEAM_ROOT:
        return ""
    userdata = STEAM_ROOT / "userdata"
    if not userdata.exists():
        return ""
    for user_dir in sorted(userdata.iterdir()):
        if not user_dir.is_dir():
            continue
        lcv = user_dir / "config" / "localconfig.vdf"
        if not lcv.exists():
            continue
        try:
            text = lcv.read_text(errors="replace")
            m = re.search(rf'"{re.escape(appid)}"\s*\{{', text)
            if not m:
                continue
            start = m.end()
            depth = 1
            i = start
            while i < len(text) and depth > 0:
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                i += 1
            block = text[start : i - 1]
            lo = re.search(r'"LaunchOptions"\s+"((?:[^"\\]|\\.)*)"', block, re.IGNORECASE)
            if lo:
                return re.sub(r'\\(.)', r'\1', lo.group(1))
        except Exception:
            continue
    return ""


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


