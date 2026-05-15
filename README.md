# Launchy

A simple, configurable Steam compatibility tool that shows a launch window before starting games — with per-game settings for Proton version, environment variables, wrappers, and launch arguments.

## Features

- Countdown window before launch (configurable, can be set to 0 to disable)
- Header image, game title, and folder paths shown on launch
- **Play Now**, **Game Settings**, **Global Settings**, and **Cancel** buttons
- Per-game and global configuration stored in `~/.config/launchy/`
- Per-game values override global values for env vars and Proton; wrappers and extra args are concatenated
- Supports any pre-game wrappers (MangoHud, Gamescope, Strangle, …)
- Detects and lists all installed Proton / GE-Proton versions
- Attempts to write the chosen Proton version to Steam's `localconfig.vdf`

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
yay -S launchy   # or paru, makepkg, etc.
```

After installation, register with Steam:
```bash
launchy install
```

### From source (no pip required)

```bash
git clone https://github.com/YOURUSERNAME/launchy
cd launchy
make install           # installs to ~/.local
launchy install        # registers with Steam
```

To install system-wide instead:
```bash
sudo make install PREFIX=/usr/local
```

To uninstall:
```bash
make uninstall
launchy uninstall      # removes Steam compat tool entry
```

Then restart Steam and select **Launchy** in a game's **Properties → Compatibility**.

## Configuration

Config files live in `~/.config/launchy/`:

| File | Purpose |
|------|---------|
| `config.toml` | Global settings |
| `games/<appid>.toml` | Per-game overrides |

### Global config example

```toml
[general]
countdown = 5      # seconds before auto-launch (0 = disabled)
proton = ""        # default Proton (empty = Steam's choice)

[env]
MANGOHUD = "1"
DXVK_ASYNC = "1"

[wrappers]
pre = ["mangohud"]

[args]
extra = []
```

### Per-game config example (`games/1091500.toml`)

```toml
[general]
proton = "GE-Proton10-24"   # overrides global

[env]
DXVK_ASYNC = "0"            # overrides global

[wrappers]
pre = ["strangle 60"]       # appended after global wrappers

[args]
game_args = ["--dx11"]
```

## Merge rules

| Setting | Merge behaviour |
|---------|----------------|
| `env` | Global + per-game merged; per-game values win on conflict |
| `wrappers.pre` | Global list + per-game list concatenated |
| `args.extra` (global) / `args.game_args` (per-game) | Both appended to command |
| `general.proton` | Per-game wins if non-empty, otherwise global |

## CLI reference

```
launchy install          Register with Steam as a compat tool
launchy uninstall        Remove the Steam compat tool entry
launchy <verb> [cmd...]  Called automatically by Steam
launchy --help
```

## How it works

Steam calls `launchy waitforexitandrun /path/to/game.exe [args]`.  
Launchy shows the UI, and when the user confirms (or the countdown expires), it builds the final command:

```
[pre_wrappers...] [steam_game_cmd...] [extra_args] [game_args]
```

with the merged environment, then `execvpe`s into it — so the Launchy process *becomes* the game process, which is what Steam expects.
