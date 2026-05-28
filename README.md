# CatchingApril

Tiny system that polls April's AirTag through Apple's Find My network, stores location
reports in SQLite, and renders her daily trail on Google Maps.

```
poller.py  ──►  tracks.db  ──►  server.py  ──►  map.html
```

---

## 0. Prerequisites

- Python 3.10+ (we install 3.12 via [uv](https://docs.astral.sh/uv/) in step 1)
- An always-on host for the poller and server. Default is a **Mac mini**
  (macOS 15); any always-on Linux box (Pi, NAS, old laptop) works too.
- Brief one-time access to a Mac signed into your Apple ID (FindMy.app must see the AirTag).
  The Mac mini itself is fine for this step as long as it's on macOS 14 or 15.
- A Google Maps JavaScript API key with the **Maps JavaScript API** enabled.
  (The `visualization` library used for the heatmap is loaded client-side via
  `libraries=visualization` in the script URL — it's not a separate API to
  enable in the Cloud Console.)

## 1. Install uv and Python 3.12

We use [uv](https://docs.astral.sh/uv/) (from Astral) for Python and venv
management — faster than pip and replaces `pyenv` + `venv` + `pip` in one tool.

```bash
brew install uv
uv python install 3.12
uv venv --python 3.12               # creates .venv/
source .venv/bin/activate
uv pip install -r requirements.txt  # installs findmy, aiohttp, flask
```

`pip install -r requirements.txt` still works as a fallback if you don't want
uv.

## 2. One-time AirTag key dump (on the Mac)

```bash
uv pip install findmy                 # or: pip install findmy
python -m findmy util dump-keys -o ./devices
# pops an interactive keychain password prompt — that's expected
```

Copy `./devices/<your-airtag>.json` to the project folder as `airtag.json` next to `poller.py`.

> Heads-up: macOS 26 ("Sequoia") locks the BeaconStoreKey even with SIP off. If you're on
> 26, borrow a Mac on 14/15 for this step, or use the beaconstorekey-extractor utility
> referenced in the FindMy.py docs.

## 3. Anisette server (one-liner)

Runs in Docker on the host. On the Mac mini, install **Docker Desktop** first.

```bash
docker run -d --restart always --name anisette \
  -p 6969:6969 dadoum/anisette-v3-server
```

## 4. Configure & run the poller

```bash
cp .env.example .env                 # then edit .env with real creds
set -a; source .env; set +a          # export the vars into this shell
python poller.py                     # uses the venv from step 1
# first run will prompt for a 2FA code; session cached to account.json
```

Leave it running. It writes to `tracks.db` every 2 minutes.

### Run it as a service

**Mac mini (launchd)** — the default. A `LaunchAgent` plist will live at
`~/Library/LaunchAgents/com.catchingapril.poller.plist`; see [the launchd
section below](#launchd-plist-mac-mini) once we add the actual file to the
repo.

**Linux (systemd)** — alternate host reference, kept here in case the project
later moves to a Pi/NAS:

```ini
# /etc/systemd/system/catchingapril.service
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

## 5. Run the web app

```bash
python server.py
# open http://localhost:5000 on the Mac mini
# or http://<mac-mini-tailnet-name>:5000 from your phone over Tailscale
```

The Flask app has **no authentication** and shouldn't be exposed to the public
internet. Hosting plan is **Tailscale only** — install the tailnet on the Mac
mini and on your phone, then hit the tailnet hostname from anywhere. Don't
port-forward `5000`.

Paste your Google Maps key into `map.html` (two places: the `GOOGLE_MAPS_KEY` constant
**and** the `<script src=…>` URL near the bottom).

## 6. Cat-specific notes

- **Breakaway collar only.** Non-negotiable for outdoor cats.
- The AirTag updates only when a passing iPhone reports it — expect 1–5 min gaps in busy
  areas, longer (or nothing) in quiet alleys. The "path" view will sometimes draw a
  straight line across blocks where there was no relay; that's the data, not a bug.
- After ~24 h of being away from you, the tag will start chirping and pinging nearby
  iPhones with an "AirTag found moving with you" alert. Neighbors may see it.
- Battery (CR2032) lasts ~12 months. Drop a Calendar reminder.

## 7. Where to grow this

- **Geofence alerts**: trigger a push notification (e.g. via ntfy.sh) when she crosses
  outside a polygon around the yard.
- **Per-day playback**: animate the marker along the polyline using a time slider.
- **Time-of-day heatmaps**: separate maps for morning vs evening prowls.
- **Multiple tags**: drop more `airtag*.json` files into the folder and key the DB on
  device id; useful if you ever add a second cat.
