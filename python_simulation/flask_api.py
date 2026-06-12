"""
=============================================================================
Smart Waste Management & Bin Level Detection System
File: python_simulation/flask_api.py
Description:
    Lightweight Flask REST + Socket.IO API server that:
    - Runs the simulator in a background thread
    - Streams live readings to the dashboard via Socket.IO
    - Exposes REST endpoints for the dashboard to fetch historical data
    - Serves the dashboard HTML (optional)

    Start: python python_simulation/flask_api.py
    Dashboard: open dashboard/index.html in browser (file://)
              OR http://localhost:5000 (served by Flask)
=============================================================================
"""

import os
import sys
import json
import time
import threading
import csv
from datetime import datetime
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

# Add project root to path so sibling imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_simulation.smart_waste_simulator import (
    SmartBin, BinConfig, WasteFleetManager, CSVLogger,
    BIN_CONFIGS, CSV_LOG_PATH
)

# ─── App Setup ────────────────────────────────────────────────────────────────
app    = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), "..", "dashboard"))
CORS(app)

# Try to import socketio (optional — dashboard works fine via REST polling too)
try:
    from flask_socketio import SocketIO, emit
    socketio = SocketIO(app, cors_allowed_origins="*")
    SOCKETIO_AVAILABLE = True
except ImportError:
    socketio             = None
    SOCKETIO_AVAILABLE   = False

# ─── In-Memory State ──────────────────────────────────────────────────────────
_latest: dict   = {}         # bin_id → latest reading dict
_history: list  = []         # All readings (capped at 500)
_manager        = None
_lock           = threading.Lock()

MAX_HISTORY = 500

# ─── Background Simulation Thread ─────────────────────────────────────────────
def simulation_worker():
    """Runs the fleet simulation in a background thread, updating _latest."""
    global _manager
    logger   = CSVLogger(CSV_LOG_PATH)
    _manager = WasteFleetManager(logger)

    while True:
        readings = _manager.run_cycle()
        with _lock:
            for r in readings:
                d = r.as_dict()
                _latest[r.bin_id] = d
                _history.append(d)
                if len(_history) > MAX_HISTORY:
                    _history.pop(0)

        # Push via Socket.IO if available
        if SOCKETIO_AVAILABLE and socketio:
            summary = _manager.get_summary()
            socketio.emit("fleet_update", {
                "bins":    list(_latest.values()),
                "summary": summary,
            })

        time.sleep(3)   # New reading every 3 seconds

# ─── REST Endpoints ───────────────────────────────────────────────────────────
@app.route("/api/status")
def api_status():
    """Health-check endpoint."""
    return jsonify({
        "status":  "running",
        "time":    datetime.now().isoformat(),
        "version": "1.0.0",
    })

@app.route("/api/bins/latest")
def api_bins_latest():
    """Return the most recent reading for every bin."""
    with _lock:
        data = list(_latest.values())
    return jsonify({"bins": data, "count": len(data)})

@app.route("/api/bins/history")
def api_bins_history():
    """Return recent readings, optionally filtered by bin_id."""
    bin_id = request.args.get("bin_id")
    limit  = int(request.args.get("limit", 100))
    with _lock:
        data = list(_history)
    if bin_id:
        data = [r for r in data if r["bin_id"] == bin_id]
    return jsonify({"history": data[-limit:], "count": len(data[-limit:])})

@app.route("/api/fleet/summary")
def api_fleet_summary():
    """Fleet-wide statistics."""
    if _manager is None:
        return jsonify({"error": "Simulation not started yet"}), 503
    return jsonify(_manager.get_summary())

@app.route("/api/bins/config")
def api_bins_config():
    """Static bin configuration (location, zone, capacity)."""
    configs = [
        {
            "bin_id":          c.bin_id,
            "location":        c.location,
            "zone":            c.zone,
            "lat":             c.lat,
            "lon":             c.lon,
            "capacity_litres": c.capacity_litres,
        }
        for c in BIN_CONFIGS
    ]
    return jsonify({"bins": configs})

@app.route("/api/bins/alerts")
def api_bins_alerts():
    """Return only readings where alert=True (last 50)."""
    with _lock:
        alerts = [r for r in _history if r.get("alert") is True][-50:]
    return jsonify({"alerts": alerts, "count": len(alerts)})

@app.route("/api/logs/csv")
def api_logs_csv():
    """Serve the raw CSV log for download."""
    if os.path.exists(CSV_LOG_PATH):
        return send_from_directory(
            os.path.dirname(CSV_LOG_PATH),
            os.path.basename(CSV_LOG_PATH),
            as_attachment=True,
        )
    return jsonify({"error": "Log file not found"}), 404

# ─── Dashboard Serve ──────────────────────────────────────────────────────────
@app.route("/")
def serve_dashboard():
    dashboard_dir = os.path.join(os.path.dirname(__file__), "..", "dashboard")
    return send_from_directory(dashboard_dir, "index.html")

@app.route("/<path:filename>")
def serve_static(filename):
    dashboard_dir = os.path.join(os.path.dirname(__file__), "..", "dashboard")
    return send_from_directory(dashboard_dir, filename)

# ─── Entry Point ──────────────────────────────────────────────────────────────
def start_server(host="0.0.0.0", port=5000, debug=False):
    # Start simulation in background
    sim_thread        = threading.Thread(target=simulation_worker, daemon=True)
    sim_thread.start()
    print(f"\n  🌐  Smart Waste API running at http://{host}:{port}")
    print(f"  📊  Dashboard → http://localhost:{port}")
    print(f"  📡  REST API  → http://localhost:{port}/api/bins/latest")
    print(f"  Press Ctrl+C to stop.\n")

    if SOCKETIO_AVAILABLE and socketio:
        socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)
    else:
        app.run(host=host, port=port, debug=debug)

if __name__ == "__main__":
    start_server()