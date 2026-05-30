"""
CatchingApril — server.py

Tiny Flask app that serves the map page and exposes location data as JSON.
Pair with poller.py writing into the same tracks.db.

    pip install flask
    python server.py
    # → open http://localhost:5001/

Port defaults to 5001 because macOS uses :5000 for AirPlay Receiver out
of the box (`Address already in use`). Override with the PORT env var:
    PORT=8080 python server.py
"""
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template, request

DB_PATH          = Path("tracks.db")
APP_DIR          = Path(__file__).parent
PORT             = int(os.environ.get("PORT", "5001"))
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

app = Flask(__name__)


def query(start_iso: str, end_iso: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT ts, lat, lon, accuracy_m FROM locations "
        "WHERE ts BETWEEN ? AND ? ORDER BY ts ASC",
        (start_iso, end_iso),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.route("/")
def index():
    return render_template("map.html", google_maps_key=GOOGLE_MAPS_API_KEY)


@app.route("/api/locations")
def locations():
    # Default window: last 24 hours
    now = datetime.now(timezone.utc)
    end_iso   = request.args.get("end")   or now.isoformat()
    start_iso = request.args.get("start") or (now - timedelta(hours=24)).isoformat()
    return jsonify({
        "start": start_iso,
        "end":   end_iso,
        "points": query(start_iso, end_iso),
    })


@app.route("/api/days")
def days():
    """List dates that have data, for a date-picker dropdown."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT DISTINCT substr(ts, 1, 10) AS d FROM locations ORDER BY d DESC"
    ).fetchall()
    conn.close()
    return jsonify([r[0] for r in rows])


if __name__ == "__main__":
    # 0.0.0.0 so you can view from your phone over Tailscale.
    # Keep this OFF the public internet — there's no auth on the data.
    app.run(host="0.0.0.0", port=PORT, debug=False)
