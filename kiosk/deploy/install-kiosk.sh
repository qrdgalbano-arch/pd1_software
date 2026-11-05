#!/usr/bin/env bash
# Installs the QMMC Rehab Station kiosk on Ubuntu/Debian. Run:  sudo bash kiosk/deploy/install-kiosk.sh [path/to/QMMCRehab.deb]
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Run as root: sudo bash $0"; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"
DEB="${1:-$(ls "$HERE"/../dist/*.deb 2>/dev/null | head -n1)}"
[ -f "$DEB" ] || { echo "No .deb found. Build it first: cd kiosk && npm install && npm run dist"; exit 1; }

apt-get update
apt-get install -y cage dbus-user-session speech-dispatcher espeak-ng
apt-get install -y "$DEB"

# Chromium SUID sandbox helper needs root ownership and mode 4755.
chown root:root /opt/QMMCRehab/chrome-sandbox
chmod 4755 /opt/QMMCRehab/chrome-sandbox

id kiosk >/dev/null 2>&1 || adduser --disabled-password --gecos "" kiosk
usermod -aG video,render,audio kiosk

install -m 644 "$HERE/cage@.service" /etc/systemd/system/cage@.service
install -m 644 "$HERE/cage.pam" /etc/pam.d/cage

systemctl daemon-reload
systemctl enable cage@tty1.service
systemctl set-default graphical.target

echo "Installed. Reboot to start the kiosk:  sudo reboot"
echo "Admin access after that: SSH, or Ctrl+Alt+Shift+Q inside the app to quit it (the service restarts it)."
