# CatchingApril

Polls April's AirTag through Apple's Find My network, stores reports in SQLite,
and renders her daily trail on Google Maps.

## Architecture

Three processes on one always-on host — currently a **Mac mini** (macOS 15):

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
  on the same box (Docker Desktop on the Mac mini). `findmy.py` needs it to
  talk to Apple.
- **Process supervision** — on the Mac mini this means **launchd**
  (`~/Library/LaunchAgents/*.plist`), not systemd. The README's systemd unit
  is alternate-host reference only.

## Key caveat: AirTag key dump (BeaconStoreKey lockdown)

The one-time `python -m findmy decrypt --out-dir ./devices` step **must** be
run on a Mac that's signed into the Apple ID FindMy.app uses to see the
AirTag. Apple has progressively locked down the `BeaconStoreKey` so the
`security` CLI can no longer read it — findmy's decrypt fails with a
`ValueError` when this happens.

> The findmy CLI renamed `util dump-keys -o` → `decrypt --out-dir` in 0.10.
> Both names accomplish the same thing; the new one is what's pinned in
> `requirements.txt`.

**Affected OS versions (empirically confirmed or documented):**

- **macOS 15.7.7** (our Mac mini, 2026-05-28) — locked down. `BeaconStore`
  keychain entry isn't reachable via `security find-generic-password` on
  either login or System keychain, despite FindMy.app working normally and
  `~/Library/com.apple.icloud.searchpartyd/OwnedBeacons/` being populated.
  Apple appears to have backported the protection into recent 15.x point
  releases.
- **macOS 26** — fully locked; disabling SIP is not sufficient (per
  FindMy.py issue #176).
- **macOS 14 and pre-15.7 15.x** — believed to still work with the standard
  `findmy decrypt` flow.

**Workarounds, in order of preference:**

1. **Use another Mac on macOS 14 or pre-15.7 15.x** for the one-time dump.
   This is by far the simplest — no SIP changes, no security tradeoffs on
   the always-on box.
2. **Patched `pajowu/beaconstorekey-extractor`** on the affected Mac —
   purpose-built for this. A small Swift binary that claims the searchparty
   keychain-access-group entitlement and reads the `BeaconStore` keychain
   item via `SecItemCopyMatching`. Requires SIP **and** AMFI disabled
   (three reboots) but **no Apple Developer ID** — override the Makefile
   with `make run DEVELOPER_ID=-` to use ad-hoc signing, which AMFI-off
   permits. Ships `make decrypt` to decrypt every `OwnedBeacons/*.record`
   in one pass.

   **One-line patch required on 15.7+:** add
   `kSecAttrSynchronizable: kSecAttrSynchronizableAny` to the
   `SecItemCopyMatching` query, because the `BeaconStore` keychain item
   has moved to the **iCloud keychain** (synchronizable) on Sequoia
   point releases — the default query only returns local items and
   returns `errSecItemNotFound` otherwise. The README's "BeaconStoreKey
   lockdown workaround" section has the exact `sed` command and the
   full procedure.

> **Wrong-tool footnote (learned the hard way 2026-05-30):**
> `manonstreet/findmy-key-extractor` looks like the right tool but
> isn't — it only extracts `LocalStorage.key` (the SQLite key for
> `findmylocateagent`'s DB) and the FMIP/FMF service keys. It hooks
> `SecItemCopyMatching` inside `FindMy.app` and filters by `svce`
> attribute, but the `BeaconStore` read happens inside
> `searchpartyuseragent`, not `FindMy.app`. Using `LocalStorage.key` to
> decrypt `OwnedBeacons/*.record` fails with `cryptography.exceptions.InvalidTag`.

After the dump, copy `devices/<airtag>.json` to the Mac mini as `airtag.json`
next to `poller.py`. The Mac mini never needs a Mac signed into iCloud after
that — the poller talks to Apple's servers via Anisette using the dumped
key.

## Hosting plan: Tailscale, not public internet

`server.py` binds `0.0.0.0:5000` and has **no authentication**. The plan is to
expose it only over **Tailscale** — install the tailnet on the Pi and on the
phone, then hit `http://<pi-tailnet-name>:5000` from anywhere.

Do not port-forward `5000` or stick this behind a public reverse proxy without
adding auth first. Cat location history is sensitive and the API is wide open.

## Documentation hygiene

**Keep `README.md` in sync with the codebase as work progresses.** Whenever a
change affects setup, architecture, the host machine, dependencies, run
commands, or environment variables, update the README in the same change.

The README is the install/run guide; CLAUDE.md is the architectural context.
When a decision is captured here (host, hosting model, conventions), make sure
the operational consequence is reflected in the README — and vice versa.
If they disagree, fix them both before moving on.

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
