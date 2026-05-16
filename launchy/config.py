import os
import sys
import tomllib
import uuid
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "launchy"
GAMES_DIR = CONFIG_DIR / "games"
SETS_DIR = CONFIG_DIR / "sets"

_DEFAULT_GLOBAL = {
    "general": {
        "countdown": 5,
        "proton": "",
    },
    "env": {},
    "wrappers": {"pre": []},
    "args": {"extra": []},
}

_DEFAULT_GAME = {
    "general": {
        "name": "",
        "proton": "",
        "skip_countdown": False,
    },
    "env": {},
    "wrappers": {"pre": []},
    "args": {"game_args": []},
}

_DEFAULT_SET = {
    "general": {"name": "New Set", "show_in_launch": False, "enabled_by_default": False},
    "env": {},
    "wrappers": {"pre": []},
    "args": {"extra": []},
}


def _ensure_dirs():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    GAMES_DIR.mkdir(parents=True, exist_ok=True)
    SETS_DIR.mkdir(parents=True, exist_ok=True)


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception as e:
        print(f"Warning: failed to read {path}: {e}", file=sys.stderr)
        return {}


def _save(path: Path, data: dict):
    from launchy.utils import toml_dumps
    _ensure_dirs()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(toml_dumps(data) + "\n", encoding="utf-8")


def _merge(base: dict, over: dict) -> dict:
    result = {}
    for key in list(base) + [k for k in over if k not in base]:
        bv = base.get(key)
        ov = over.get(key)
        if isinstance(bv, dict) and isinstance(ov, dict):
            result[key] = _merge(bv, ov)
        elif key in over:
            result[key] = ov
        else:
            result[key] = bv
    return result


def get_global_config() -> dict:
    return _merge(_DEFAULT_GLOBAL, _load(CONFIG_DIR / "config.toml"))


def save_global_config(config: dict):
    _save(CONFIG_DIR / "config.toml", config)


def get_game_config(appid: str) -> dict:
    return _merge(_DEFAULT_GAME, _load(GAMES_DIR / f"{appid}.toml"))


def save_game_config(appid: str, config: dict):
    _save(GAMES_DIR / f"{appid}.toml", config)


# ---------------------------------------------------------------------------
# Sets
# ---------------------------------------------------------------------------

def get_set_config(set_id: str) -> dict:
    return _merge(_DEFAULT_SET, _load(SETS_DIR / f"{set_id}.toml"))


def save_set_config(set_id: str, config: dict):
    _save(SETS_DIR / f"{set_id}.toml", config)


def delete_set_config(set_id: str):
    path = SETS_DIR / f"{set_id}.toml"
    if path.exists():
        path.unlink()


def create_set() -> str:
    """Create a new set with default config, return its ID."""
    set_id = str(uuid.uuid4())
    save_set_config(set_id, dict(_DEFAULT_SET))
    return set_id


def get_games_with_skip_countdown() -> list[str]:
    """Return appids of all games that have skip_countdown=True."""
    result = []
    if not GAMES_DIR.exists():
        return result
    for path in GAMES_DIR.glob("*.toml"):
        cfg = _load(path)
        if cfg.get("general", {}).get("skip_countdown", False):
            result.append(path.stem)
    return result


def bootstrap_game_config(appid: str):
    """If no per-game config exists, create one with default-enabled sets."""
    path = GAMES_DIR / f"{appid}.toml"
    if path.exists():
        return
    g = get_global_config()
    default_enabled = []
    for sid in g.get("sets", {}).get("order", []):
        try:
            if get_set_config(sid).get("general", {}).get("enabled_by_default", False):
                default_enabled.append(sid)
        except Exception:
            pass
    if default_enabled:
        cfg = dict(_DEFAULT_GAME)
        cfg["sets"] = {"enabled": default_enabled}
        save_game_config(appid, cfg)


# ---------------------------------------------------------------------------
# Merged config
# ---------------------------------------------------------------------------

def _expand_with_deps(enabled_ids: set, all_set_ids: list) -> set:
    """Expand enabled set IDs with their transitive requires."""
    result = set(enabled_ids)
    valid = set(all_set_ids)
    queue = list(enabled_ids)
    while queue:
        sid = queue.pop()
        try:
            for dep in get_set_config(sid).get("general", {}).get("requires", []):
                if dep in valid and dep not in result:
                    result.add(dep)
                    queue.append(dep)
        except Exception:
            pass
    return result


def get_merged_config(appid: str) -> dict:
    """Effective config for a game: global → sets (by priority) → per-game."""
    g = get_global_config()
    p = get_game_config(appid)

    ignore = p.get("global_ignore", {})
    ignore_env = set(ignore.get("env", []))
    ignore_wrappers = set(ignore.get("wrappers", []))
    ignore_args = set(ignore.get("args", []))

    # Active sets in priority order (index 0 = highest priority)
    all_set_ids = g.get("sets", {}).get("order", [])
    if not (GAMES_DIR / f"{appid}.toml").exists():
        enabled_ids = set()
        for sid in all_set_ids:
            try:
                if get_set_config(sid).get("general", {}).get("enabled_by_default", False):
                    enabled_ids.add(sid)
            except Exception:
                pass
    else:
        enabled_ids = set(p.get("sets", {}).get("enabled", []))
    enabled_ids = _expand_with_deps(enabled_ids, all_set_ids)
    active_sets = []
    for sid in all_set_ids:
        if sid in enabled_ids:
            try:
                active_sets.append(get_set_config(sid))
            except Exception:
                pass

    merged = {
        "general": dict(g["general"]),
        "env": {},
        "wrappers": {},
        "args": {},
    }

    if p["general"].get("proton"):
        merged["general"]["proton"] = p["general"]["proton"]
    if p["general"].get("name"):
        merged["general"]["name"] = p["general"]["name"]

    # --- Env: global → sets (lowest→highest priority) → per-game ---
    eff_env = {k: v for k, v in g.get("env", {}).items() if k not in ignore_env}
    for sc in reversed(active_sets):  # lowest priority first so highest wins
        eff_env.update(sc.get("env", {}))
    eff_env.update(p.get("env", {}))
    merged["env"] = eff_env

    # --- Wrappers: global → sets (highest priority binary wins) → per-game ---
    game_pre = list(p.get("wrappers", {}).get("pre", []))
    game_bins = {w.split()[0] for w in game_pre if w.strip()}

    # Collect set wrappers: highest priority set first; skip binaries already claimed
    set_pre = []
    set_bins: set = set()
    for sc in active_sets:  # highest priority first
        for w in sc.get("wrappers", {}).get("pre", []):
            b = w.split()[0] if w.strip() else w
            if b not in set_bins and b not in game_bins:
                set_pre.append(w)
                set_bins.add(b)

    # Global wrappers: skip ignored and binaries claimed by sets or per-game
    global_pre = []
    for w in g.get("wrappers", {}).get("pre", []):
        b = w.split()[0] if w.strip() else w
        if b not in ignore_wrappers and b not in game_bins and b not in set_bins:
            global_pre.append(w)

    merged["wrappers"]["pre"] = global_pre + set_pre + game_pre

    # --- Args: global → sets (highest priority first) → per-game ---
    global_extra = [a for a in g.get("args", {}).get("extra", []) if str(a) not in ignore_args]
    set_extra: list = []
    for sc in active_sets:  # highest priority first
        set_extra.extend(sc.get("args", {}).get("extra", []))

    merged["args"]["extra"] = global_extra + set_extra
    merged["args"]["game_args"] = list(p.get("args", {}).get("game_args", []))

    return merged
