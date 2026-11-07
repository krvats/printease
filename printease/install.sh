#!/usr/bin/env bash
# PrintEase one-command installer:
#   curl -fsSL https://raw.githubusercontent.com/krvats/printease/main/install.sh | bash
# RULE: every new dependency/file/feature MUST be wired into this single installer.
set -euo pipefail
REPO="${PRINTEASE_REPO:-krvats/printease}"
APP="$HOME/.local/share/printease-app"
BIN="$HOME/.local/bin"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || echo .)"
[[ $EUID -eq 0 ]] && { echo "Run as your normal user, not root."; exit 1; }

echo "==> 1/5 Installing system packages (CUPS, Python, polkit, git)"
. /etc/os-release 2>/dev/null || true
case "${ID:-} ${ID_LIKE:-}" in
  *arch*|*cachyos*|*manjaro*) sudo pacman -S --needed --noconfirm cups cups-filters ghostscript avahi nss-mdns polkit python git ;;
  *debian*|*ubuntu*|*mint*)   sudo apt-get update -y && sudo apt-get install -y cups cups-filters ghostscript printer-driver-escpr python3 git pkexec || sudo apt-get install -y cups cups-filters ghostscript printer-driver-escpr python3 git policykit-1 ;;
  *fedora*|*rhel*)            sudo dnf install -y cups cups-filters ghostscript polkit python3 git ;;
  *suse*)                     sudo zypper --non-interactive install cups cups-filters ghostscript polkit python3 git ;;
  *) echo "Unknown distro: install cups, python3, git and polkit yourself, then re-run." ;;
esac

echo "==> 2/5 Starting CUPS"
sudo systemctl enable --now cups.service || true
sudo systemctl enable --now avahi-daemon.service 2>/dev/null || true

echo "==> 3/5 Getting PrintEase"
mkdir -p "$BIN" "$APP"
if [[ -f "$SRC/printease/server.py" ]]; then
  [[ "$SRC" == "$APP" ]] || cp -r "$SRC/printease" "$SRC/profiles" "$SRC/assets" "$APP/" 2>/dev/null || true
elif [[ -d "$APP/.git" ]]; then git -C "$APP" pull --ff-only
else rm -rf "$APP"; git clone --depth 1 "https://github.com/$REPO.git" "$APP"; fi

echo "==> 4/5 Printer driver (Arch/AUR only; other distros got it in step 1)"
if command -v pacman >/dev/null; then
  H=$(command -v paru || command -v yay || true)
  if [[ -n "$H" ]]; then "$H" -S --needed --noconfirm epson-inkjet-printer-escpr2 || echo "AUR driver failed; use 'Install drivers' in the app."
  else echo "No AUR helper (paru/yay). Install one, or use 'Install drivers' in the app."; fi
fi

echo "==> 5/5 Creating launcher and app-menu entry"
cat > "$BIN/printease" <<LAUNCH
#!/usr/bin/env bash
export PRINTEASE_REPO="$REPO"
cd "$APP" && exec python3 -m printease "\$@"
LAUNCH
chmod +x "$BIN/printease"
mkdir -p "$HOME/.local/share/applications" "$HOME/.local/share/icons"
cp "$APP/assets/icon.svg" "$HOME/.local/share/icons/printease.svg" 2>/dev/null || true
cat > "$HOME/.local/share/applications/printease.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=PrintEase
Comment=Printer setup and printing, no terminal
Exec=$BIN/printease
Icon=$HOME/.local/share/icons/printease.svg
Terminal=false
Categories=Utility;Settings;
DESK
D="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
[[ -d "$D" ]] && { cp "$HOME/.local/share/applications/printease.desktop" "$D/" && chmod +x "$D/printease.desktop"; } || true
echo "==> Done! Open 'PrintEase' from your app menu (or the Desktop icon). No terminal needed."
