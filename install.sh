#!/usr/bin/env bash
# PrintEase one-command installer
#   curl -fsSL https://raw.githubusercontent.com/krvats/printease/main/install.sh | bash
# Works on: Arch / CachyOS / Manjaro / EndeavourOS / Garuda, Ubuntu / Debian /
#   Mint / Pop!_OS / Elementary / Zorin / Kali, Fedora / RHEL / CentOS / AlmaLinux /
#   Rocky / Nobara, openSUSE / SUSE, Void, Alpine, NixOS (limited), Gentoo (limited)
set -euo pipefail

REPO="${PRINTEASE_REPO:-krvats/printease}"
APP="$HOME/.local/share/printease-app"
BIN="$HOME/.local/bin"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || echo .)"

[[ $EUID -eq 0 ]] && { echo "Run as your normal user, not root."; exit 1; }

# ── 1. detect distro ──────────────────────────────────────────────────────────
. /etc/os-release 2>/dev/null || true
ID_L="${ID:-linux}"
ID_LIKE_L="${ID_LIKE:-}"
COMBINED="${ID_L} ${ID_LIKE_L}"

echo "==> 1/5  Installing system packages (CUPS, Python 3, polkit, avahi, git)"
case "$COMBINED" in
  *arch*|*cachyos*|*manjaro*|*endeavouros*|*garuda*|*artix*|*blackarch*)
    sudo pacman -S --needed --noconfirm \
      cups cups-filters ghostscript avahi nss-mdns polkit python git
    # enable avahi for mDNS printer discovery
    sudo systemctl enable --now avahi-daemon.service 2>/dev/null || true
    ;;
  *ubuntu*|*debian*|*mint*|*pop*|*elementary*|*zorin*|*kali*|*lmde*|*neon*|*raspbian*)
    sudo apt-get update -y
    sudo apt-get install -y \
      cups cups-filters ghostscript python3 git \
      avahi-daemon avahi-utils \
      policykit-1 pkexec 2>/dev/null \
      || sudo apt-get install -y cups cups-filters ghostscript python3 git avahi-daemon polkit
    sudo systemctl enable --now avahi-daemon 2>/dev/null || true
    ;;
  *fedora*|*rhel*|*centos*|*alma*|*rocky*|*nobara*)
    sudo dnf install -y cups cups-filters ghostscript avahi nss-mdns polkit python3 git
    sudo systemctl enable --now avahi.service 2>/dev/null || true
    ;;
  *suse*|*opensuse*)
    sudo zypper --non-interactive install cups cups-filters ghostscript avahi nss-mdns polkit python3 git
    sudo systemctl enable --now avahi.service 2>/dev/null || true
    ;;
  *void*)
    sudo xbps-install -Sy cups cups-filters ghostscript avahi nss-mdns polkit python3 git
    sudo ln -sf /etc/sv/avahi-daemon /var/service/ 2>/dev/null || true
    sudo ln -sf /etc/sv/cupsd       /var/service/ 2>/dev/null || true
    ;;
  *alpine*)
    sudo apk add --no-cache cups cups-filters ghostscript avahi python3 git
    ;;
  *nixos*)
    echo "   NixOS: add 'services.printing.enable = true; services.avahi.enable = true;' to configuration.nix and rebuild."
    ;;
  *gentoo*)
    sudo emerge --noreplace net-print/cups app-text/ghostscript-gpl net-dns/avahi dev-lang/python git
    ;;
  *)
    echo "   Distro not auto-detected. Install: cups, python3, git, polkit, avahi — then re-run."
    ;;
esac

# ── 2. start CUPS ─────────────────────────────────────────────────────────────
echo "==> 2/5  Starting CUPS"
sudo systemctl enable --now cups.service 2>/dev/null \
  || sudo service cups start 2>/dev/null \
  || { echo "   Could not start CUPS automatically. Start it with: sudo systemctl start cups"; }

# ── 3. get PrintEase ──────────────────────────────────────────────────────────
echo "==> 3/5  Getting PrintEase"
mkdir -p "$BIN" "$APP"
if [[ -f "$SRC/printease/server.py" ]]; then
  # running from an already-extracted source tree
  [[ "$SRC" == "$APP" ]] || rsync -a --exclude='.git' \
    "$SRC/printease" "$SRC/profiles" "$SRC/assets" "$APP/" 2>/dev/null \
    || cp -r "$SRC/printease" "$SRC/profiles" "$SRC/assets" "$APP/"
elif [[ -d "$APP/.git" ]]; then
  git -C "$APP" pull --ff-only
else
  rm -rf "$APP"
  git clone --depth 1 "https://github.com/$REPO.git" "$APP"
fi

# ── 4. printer drivers ────────────────────────────────────────────────────────
echo "==> 4/5  Printer drivers"
echo "   IPP Everywhere (driverless) is built into CUPS 2.x and later."
echo "   Most modern USB and network printers work without extra drivers."
echo "   If your printer needs a vendor driver, install it via your package manager:"
case "$COMBINED" in
  *arch*|*cachyos*|*manjaro*|*endeavouros*|*garuda*|*artix*)
    echo "   HP    : paru -S hplip  (or:  sudo pacman -S hplip)"
    echo "   Epson : paru -S epson-inkjet-printer-escpr2"
    echo "   Canon : paru -S cnijfilter2 / gutenprint"
    echo "   Brother: paru -S brother-<model>"
    ;;
  *ubuntu*|*debian*|*mint*|*pop*|*zorin*|*kali*)
    echo "   HP    : sudo apt install hplip"
    echo "   Epson : sudo apt install printer-driver-escpr  (or use Epson's .deb)"
    echo "   Canon : sudo apt install printer-driver-gutenprint"
    echo "   Brother: download the .deb from support.brother.com"
    ;;
  *fedora*|*rhel*|*centos*|*rocky*|*alma*)
    echo "   HP    : sudo dnf install hplip"
    echo "   General: sudo dnf install gutenprint foomatic-db-ppds"
    ;;
  *)
    echo "   Consult your distro's package manager or the printer vendor's Linux downloads page."
    ;;
esac
echo "   You can also install drivers from within PrintEase → Maintenance."

# ── 5. launcher + desktop entry ───────────────────────────────────────────────
echo "==> 5/5  Creating launcher"
mkdir -p "$HOME/.local/share/applications" "$HOME/.local/share/icons"

# Write launcher with printf so variable expansion works correctly
# and there are no fragile sed patches needed.
printf '%s\n' '#!/usr/bin/env bash' \
  '# PrintEase launcher — daemonises the server' \
  "APPDIR=\"$APP\"" \
  'PIDFILE="${XDG_RUNTIME_DIR:-/tmp}/printease.pid"' \
  'LOGFILE="${XDG_RUNTIME_DIR:-/tmp}/printease.log"' \
  '' \
  'running() { [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; }' \
  '' \
  'case "${1:-start}" in' \
  '  stop)' \
  '    if running; then' \
  '      kill "$(cat "$PIDFILE")" 2>/dev/null; rm -f "$PIDFILE"; echo "PrintEase stopped."' \
  '    else' \
  '      echo "PrintEase is not running."' \
  '    fi; exit 0 ;;' \
  '' \
  '  status)' \
  '    if running; then' \
  '      echo "Running  PID $(cat "$PIDFILE")  →  http://127.0.0.1:8765"' \
  '    else' \
  '      echo "Not running."' \
  '    fi; exit 0 ;;' \
  '' \
  '  restart) "$0" stop; sleep 0.5; exec "$0" start ;;' \
  '' \
  '  start|"")' \
  '    if running; then' \
  '      echo "Already running (PID $(cat "$PIDFILE"))  →  http://127.0.0.1:8765"' \
  '      xdg-open "http://127.0.0.1:8765" 2>/dev/null &' \
  '      exit 0' \
  '    fi' \
  '    cd "$APPDIR"' \
  '    nohup python3 -m printease 1>>"$LOGFILE" 2>&1 &' \
  '    PID=$!' \
  '    echo $PID > "$PIDFILE"' \
  '    disown $PID' \
  '    echo "PrintEase started (PID $PID)  →  http://127.0.0.1:8765"' \
  '    echo "Logs: $LOGFILE  |  Stop: printease stop"' \
  '    ;;' \
  '' \
  '  *) echo "Usage: printease [start|stop|status|restart]"; exit 1 ;;' \
  'esac' > "$BIN/printease"

chmod +x "$BIN/printease"

# ── optional: systemd user service (auto-start on login) ──────────────────────
SVCDIR="$HOME/.config/systemd/user"
if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
  mkdir -p "$SVCDIR"
  printf '%s\n' \
    '[Unit]' \
    'Description=PrintEase printer manager' \
    'After=network.target' \
    '' \
    '[Service]' \
    'Type=forking' \
    "WorkingDirectory=$APP" \
    "ExecStart=$BIN/printease start" \
    "ExecStop=$BIN/printease stop" \
    'PIDFile=${XDG_RUNTIME_DIR}/printease.pid' \
    'Restart=on-failure' \
    'RestartSec=3' \
    '' \
    '[Install]' \
    'WantedBy=default.target' > "$SVCDIR/printease.service"
  systemctl --user daemon-reload 2>/dev/null || true
  echo "   Systemd user service installed."
  echo "   Auto-start on login: systemctl --user enable --now printease"
fi

[[ -f "$APP/assets/icon.svg" ]] && \
  cp "$APP/assets/icon.svg" "$HOME/.local/share/icons/printease.svg" 2>/dev/null || true

cat > "$HOME/.local/share/applications/printease.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=PrintEase
Comment=Printer setup and printing
Exec=$BIN/printease
Icon=$HOME/.local/share/icons/printease.svg
Terminal=false
Categories=Utility;Settings;
Keywords=print;printer;cups;
DESK

D="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
[[ -d "$D" ]] && {
  cp "$HOME/.local/share/applications/printease.desktop" "$D/printease.desktop"
  chmod +x "$D/printease.desktop"
} || true

update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

# make sure ~/.local/bin is on PATH
if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
  echo ""
  echo "   NOTE: $HOME/.local/bin is not in your PATH."
  echo "   Add this line to your ~/.bashrc or ~/.zshrc:"
  echo '   export PATH="$HOME/.local/bin:$PATH"'
fi

echo ""
echo "==> Done!"
echo "   Open PrintEase from your app menu, the Desktop icon, or run: printease"
