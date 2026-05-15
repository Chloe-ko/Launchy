import os
import sys
import tomllib
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "launchy"
GAMES_DIR = CONFIG_DIR / "games"

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
    },
    "env": {},
    "wrappers": {"pre": []},
    "args": {"game_args": []},
}


def _ensure_dirs():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    GAMES_DIR.mkdir(parents=True, exist_ok=True)


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
    # base keys first (preserves expected order), then any new keys from over
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


def get_merged_config(appid: str) -> dict:
    """Effective config for a game: global + per-game, with per-game taking precedence."""
    g = get_global_config()
    p = get_game_config(appid)

    merged = {
        "general": dict(g["general"]),
        "env": {**g.get("env", {}), **p.get("env", {})},
        "wrappers": {},
        "args": {},
    }

    if p["general"].get("proton"):
        merged["general"]["proton"] = p["general"]["proton"]
    if p["general"].get("name"):
        merged["general"]["name"] = p["general"]["name"]

    merged["wrappers"]["pre"] = (
        list(g.get("wrappers", {}).get("pre", []))
        + list(p.get("wrappers", {}).get("pre", []))
    )
    merged["args"]["extra"] = list(g.get("args", {}).get("extra", []))
    merged["args"]["game_args"] = list(p.get("args", {}).get("game_args", []))

    return merged
