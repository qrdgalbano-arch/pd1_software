# QMMC Rehab Station - kiosk

Standalone, offline Linux kiosk for the Design C prototype. An Electron window loads the prototype from a private `app://` scheme (no web server, no browser UI). MediaPipe is served from `node_modules` and all other network requests are blocked. Cage (a Wayland kiosk compositor) makes it the only program the PC can show.

## 1. Test on a development PC
    cd kiosk
    npm install
    npm start            # kiosk window; admin exit: Ctrl+Alt+Shift+Q
    npm run debug        # same, with devtools and shortcuts enabled (KIOSK_DEBUG=1)

## 2. Build the installer (on Linux or WSL)
    cd kiosk
    npm install
    npm run dist         # creates kiosk/dist/*.deb

The .deb contains the prototype, the pose model, the avatar and the Three.js files, so the app needs no internet.

## 3. Install on the Mini PC (Ubuntu/Debian, systemd)
Copy the repo (or just `kiosk/`) and the .deb to the PC, then:

    sudo bash kiosk/deploy/install-kiosk.sh kiosk/dist/<file>.deb
    sudo reboot

The script installs Cage and the speech packages, installs the .deb to `/opt/QMMCRehab`, creates a password-less `kiosk` user (groups: video, render, audio), and enables `cage@tty1.service`, which starts the app at boot and restarts it if it exits.

## Maintenance
- SSH in (key login recommended). Logs: `journalctl -u cage@tty1 -b`.
- Stop the kiosk: `sudo systemctl stop cage@tty1`. Start it: `sudo systemctl start cage@tty1`.
- Undo: `sudo systemctl disable cage@tty1 && sudo systemctl set-default multi-user.target`.

## Notes / not yet verified
- Untested on the target hardware. Check after the first reboot: the app starts by itself, the camera opens, the 3D avatar renders (needs a working GPU driver), and it works with the network unplugged.
- Voice uses the system speech engine (espeak-ng by default, which sounds robotic). Pre-recorded prompts would sound clearer.
- Camera access is granted automatically to the app only; every other permission is denied.
- BIOS: boot from the internal drive only and set an admin password.
- Change the screen/sleep settings so the display does not blank during sessions.
