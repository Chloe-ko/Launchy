<img src="data/logo-pixel-heart.svg" width="80" align="left" style="margin-right: 16px"/>

# Launchy

[![Tests](https://github.com/Chloe-ko/Launchy/actions/workflows/tests.yml/badge.svg)](https://github.com/Chloe-ko/Launchy/actions/workflows/tests.yml)

A configurable Steam compatibility tool that intercepts game launches to show a settings window before the game starts.

> This project was developed with the help of [Claude](https://claude.ai) (Anthropic AI).

<br clear="left"/>

## Features

- **Launch window** — game art, ProtonDB rating, Proton selector, countdown before auto-launch
- **Skip countdown** — per-game toggle in game settings to bypass the launch window and launch instantly
- **Sets** — reusable named config profiles (env vars, wrappers, args) that can be enabled per-game
- **Per-game and global settings** — Proton version, environment variables, pre-launch wrappers, and extra arguments
- **Application launcher entry** — `launchy settings` available from your desktop launcher

## Dependencies

- Python ≥ 3.11
- GTK 4
- libadwaita ≥ 1.4
- python-gobject

On Arch Linux:
```
sudo pacman -S python gtk4 libadwaita python-gobject
```

## Installation

### From AUR

```bash
yay -S launchy
launchy install
```

### From source

```bash
git clone https://github.com/Chloe-ko/launchy
cd launchy
make install
launchy install
```

Restart Steam and select **Launchy** under **Properties → Compatibility** for any game.

To uninstall: `make uninstall`

## Configuration

Config files live in `~/.config/launchy/`:

| Path | Purpose |
|------|---------|
| `config.toml` | Global settings (countdown, default Proton, env, wrappers, args) |
| `games/<appid>.toml` | Per-game overrides and active sets |
| `sets/<uuid>.toml` | Set definitions |

## Merge rules

| Setting | Behaviour |
|---------|-----------|
| `env` | Global → active sets → per-game; last writer wins per key |
| `wrappers` | Global + sets + per-game concatenated; binary deduplication across sets |
| `args` | Global + sets + per-game appended to final command |
| `proton` | Per-game wins if set, otherwise global |

## CLI

```
launchy install              Register with Steam as a compat tool
launchy uninstall            Remove Steam compat tool entry
launchy settings             Open global settings
launchy settings <appid>     Open per-game settings
```

## License

GPLv3 — see [LICENSE](LICENSE).
