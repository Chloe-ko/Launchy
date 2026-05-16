# Launchy

> **Disclaimer:** This project was entirely vibe coded using Claude (AI). I did not write any of this code myself. Use at your own risk, and feel free to improve it.

A configurable Steam compatibility tool that intercepts game launches to show a settings window — letting you tweak Proton version, environment variables, wrappers, and arguments before the game starts.

## Features

### Launch window
- Shows game art, title, Steam App ID, and ProtonDB rating (fetched live)
- Countdown before auto-launch (configurable globally; 0 disables it)
- Quick Proton version selector per launch
- Quick-toggle checkboxes for sets that are marked "show in launch"
- **Skip countdown** toggle: when enabled, the game launches instantly next time with no window shown at all

### Settings
- **Per-game settings** — Proton version, env vars, wrappers, arguments, and which sets are active
- **Global settings** — default Proton, countdown duration, global env/wrappers/args
- Settings open from the launch window or via `launchy settings [appid]`
- Steam launch options shown as read-only reference in each tab
- Global options shown as read-only reference in per-game tabs (with per-game override indicators)

### Sets — reusable config profiles
- Create named sets with their own env vars, wrappers, and arguments
- Enable sets per-game; active sets' contributions shown grouped by set name in per-game settings
- Sets can be marked to appear as quick-toggles in the launch window
- Sets support a priority order and dependency requirements

### Global settings extras
- "Skip Countdown" section lists all games with instant-launch enabled, with their cover art, sorted alphabetically — each has a Remove button to restore the launch window

### Desktop integration
- Installs a `.desktop` entry so Launchy appears in your application launcher (`launchy settings`)
- Window class registered as `launchy` for compositor rules

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
```

After installation, register with Steam:
```bash
launchy install
```

### From source

```bash
git clone https://github.com/Chloe-ko/launchy
cd launchy
make install           # installs to ~/.local
launchy install        # registers with Steam
```

System-wide:
```bash
sudo make install PREFIX=/usr/local
```

Uninstall:
```bash
make uninstall
```

Then restart Steam and select **Launchy** under **Properties → Compatibility** for any game.

## Configuration

Config files live in `~/.config/launchy/`:

| Path | Purpose |
|------|---------|
| `config.toml` | Global settings |
| `games/<appid>.toml` | Per-game overrides |
| `sets/<uuid>.toml` | Set definitions |

### Global config (`config.toml`)

```toml
[general]
countdown = 5      # seconds before auto-launch (0 = disabled)
proton = ""        # default Proton version ID

[env]
MANGOHUD = "1"

[wrappers]
pre = ["mangohud"]

[args]
extra = []
```

### Per-game config (`games/1091500.toml`)

```toml
[general]
proton = "GE-Proton10-24"   # overrides global
skip_countdown = true        # skip launch window entirely

[env]
DXVK_ASYNC = "0"            # overrides global

[wrappers]
pre = ["strangle 60"]

[args]
game_args = ["--dx11"]

[sets]
enabled = ["<set-uuid>"]
```

## Merge rules

| Setting | Behaviour |
|---------|-----------|
| `env` | Global → active sets (priority order) → per-game; last writer wins per key |
| `wrappers.pre` | Global + sets + per-game concatenated; binary deduplication across sets |
| `args.extra` / `args.game_args` | All appended to final command |
| `general.proton` | Per-game wins if set, otherwise global |

## CLI

```
launchy install              Register with Steam as a compat tool
launchy uninstall            Remove Steam compat tool entry
launchy settings             Open global settings
launchy settings <appid>     Open per-game settings
launchy <verb> [cmd...]      Called automatically by Steam
```

## How it works

Steam calls `launchy waitforexitandrun /path/to/game.exe [args]`.
Launchy checks if the game has skip-countdown enabled — if so, it builds the final command and execs immediately. Otherwise it shows the UI, and when the user confirms (or the countdown expires) it builds:

```
[pre_wrappers...] [steam_runtime] [proton] <verb> [game_cmd...] [extra_args] [game_args]
```

with the merged environment, then `execvpe`s — becoming the game process, as Steam expects.

## License

GPLv2 — see [LICENSE](LICENSE).
