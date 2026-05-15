#!/usr/bin/env bash
# Quick install script — registers Launchy as a Steam compat tool.
# Requires Launchy to already be installed on the system (e.g. via pip or AUR).

set -euo pipefail

STEAM_ROOTS=(
    "$HOME/.steam/root"
    "$HOME/.steam/steam"
    "$HOME/.local/share/Steam"
)

steam_root=""
for p in "${STEAM_ROOTS[@]}"; do
    if [[ -d "$p/steamapps" ]]; then
        steam_root="$p"
        break
    fi
done

if [[ -z "$steam_root" ]]; then
    echo "Error: Could not find Steam installation." >&2
    exit 1
fi

target="$steam_root/compatibilitytools.d/launchy"
mkdir -p "$target"

cat > "$target/compatibilitytool.vdf" << 'EOF'
"compatibilitytools"
{
  "compat_tools"
  {
    "launchy"
    {
      "install_path" "."
      "display_name"  "Launchy"
      "from_oslist"   "Windows"
      "to_oslist"     "linux"
      "launch_configs"
      {
        "0"
        {
          "commandline" "/launchy %verb%"
          "description" "Default"
        }
      }
    }
  }
}
EOF

cat > "$target/launchy" << 'EOF'
#!/usr/bin/env bash
exec /usr/bin/launchy "$@"
EOF
chmod +x "$target/launchy"

echo "Launchy installed to: $target"
echo "Restart Steam, then select 'Launchy' as the compatibility tool for a game."
