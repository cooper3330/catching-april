"""
CatchingApril — login.py

One-time interactive login helper. Run this *once* with valid Apple
credentials in env vars to do the 2FA dance and cache the session to
`account.json`. After that, `poller.py` restores the cached session on
every restart — no 2FA needed.

Usage:
    set -a; source .env; set +a
    python login.py

Prereqs:
    - Anisette server running (see README §3).
    - Apple ID has 2FA enabled (it does for any modern Apple account).
    - Access to a trusted device or phone to receive the 6-digit code.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from findmy.reports import AsyncAppleAccount, RemoteAnisetteProvider
from findmy.reports.state import LoginState

APPLE_EMAIL    = os.environ.get("APPLE_EMAIL", "you@example.com")
APPLE_PASSWORD = os.environ.get("APPLE_PASSWORD", "change-me")
ANISETTE_URL   = os.environ.get("ANISETTE_URL", "http://localhost:6969")
ACCOUNT_STATE  = Path("account.json")


async def main() -> int:
    if APPLE_EMAIL == "you@example.com" or APPLE_PASSWORD == "change-me":
        print(
            "APPLE_EMAIL / APPLE_PASSWORD not set — copy .env.example to .env, "
            "fill in real credentials, then `set -a; source .env; set +a`.",
            file=sys.stderr,
        )
        return 1

    anisette = RemoteAnisetteProvider(ANISETTE_URL)
    acct = AsyncAppleAccount(anisette)

    print(f"Logging in as {APPLE_EMAIL}…")
    state = await acct.login(APPLE_EMAIL, APPLE_PASSWORD)
    print(f"  login state: {state.name}")

    if state == LoginState.REQUIRE_2FA:
        methods = await acct.get_2fa_methods()
        if not methods:
            print("Account requires 2FA but no methods available.", file=sys.stderr)
            return 1

        print("\nAvailable 2FA methods:")
        for i, m in enumerate(methods):
            print(f"  [{i}] {m}")

        choice = input(f"\nChoose method [0-{len(methods) - 1}] (default 0): ").strip() or "0"
        try:
            method = methods[int(choice)]
        except (ValueError, IndexError):
            print(f"Invalid choice: {choice!r}", file=sys.stderr)
            return 1

        print(f"Requesting code via {method}…")
        await method.request()
        code = input("Enter the 6-digit 2FA code: ").strip()
        state = await method.submit(code)
        print(f"  after 2FA submit, state: {state.name}")

    if state not in (LoginState.AUTHENTICATED, LoginState.LOGGED_IN):
        print(f"Login did not complete; final state: {state.name}", file=sys.stderr)
        return 1

    ACCOUNT_STATE.write_text(json.dumps(acct.export()))
    print(f"\nSaved session to {ACCOUNT_STATE}")
    print("Next: `python poller.py` to start the polling loop.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
