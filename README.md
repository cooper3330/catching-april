# CatchingApril

Tiny system that polls April's AirTag through Apple's Find My network, stores location
reports in SQLite, and renders her daily trail on Google Maps.

```
poller.py  ──►  tracks.db  ──►  server.py  ──►  map.html
```

---

## 0. Prerequisites

- Python 3.10+
- An always-on Linux box (Pi, NAS, old laptop) for the poller and server
- Brief one-time access to a Mac signed into your Apple ID (FindMy.app must see the AirTag)
- A Google Maps JavaScript API key with the **Maps JavaScript API** and **Maps JavaScript
  API – Visualization library** enabled

## 1. One-time AirTag key dump (on the Mac)

```bash
pip install findmy
python -m findmy util dump-keys -o ./devices
# pops an interactive keychain password prompt — that's expected
```

Copy `./devices/<your-airtag>.json` to the Linux box as `airtag.json` next to `poller.py`.

> Heads-up: macOS 26 ("Sequoia") locks the BeaconStoreKey even with SIP off. If you're on
> 26, borrow a Mac on 14/15 for this step, or use the beaconstorekey-extractor utility
> referenced in the FindMy.py docs.

## 2. Anisette server (one-liner, on the Linux box)

```bash
docker run -d --restart always --name anisette \
  -p 6969:6969 dadoum/anisette-v3-server
```

## 3. Configure & run the poller

```bash
pip install findmy aiohttp flask
export APPLE_EMAIL="you@example.com"
export APPLE_PASSWORD="…"
python poller.py
# first run will prompt for a 2FA code; session cached to account.json
```

Leave it running. It writes to `tracks.db` every 2 minutes.

### Run it as a service (systemd)

`/etc/systemd/system/catchingapril.service`:

```ini
[Unit]
Description=CatchingApril — AirTag poller
After=network-online.target docker.service

[Service]
WorkingDirectory=/home/kyle/catchingapril
Environment=APPLE_EMAIL=you@example.com
Environment=APPLE_PASSWORD=…
ExecStart=/usr/bin/python3 poller.py
Restart=on-failure
RestartSec=10
User=kyle

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now catchingapril
journalctl -u catchingapril -f
```

## 4. Run the web app

```bash
python server.py
# open http://<pi-ip>:5000 from your phone on the home wifi
```

Paste your Google Maps key into `map.html` (two places: the `GOOGLE_MAPS_KEY` constant
**and** the `<script src=…>` URL near the bottom).

## 5. Cat-specific notes

- **Breakaway collar only.** Non-negotiable for outdoor cats.
- The AirTag updates only when a passing iPhone reports it — expect 1–5 min gaps in busy
  areas, longer (or nothing) in quiet alleys. The "path" view will sometimes draw a
  straight line across blocks where there was no relay; that's the data, not a bug.
- After ~24 h of being away from you, the tag will start chirping and pinging nearby
  iPhones with an "AirTag found moving with you" alert. Neighbors may see it.
- Battery (CR2032) lasts ~12 months. Drop a Calendar reminder.

## 6. Where to grow this

- **Geofence alerts**: trigger a push notification (e.g. via ntfy.sh) when she crosses
  outside a polygon around the yard.
- **Per-day playback**: animate the marker along the polyline using a time slider.
- **Time-of-day heatmaps**: separate maps for morning vs evening prowls.
- **Multiple tags**: drop more `airtag*.json` files into the folder and key the DB on
  device id; useful if you ever add a second cat.
