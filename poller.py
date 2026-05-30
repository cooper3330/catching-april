"""
CatchingApril — poller.py

Background worker that polls April's AirTag via Apple's Find My network
and writes location reports into a local SQLite database.

Run this on a Raspberry Pi, NAS, or any always-on Linux box.

Requirements:
    pip install findmy aiohttp

One-time setup (must be done on a Mac, once):
    1. Make sure FindMy.app on the Mac sees your AirTag.
    2. Run: python -m findmy util dump-keys -o ./devices
       (see https://docs.mikealmel.ooo/FindMy.py for the current command)
    3. Copy ./devices/<your-airtag>.json to this folder as `airtag.json`.

Also needs an Anisette server running locally (Docker is easiest):
    docker run -d --restart always --name anisette -p 6969:6969 \
        dadoum/anisette-v3-server
"""
import asyncio
import json
import logging
import os
import sqlite3
from datetime import timezone
from pathlib import Path

from findmy import FindMyAccessory
from findmy.reports import RemoteAnisetteProvider, AsyncAppleAccount

# ---------- CONFIG ----------
APPLE_EMAIL    = os.environ.get("APPLE_EMAIL", "you@example.com")
APPLE_PASSWORD = os.environ.get("APPLE_PASSWORD", "change-me")
ANISETTE_URL   = os.environ.get("ANISETTE_URL", "http://localhost:6969")
AIRTAG_JSON    = Path("airtag.json")        # dumped from a Mac, see header
ACCOUNT_STATE  = Path("account.json")       # cached login (so 2FA only happens once)
DB_PATH        = Path("tracks.db")
POLL_SECONDS   = 120                        # ~2 min; AirTag relays update ~1–5 min
# Note: findmy 0.10's fetch_location_history hardcodes a 7-day lookback —
# there's no public API to narrow the window. INSERT OR IGNORE dedupes the
# repeats, so this is wasteful network-wise but functionally correct.

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
log = logging.getLogger("catchingapril")


def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS locations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT    NOT NULL,           -- ISO 8601 UTC
            lat         REAL    NOT NULL,
            lon         REAL    NOT NULL,
            accuracy_m  REAL,
            status      INTEGER,
            UNIQUE(ts, lat, lon)                     -- dedupe identical reports
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON locations(ts)")
    conn.commit()
    return conn


async def get_account(anisette: RemoteAnisetteProvider) -> AsyncAppleAccount:
    """Restore cached Apple session written by `login.py`.

    First-time 2FA is handled by `login.py` (a separate one-shot script) so
    this daemon never needs to do interactive prompts. In findmy 0.10,
    `from_json` reads the anisette provider config from the saved state, so
    the `anisette` arg here is unused on the restore path — kept on the
    signature for symmetry with `main()`.
    """
    if not ACCOUNT_STATE.exists():
        raise SystemExit(
            f"Missing {ACCOUNT_STATE} — run `python login.py` once to do the "
            "one-time 2FA login, then re-run poller.py."
        )

    log.info("Restoring cached Apple account session from %s…", ACCOUNT_STATE)
    del anisette  # unused on the restore path; provider comes from the JSON
    return AsyncAppleAccount.from_json(ACCOUNT_STATE)


async def poll_once(account: AsyncAppleAccount,
                    airtag: FindMyAccessory,
                    conn: sqlite3.Connection) -> None:
    reports = await account.fetch_location_history(airtag)

    inserted = 0
    for r in reports:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO locations (ts, lat, lon, accuracy_m, status) "
                "VALUES (?, ?, ?, ?, ?)",
                (r.timestamp.astimezone(timezone.utc).isoformat(),
                 r.latitude, r.longitude,
                 getattr(r, "horizontal_accuracy", None),
                 getattr(r, "status", None)),
            )
            if conn.total_changes:
                inserted += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("Insert failed: %s", exc)
    conn.commit()
    log.info("Fetched %d reports, %d new", len(reports), inserted)


async def main() -> None:
    if not AIRTAG_JSON.exists():
        raise SystemExit(f"Missing {AIRTAG_JSON} — dump it from a Mac first (see header).")

    conn = init_db()
    anisette = RemoteAnisetteProvider(ANISETTE_URL)
    account  = await get_account(anisette)

    with AIRTAG_JSON.open("r") as f:
        airtag = FindMyAccessory.from_json(json.load(f))

    # In findmy 0.10 the name attr exists but is often None on dumped tags;
    # fall back to "(unnamed)" so the log line stays readable.
    log.info("Poller started for AirTag: %s", getattr(airtag, "name", None) or "(unnamed)")
    while True:
        try:
            await poll_once(account, airtag, conn)
        except Exception as exc:  # noqa: BLE001
            log.exception("Poll cycle failed: %s", exc)
        await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
