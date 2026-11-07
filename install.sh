#!/usr/bin/env bash
# PrintEase one-command installer
#   curl -fsSL https://raw.githubusercontent.com/krvats/printease/main/install.sh | bash
#
# Works on: Arch / CachyOS / Manjaro / EndeavourOS / Garuda, Ubuntu / Debian /
#   Mint / Pop!_OS / Elementary / Zorin / Kali, Fedora / RHEL / CentOS /
#   AlmaLinux / Rocky / Nobara, openSUSE / SUSE, Void, Alpine, Gentoo
set -euo pipefail

REPO="${PRINTEASE_REPO:-krvats/printease}"
APP="$HOME/.local/share/printease-app"
BIN="$HOME/.local/bin"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || echo .)"

[[ $EUID -eq 0 ]] && { echo "Run as your normal user, not root."; exit 1; }

. /etc/os-release 2>/dev/null || true
ID_L="${ID:-linux}"
ID_LIKE_L="${ID_LIKE:-}"
COMBINED="${ID_L} ${ID_LIKE_L}"

# ── 1. system packages ────────────────────────────────────────────────────────
echo "==> 1/6  Installing system packages"
case "$COMBINED" in
  *arch*|*cachyos*|*manjaro*|*endeavouros*|*garuda*|*artix*|*blackarch*)
    sudo pacman -S --needed --noconfirm \
      cups cups-filters ghostscript avahi nss-mdns polkit python git
    sudo systemctl enable --now avahi-daemon.service 2>/dev/null || true
    ;;
  *ubuntu*|*debian*|*mint*|*pop*|*elementary*|*zorin*|*kali*|*lmde*|*neon*)
    sudo apt-get update -y
    sudo apt-get install -y \
      cups cups-filters ghostscript python3 git avahi-daemon avahi-utils polkit
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
  *)
    echo "   Distro not auto-detected. Manually install: cups python3 git polkit avahi"
    ;;
esac

# ── 2. start CUPS ─────────────────────────────────────────────────────────────
echo "==> 2/6  Starting CUPS"
sudo systemctl enable --now cups.service 2>/dev/null \
  || sudo service cups start 2>/dev/null \
  || echo "   Could not start CUPS automatically — run: sudo systemctl start cups"

# ── 3. PRIVILEGE SETUP ────────────────────────────────────────────────────────
# This is the step that makes PrintEase run without ever prompting for a password.
# It adds the user to the 'lp' group (CUPS admin group) and sets up:
#   a) A sudoers rule for specific lpadmin/cupsctl commands (NOPASSWD)
#   b) A polkit rule so pkexec works silently for CUPS
echo "==> 3/6  Granting printer management privileges (no more password prompts)"

# Add user to lp group so lpadmin works on most distros without sudo
sudo usermod -aG lp "$USER" 2>/dev/null || true
# Also add to sys group if it exists (some Arch setups need this)
getent group sys  > /dev/null 2>&1 && sudo usermod -aG sys  "$USER" 2>/dev/null || true
getent group cups > /dev/null 2>&1 && sudo usermod -aG cups "$USER" 2>/dev/null || true

# Sudoers rule — only specific CUPS commands, no shell, no wildcard
SUDOERS_FILE="/etc/sudoers.d/printease"
cat <<SUDOERS | sudo tee "$SUDOERS_FILE" > /dev/null
# PrintEase printer management — no password prompt for CUPS commands
Defaults!$(which lpadmin 2>/dev/null || echo /usr/bin/lpadmin) !requiretty
${USER} ALL=(ALL) NOPASSWD: $(which lpadmin 2>/dev/null    || echo /usr/bin/lpadmin)
${USER} ALL=(ALL) NOPASSWD: $(which cupsctl 2>/dev/null    || echo /usr/bin/cupsctl)
${USER} ALL=(ALL) NOPASSWD: $(which cupsenable 2>/dev/null || echo /usr/sbin/cupsenable)
${USER} ALL=(ALL) NOPASSWD: $(which cupsdisable 2>/dev/null|| echo /usr/sbin/cupsdisable)
${USER} ALL=(ALL) NOPASSWD: $(which cancel 2>/dev/null     || echo /usr/bin/cancel)
SUDOERS
sudo chmod 440 "$SUDOERS_FILE"
# Validate — if visudo rejects it, remove it and let pkexec handle elevation
sudo visudo -c -f "$SUDOERS_FILE" 2>/dev/null \
  || { echo "   sudoers syntax error (non-fatal, falling back to pkexec)"; sudo rm -f "$SUDOERS_FILE"; }

# Polkit rule — allows lp-group members to administer CUPS via pkexec graphically
# (this covers the graphical dialog path on KDE, GNOME, etc.)
POLKIT_DIR="/etc/polkit-1/rules.d"
if [[ -d "$POLKIT_DIR" ]]; then
  sudo tee "$POLKIT_DIR/50-printease.rules" > /dev/null << 'POLKIT'
/* PrintEase: allow lp group to manage CUPS printers without a password prompt */
polkit.addRule(function(action, subject) {
  var cups_actions = [
    "org.opensuse.cupspkhelper.mechanism.all-edit",
    "org.opensuse.cupspkhelper.mechanism.printeraddremove",
    "org.opensuse.cupspkhelper.mechanism.server-settings",
    "com.redhat.printhelper.mechanism.all",
    "org.cups.cupsd.printer.create-printer",
    "org.cups.cupsd.printer.delete",
    "org.cups.cupsd.printer.enable",
    "org.cups.cupsd.printer.disable",
  ];
  for (var i = 0; i < cups_actions.length; i++) {
    if (action.id.indexOf(cups_actions[i]) === 0 && subject.isInGroup("lp")) {
      return polkit.Result.YES;
    }
  }
});
POLKIT
  echo "   Polkit rule written to $POLKIT_DIR/50-printease.rules"
fi

echo ""
echo "   NOTE: Group membership (lp) takes effect on next login."
echo "   For this session you can run: newgrp lp"
echo ""

# ── 4. get PrintEase ──────────────────────────────────────────────────────────
echo "==> 4/6  Getting PrintEase"
mkdir -p "$BIN" "$APP"
if [[ -f "$SRC/printease/server.py" ]]; then
  [[ "$SRC" == "$APP" ]] || rsync -a --exclude='.git' \
    "$SRC/printease" "$SRC/profiles" "$SRC/assets" "$APP/" 2>/dev/null \
    || cp -r "$SRC/printease" "$SRC/profiles" "$SRC/assets" "$APP/"
elif [[ -d "$APP/.git" ]]; then
  git -C "$APP" pull --ff-only
else
  rm -rf "$APP"
  git clone --depth 1 "https://github.com/$REPO.git" "$APP"
fi

# ── 5. printer drivers ────────────────────────────────────────────────────────
echo "==> 5/6  Printer drivers"
echo "   IPP Everywhere (driverless) is built into CUPS 2.x — most modern printers work already."
echo "   Vendor-specific drivers (if your printer needs them):"
case "$COMBINED" in
  *arch*|*cachyos*|*manjaro*|*endeavouros*|*garuda*)
    echo "   Epson : paru -S epson-inkjet-printer-escpr2  (AUR)"
    echo "   HP    : sudo pacman -S hplip"
    echo "   Canon : paru -S cnijfilter2  (AUR)"
    echo "   Brother: paru -S brother-<model>  (AUR)"
    ;;
  *ubuntu*|*debian*|*mint*|*pop*|*zorin*)
    echo "   Epson : sudo apt install printer-driver-escpr  (or Epson's .deb)"
    echo "   HP    : sudo apt install hplip"
    echo "   Canon : sudo apt install printer-driver-gutenprint"
    echo "   Brother: download the .deb from support.brother.com"
    ;;
  *fedora*|*rhel*|*centos*|*rocky*|*alma*)
    echo "   HP    : sudo dnf install hplip"
    echo "   General: sudo dnf install gutenprint foomatic-db-ppds"
    ;;
  *)
    echo "   See your distro's package manager or the printer vendor's Linux downloads page."
    ;;
esac

# ── 6. launcher + desktop entry ───────────────────────────────────────────────
echo "==> 6/6  Creating launcher"
mkdir -p "$HOME/.local/share/applications" "$HOME/.local/share/icons"

printf '%s\n' \
  '#!/usr/bin/env bash' \
  '# PrintEase launcher' \
  "APPDIR=\"$APP\"" \
  'PIDFILE="${XDG_RUNTIME_DIR:-/tmp}/printease.pid"' \
  'LOGFILE="${XDG_RUNTIME_DIR:-/tmp}/printease.log"' \
  'URL="http://127.0.0.1:8765/"' \
  '' \
  'running() { [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; }' \
  '' \
  'case "${1:-start}" in' \
  '  stop)' \
  '    running && { kill "$(cat "$PIDFILE")" 2>/dev/null; rm -f "$PIDFILE"; echo "Stopped."; } || echo "Not running."; exit 0 ;;' \
  '  status)' \
  '    running && echo "Running PID $(cat \"$PIDFILE\") → $URL" || echo "Not running."; exit 0 ;;' \
  '  restart) "$0" stop; sleep 0.5; exec "$0" start ;;' \
  '  start|"")' \
  '    if running; then' \
  '      echo "Already running (PID $(cat \"$PIDFILE\")) → $URL"' \
  '      xdg-open "$URL" 2>/dev/null &' \
  '      exit 0' \
  '    fi' \
  '    cd "$APPDIR"' \
  '    nohup python3 -m printease 1>>"$LOGFILE" 2>&1 &' \
  '    PID=$!' \
  '    echo $PID > "$PIDFILE"' \
  '    disown $PID' \
  '    echo "PrintEase started (PID $PID) → $URL"' \
  '    echo "Logs: $LOGFILE  |  Stop: printease stop"' \
  '    sleep 0.5' \
  '    xdg-open "$URL" 2>/dev/null &' \
  '    ;;' \
  '  *) echo "Usage: printease [start|stop|status|restart]"; exit 1 ;;' \
  'esac' > "$BIN/printease"
chmod +x "$BIN/printease"

# systemd user service (auto-start on login)
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
  echo "   Systemd user service created."
  echo "   To auto-start on login: systemctl --user enable --now printease"
fi

# Desktop icon + app menu entry
[[ -f "$APP/assets/icon.svg" ]] && cp "$APP/assets/icon.svg" "$HOME/.local/share/icons/printease.svg" || true

cat > "$HOME/.local/share/applications/printease.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=PrintEase
Comment=Printer management and printing
Exec=$BIN/printease
Icon=$HOME/.local/share/icons/printease.svg
Terminal=false
Categories=Utility;Settings;
Keywords=print;printer;cups;
DESK

DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
[[ -d "$DESKTOP_DIR" ]] && {
  cp "$HOME/.local/share/applications/printease.desktop" "$DESKTOP_DIR/printease.desktop"
  chmod +x "$DESKTOP_DIR/printease.desktop"
} || true

update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

# PATH reminder
if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
  echo ""
  echo "   NOTE: Add ~/.local/bin to your PATH — add this to ~/.bashrc or ~/.zshrc:"
  echo '   export PATH="$HOME/.local/bin:$PATH"'
fi

echo ""
echo "============================================================"
echo "  PrintEase installed successfully."
echo ""
echo "  To start it now, in a new terminal:"
echo "    newgrp lp     ← activates group membership without logout"
echo "    printease"
echo ""
echo "  Or log out and back in, then just run: printease"
echo "============================================================"
