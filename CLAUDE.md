# CatchingApril

Polls April's AirTag through Apple's Find My network, stores reports in SQLite,
and renders her daily trail on Google Maps.

## Architecture

Three processes on one always-on Linux box (Pi / NAS / old laptop):

```
poller.py  ──►  tracks.db  ──►  server.py  ──►  map.html
   ▲                              (Flask)        (vanilla JS,
   │                                              Google Maps JS)
Anisette
(Docker)
```

- **poller.py** — async worker. Loops every `POLL_SECONDS` (default 120s),
  pulls the last `LOOKBACK_HOURS` of reports from Find My via `findmy.py`,
  and `INSERT OR IGNORE`s them into `locations`. Caches the Apple session in
  `account.json` so 2FA only happens once.
- **tracks.db** — SQLite. Single table `locations(id, ts, lat, lon, accuracy_m, status)`
  with a UNIQUE constraint on `(ts, lat, lon)` for dedupe and an index on `ts`.
  Timestamps are ISO 8601 UTC strings.
- **server.py** — Flask. Serves `map.html` at `/`, exposes `/api/locations?start=&end=`
  (defaults to last 24h) and `/api/days`. Read-only; no auth, no writes.
- **map.html** — single-page UI. Path / Heatmap / Pings modes, plus a playback
  scrubber that animates a dot along the day's polyline.
- **Anisette server** — runs as a Docker container (`dadoum/anisette-v3-server`)
  on the same box. `findmy.py` needs it to talk to Apple.

## Key caveat: macOS 26 AirTag key dump

The one-time `python -m findmy util dump-keys` step **must** be run on a Mac
that's signed into the Apple ID FindMy.app uses to see the AirTag. On
**macOS 26 ("Sequoia")** the BeaconStoreKey is locked down even with SIP
disabled — the dump will fail.

Workarounds:
1. Borrow a Mac on **macOS 14 or 15** for the one-time dump, OR
2. Use the **beaconstorekey-extractor** utility referenced in the FindMy.py docs.

After the dump, copy `devices/<airtag>.json` to the Linux box as `airtag.json`
next to `poller.py`. The Linux box never needs a Mac after that.

## Hosting plan: Tailscale, not public internet

`server.py` binds `0.0.0.0:5000` and has **no authentication**. The plan is to
expose it only over **Tailscale** — install the tailnet on the Pi and on the
phone, then hit `http://<pi-tailnet-name>:5000` from anywhere.

Do not port-forward `5000` or stick this behind a public reverse proxy without
adding auth first. Cat location history is sensitive and the API is wide open.

## Conventions

**Python**
- Python 3.10+. Standard library first; only outside deps are `findmy`,
  `aiohttp`, `flask` (see `requirements.txt`).
- Configuration via environment variables with sensible defaults
  (`os.environ.get("APPLE_EMAIL", "you@example.com")`). Real values live in
  `.env` (gitignored) or systemd `Environment=` lines.
- `pathlib.Path` for file paths, not string concatenation.
- Async only where it pays for itself (the poller). The Flask server is sync.
- Module docstring at the top of every file with a short "what / how to run"
  block — see `poller.py` and `server.py`.
- Broad `except Exception` is allowed in the poll loop with a `# noqa: BLE001`
  so one bad report doesn't kill the worker. Log and continue.
- SQLite directly via `sqlite3`. No ORM, no migration framework — schema lives
  in `init_db()` with `CREATE TABLE IF NOT EXISTS`.
- Timestamps are ISO 8601 UTC strings in the DB.

**Frontend**
- Vanilla JS, no build step, no framework. One HTML file.
- Dark theme via CSS custom properties on `:root`; the cat's trail is
  `--accent: #ff7a4a` (warm orange) everywhere.
- Google Maps JS API with the `visualization` library (for the heatmap).
  The key appears in **two places** in `map.html`: the `GOOGLE_MAPS_KEY`
  constant and the `<script src=…>` URL near the bottom. Keep them in sync.

**Data & privacy**
- `airtag.json`, `account.json`, `tracks.db`, and `.env` are secrets / PII.
  Never commit them — see `.gitignore`.
- Find My reports are sparse: 1–5 min gaps in busy areas, longer in quiet
  ones. The "path" view sometimes draws a straight line across blocks where
  no iPhone relayed — that's the data, not a bug. Don't smooth it out without
  flagging.

**Cat-specific**
- Breakaway collar only. Non-negotiable for an outdoor cat.
- After ~24h away from the owner, the AirTag chirps and pings nearby iPhones
  with an "AirTag found moving with you" alert. Expected.
- CR2032 battery lasts ~12 months.
