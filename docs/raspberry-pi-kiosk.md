# Raspberry Pi Kiosk Setup Guide

This guide prepares a Raspberry Pi to act only as a fullscreen browser display for Sidecar Deck. The backend stays on the homelab server. The Raspberry Pi does not run Docker, collect PC metrics, or host the API.

Target setup:

```text
Raspberry Pi OS Desktop
  -> auto-login desktop session
  -> Chromium kiosk mode
  -> http://homelab.local:8080
  -> 1920x480 ultrawide monitor
```

## Hardware

Recommended:

- Raspberry Pi 3, 4, or 5
- Official or high-quality power supply
- Reliable microSD card, 16 GB or larger
- Ethernet if available, otherwise stable Wi-Fi
- 8-inch `1920x480` HDMI display

The dashboard is lightweight enough for a Raspberry Pi 3, but a Pi 4 or Pi 5 gives smoother Chromium startup and better long-term kiosk reliability.

## 1. Install Raspberry Pi OS

Use Raspberry Pi Imager from another computer.

1. Choose the Pi model.
2. Choose **Raspberry Pi OS 64-bit with desktop**.
3. Open OS customization and set:
   - Hostname: `sidecar-deck-kiosk`
   - Username/password
   - Wi-Fi credentials, if not using Ethernet
   - Locale, keyboard, and timezone
   - SSH enabled, recommended for maintenance
4. Write the image to the microSD card.
5. Boot the Raspberry Pi with the kiosk display attached.

Use the Desktop image, not Lite, because this guide relies on Chromium and the standard desktop session.

## 2. Update the Pi

SSH into the Pi or open a terminal on the desktop:

```bash
sudo apt update
sudo apt -y full-upgrade
sudo reboot
```

After reboot, confirm Chromium exists:

```bash
command -v chromium || command -v chromium-browser
```

Most current Raspberry Pi OS Desktop installs provide Chromium by default.

## 3. Confirm Dashboard Access

Make sure the homelab container is running:

```bash
docker compose --env-file backend/.env up -d
```

From the Raspberry Pi:

```bash
curl http://homelab.local:8080/health
```

Expected response:

```json
{"status":"ok"}
```

If `homelab.local` does not resolve, use the homelab server IP address instead:

```text
http://192.168.1.50:8080
```

Use that same URL in the kiosk script below.

## 4. Set Display Resolution

Open the Raspberry Pi display settings and choose `1920x480` if it appears.

If the display does not expose the mode correctly, create a `cmdline.txt` backup:

```bash
sudo cp /boot/firmware/cmdline.txt /boot/firmware/cmdline.txt.bak
```

Then inspect connected display names:

```bash
wlr-randr
```

If `wlr-randr` is not installed:

```bash
sudo apt -y install wlr-randr
```

Set the mode for the connected HDMI output, replacing `HDMI-A-1` if your output name differs:

```bash
wlr-randr --output HDMI-A-1 --mode 1920x480
```

If the command works, add it to the kiosk autostart file in the next step before Chromium starts.

## 5. Disable Screen Blanking

Disable screen blanking from the Raspberry Pi configuration tool:

```bash
sudo raspi-config
```

Use:

```text
Display Options -> Screen Blanking -> No
```

Reboot after changing this setting:

```bash
sudo reboot
```

## 6. Create the Kiosk Launch Script

Create a script:

```bash
nano ~/sidecar-deck-kiosk.sh
```

Paste this, changing `DASHBOARD_URL` if needed:

```bash
#!/bin/bash
set -e

DASHBOARD_URL="http://homelab.local:8080"

# Give networking and the desktop session a moment to settle.
sleep 8

# Optional: force the ultrawide mode if the display does not pick it automatically.
# Replace HDMI-A-1 with the output name from `wlr-randr`.
# wlr-randr --output HDMI-A-1 --mode 1920x480 || true

while true; do
  if command -v chromium >/dev/null 2>&1; then
    BROWSER=chromium
  else
    BROWSER=chromium-browser
  fi

  "$BROWSER" "$DASHBOARD_URL" \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --no-first-run \
    --password-store=basic \
    --disable-session-crashed-bubble \
    --disable-features=TranslateUI \
    --enable-features=OverlayScrollbar \
    --start-maximized

  sleep 5
done
```

Make it executable:

```bash
chmod +x ~/sidecar-deck-kiosk.sh
```

## 7. Autostart Chromium

Current Raspberry Pi OS desktop releases use `labwc` for Wayland sessions. Create the autostart directory:

```bash
mkdir -p ~/.config/labwc
```

Edit the autostart file:

```bash
nano ~/.config/labwc/autostart
```

Add:

```bash
~/sidecar-deck-kiosk.sh &
```

Save, then reboot:

```bash
sudo reboot
```

After the desktop loads, Chromium should open directly to the dashboard in fullscreen kiosk mode.

## 8. Optional Boot Polish

These are optional. The kiosk works without them.

Hide the mouse cursor after a short idle period:

```bash
sudo apt -y install unclutter
```

Add this line before the kiosk script in `~/.config/labwc/autostart`:

```bash
unclutter -idle 1 &
```

Reduce browser cache writes:

```bash
mkdir -p ~/.config/chromium-flags.conf.d
nano ~/.config/chromium-flags.conf.d/sidecar-deck.conf
```

Add:

```text
--disk-cache-size=33554432
```

## 9. Maintenance Commands

Restart the kiosk browser:

```bash
pkill chromium || pkill chromium-browser
```

The loop in `sidecar-deck-kiosk.sh` will reopen Chromium after a few seconds.

View recent boot/session logs:

```bash
journalctl --user -b --no-pager | tail -100
```

Check dashboard health:

```bash
curl http://homelab.local:8080/health
```

Update the Pi:

```bash
sudo apt update
sudo apt -y full-upgrade
sudo reboot
```

## 10. Troubleshooting

### Chromium does not start after boot

Run the script manually:

```bash
~/sidecar-deck-kiosk.sh
```

If it works manually, inspect:

```bash
cat ~/.config/labwc/autostart
```

Make sure the autostart line ends with `&`.

### Dashboard shows disconnected

The page loaded, but WebSocket updates are not reaching the browser. Check:

```bash
curl http://homelab.local:8080/api/metrics/latest
```

Also verify the homelab firewall allows TCP port `8080` from the LAN.

### Dashboard URL does not resolve

Use the homelab server IP address instead of `homelab.local` in `~/sidecar-deck-kiosk.sh`.

### Display is the wrong size

Run:

```bash
wlr-randr
```

Confirm the connected output name and supported modes. If `1920x480` is listed, add the matching `wlr-randr --output ... --mode 1920x480` command to `~/sidecar-deck-kiosk.sh`.

### The browser shows a restore prompt

The kiosk launch flags include `--disable-session-crashed-bubble`, but Chromium profile state can still occasionally get messy after power loss. Reset the kiosk browser profile:

```bash
pkill chromium || true
mv ~/.config/chromium ~/.config/chromium.bak.$(date +%Y%m%d-%H%M%S)
sudo reboot
```

### Chromium asks for a keyring password

Chromium can show a keyring password dialog on first launch. For a kiosk device, launch Chromium with the basic password store so it does not try to unlock the desktop keyring.

From SSH, add the flag to the kiosk script:

```bash
grep -q -- '--password-store=basic' ~/sidecar-deck-kiosk.sh || \
  sed -i '/--no-first-run \\/a\    --password-store=basic \\' ~/sidecar-deck-kiosk.sh
```

Then restart Chromium:

```bash
pkill chromium || pkill chromium-browser || true
```

The launch loop will reopen Chromium after a few seconds. If the dialog is still visible, reboot:

```bash
sudo reboot
```

## Final Checklist

- Raspberry Pi OS 64-bit Desktop installed
- SSH enabled for maintenance
- Pi can reach `http://homelab.local:8080/health`
- Screen blanking disabled
- Display is set to `1920x480`
- `~/sidecar-deck-kiosk.sh` is executable
- `~/.config/labwc/autostart` launches the script with `&`
- Reboot opens the dashboard automatically
