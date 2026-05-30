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

## 2. One-time AirTag key dump (on a Mac)

`findmy` reads the local FindMy.app plists, decrypts them via the system
keychain, and writes one JSON file per paired accessory (AirTag, MacBook,
AirPods, etc.) into the out-dir.

> **⚠️ macOS version matters.** Apple has locked down the `BeaconStoreKey`
> in recent macOS releases — the `findmy decrypt` command fails with a
> `ValueError` because the `security` CLI can't read the key anymore. As of
> May 2026, we've empirically confirmed **macOS 15.7.7 is locked down**, and
> **macOS 26** is fully locked (disabling SIP doesn't help). Use a Mac on
> **macOS 14 or a pre-15.7 release of 15.x** for this step. If you only
> have a locked-down Mac, see the [BeaconStoreKey lockdown
> section](#beaconstorekey-lockdown-workaround) below.

```bash
# findmy is already installed in the venv from step 1
python -m findmy decrypt --out-dir ./devices
# pops an interactive keychain password prompt — that's expected
```

Find April's file in `./devices/` and copy it to the project folder on the
Mac mini as `airtag.json` next to `poller.py`:

```bash
ls devices/
cp devices/<april-file>.json airtag.json
```

> **CLI changed in findmy 0.10.** The old `util dump-keys -o ./devices`
> subcommand was replaced by `decrypt --out-dir ./devices`. Same purpose,
> different name. If you copy/paste from an older guide and see `invalid
> choice: 'util'`, that's why.

### BeaconStoreKey lockdown workaround

If `findmy decrypt` fails with a `ValueError` referencing
`_parse_beaconstore_key_from_*_output`, the `BeaconStore` keychain entry
isn't reachable on that Mac. Two options:

1. **Easier:** find another Mac on macOS 14 or pre-15.7 15.x and run the
   dump there. No security changes needed; you only need the resulting
   `airtag.json` back on the Mac mini.
2. **Harder (no other Mac available):** build and run a patched
   `pajowu/beaconstorekey-extractor` below. Requires temporarily disabling
   SIP **and** AMFI on the affected Mac, plus a **one-line patch** to make
   it search the iCloud keychain (where Sequoia stores the item) instead
   of the local one. **No Apple Developer ID** — ad-hoc codesigning
   (`DEVELOPER_ID=-`) is sufficient once AMFI is off.

> **Why the patch:** on macOS 15.7+, `BeaconStore` lives in the **iCloud
> keychain** (synced), not the local keychain. By default
> `SecItemCopyMatching` only returns non-synchronizable items, so upstream
> pajowu's query returns `errSecItemNotFound` even with the entitlement
> and AMFI off. You can verify by opening Keychain Access and searching
> for `beacon` — the `BeaconStore` entry shows under "iCloud", not
> "login". Adding `kSecAttrSynchronizable: kSecAttrSynchronizableAny` to
> pajowu's query fixes this; the patch is in step 4.

> **Tool choice (learned the hard way):** the obvious-looking
> [`manonstreet/findmy-key-extractor`][mks] is **not** the right tool —
> it extracts `LocalStorage.key`, `FMIPDataManager.bplist`, and
> `FMFDataManager.bplist` (Find My iPhone / Friends keys), and skips the
> `BeaconStoreKey` entirely. Trying to decrypt `OwnedBeacons/*.record`
> with `LocalStorage.key` fails with
> `cryptography.exceptions.InvalidTag`. Use
> [`pajowu/beaconstorekey-extractor`][bske] instead — it specifically
> reads the `BeaconStore` keychain item via the searchparty keychain
> access group.

[bske]: https://github.com/pajowu/beaconstorekey-extractor
[mks]: https://github.com/manonstreet/findmy-key-extractor

#### Full extraction procedure (Apple Silicon Mac)

Risk callouts before you start:

- While SIP is off and AMFI is bypassed, **Gatekeeper, library
  validation, and kext signing are all disabled**. Treat the Mac as
  untrusted: disconnect from networks, don't open Mail, don't run
  unknown installers.
- The extraction itself is read-only against `searchpartyd`'s data.
  Partial failure is safe to revert (`csrutil enable` + clear
  `boot-args` + reboot puts you back to a normal Mac).
- Total time: ~15 minutes including three reboots.

**1. Disable SIP from Recovery.** Shut down, hold the power button until
"Loading startup options" appears, then **Options → Continue → Utilities
→ Terminal**:

```bash
csrutil disable
reboot
```

**2. Boot back to macOS and disable AMFI:**

```bash
csrutil status                                          # should say "disabled"
sudo nvram boot-args="amfi_get_out_of_my_way=1"
sudo reboot
```

**3. Verify both are off, then disconnect from the network:**

```bash
csrutil status                                          # "disabled"
nvram boot-args                                         # "amfi_get_out_of_my_way=1"
```

**4. Build and run the BeaconStoreKey extractor.**

```bash
xcode-select -p 2>/dev/null || xcode-select --install   # CLT must be present
cd ~/dev
git clone https://github.com/pajowu/beaconstorekey-extractor
cd beaconstorekey-extractor
```

**Apply the iCloud-keychain patch.** The upstream query only searches local
keychain items. Add `kSecAttrSynchronizable: kSecAttrSynchronizableAny`
to `beaconstorekey-extractor.swift` so it also searches iCloud-synced items:

```bash
# In-place patch — add the synchronizable line after kSecAttrService:
/usr/bin/sed -i '' '/kSecAttrService as String: "BeaconStore",/a\
                            kSecAttrSynchronizable as String: kSecAttrSynchronizableAny,
' beaconstorekey-extractor.swift

grep kSecAttrSynchronizable beaconstorekey-extractor.swift    # confirm patch landed
```

Then build, ad-hoc sign, and run:

```bash
# Ad-hoc signing (no Apple Developer ID needed when AMFI is off):
make run DEVELOPER_ID=-
```

The Swift binary calls `SecItemCopyMatching` for the `BeaconStore`
keychain item using the searchparty keychain-access-group entitlement.
Output ends with:

```
Found key in keychain:
<64 hex characters>            ← the BeaconStoreKey
```

Save the hex string to a file you'll reuse:

```bash
echo "<paste-the-hex>" > /tmp/bsk.hex
```

**5. Decrypt all owned beacons and identify April.** The extractor
ships `searchpartyd-decryptor.swift`, run via `make decrypt`. It reads
the key from stdin and writes decrypted plists to `$TMPDIR/com.apple.icloud.searchpartyd/`:

```bash
cat /tmp/bsk.hex | make decrypt
```

Then map UUIDs to names from the project venv:

```bash
cd /Users/kylecooper/dev/catching-april
source .venv/bin/activate
python3 - <<'PY'
import os, plistlib, glob
tmp = os.environ["TMPDIR"]
for f in sorted(glob.glob(f"{tmp}com.apple.icloud.searchpartyd/OwnedBeacons/*.plist")):
    with open(f, "rb") as fh:
        d = plistlib.load(fh)
    print(f"{os.path.basename(f)[:36]}  ->  {d.get('name', '(unnamed)')}")
PY
```

Find the line ending in `-> April` and note its UUID.

**6. Convert April's `.record` to `airtag.json`:**

```bash
cd ~/dev
git clone https://github.com/malmeloo/FindMy.py
cd FindMy.py && pip3 install -e .

python3 examples/plist_to_json.py \
  ~/Library/com.apple.icloud.searchpartyd/OwnedBeacons/<APRIL-UUID>.record \
  /Users/kylecooper/dev/catching-april/airtag.json \
  --alignment-plist ~/Library/com.apple.icloud.searchpartyd/BeaconNamingRecord/<APRIL-UUID>/*.record \
  --key-file /tmp/bsk.hex
```

(If `plist_to_json.py --help` shows different flag names, the inputs
are still: the `.record`, the output path, the matching naming
`.record`, and the key file.)

**7. Revert security:**

```bash
sudo nvram -d boot-args
sudo shutdown -h now
```

Then Recovery again → Utilities → Terminal:

```bash
csrutil enable
reboot
```

After reboot, confirm:

```bash
csrutil status                                          # "enabled"
nvram boot-args 2>&1                                    # error: data was not found  ← good
```

The error on `nvram boot-args` is the expected "no boot-args set"
message. The extracted key + `airtag.json` remain valid — they aren't
session-bound. You only need to redo this if you re-pair the AirTag.

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
