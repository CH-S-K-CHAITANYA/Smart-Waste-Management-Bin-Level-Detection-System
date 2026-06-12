"""
=============================================================================
Smart Waste Management & Bin Level Detection System
File: python_simulation/mqtt_publisher.py
Description:
    Simulates the ESP32 publishing bin telemetry over MQTT.
    Compatible with:
      - Mosquitto (local broker)
      - HiveMQ (cloud free tier)  broker.hivemq.com : 1883
      - Eclipse (cloud)           mqtt.eclipseprojects.io : 1883

    Topic structure:
        smartwaste/{bin_id}/telemetry   → JSON payload
        smartwaste/{bin_id}/alert       → "COLLECT NOW" or "OK"
        smartwaste/fleet/summary        → Fleet-wide summary JSON

    To test without a broker, set SIMULATE_ONLY = True.
=============================================================================
"""

import os
import json
import time
import threading
from datetime import datetime

# ─── Config ───────────────────────────────────────────────────────────────────
BROKER_HOST   = "broker.hivemq.com"    # Free public broker — no auth required
BROKER_PORT   = 1883
KEEPALIVE     = 60
CLIENT_ID     = "SmartWaste-Simulator-001"
QOS           = 1
TOPIC_ROOT    = "smartwaste"

SIMULATE_ONLY = False   # Set True to print MQTT messages without connecting

# ─── Payload Builder ──────────────────────────────────────────────────────────
def build_telemetry_payload(reading: dict) -> str:
    """Serialize a BinReading dict to JSON string for MQTT publish."""
    payload = {
        "timestamp":       reading.get("timestamp", datetime.now().isoformat()),
        "bin_id":          reading["bin_id"],
        "location":        reading["location"],
        "distance_cm":     reading["distance_cm"],
        "fill_percentage": reading["fill_percentage"],
        "bin_status":      reading["bin_status"],
        "alert":           reading["alert"],
        "temperature_c":   reading["temperature_c"],
        "humidity_pct":    reading["humidity_pct"],
    }
    return json.dumps(payload)

def build_fleet_payload(summary: dict) -> str:
    summary["published_at"] = datetime.now().isoformat()
    return json.dumps(summary)

# ─── MQTT Client Wrapper ──────────────────────────────────────────────────────
class MQTTPublisher:
    """
    Wraps paho-mqtt for easy bin telemetry publishing.
    Falls back to console-only mode if paho not installed.
    """

    def __init__(self):
        self._client   = None
        self._connected = False
        self._lock     = threading.Lock()

        if SIMULATE_ONLY:
            print("  [MQTT] Simulation-only mode — messages printed, not sent.")
            return

        try:
            import paho.mqtt.client as mqtt

            def on_connect(client, userdata, flags, rc, properties=None):
                if rc == 0:
                    self._connected = True
                    print(f"  [MQTT] ✅ Connected to {BROKER_HOST}:{BROKER_PORT}")
                else:
                    print(f"  [MQTT] ❌ Connection failed — rc={rc}")

            def on_publish(client, userdata, mid, reason_code=None, properties=None):
                pass   # Silence successful publish confirmations

            def on_disconnect(client, userdata, disconnect_flags, rc, properties=None):
                self._connected = False
                print(f"  [MQTT] Disconnected (rc={rc}). Reconnecting...")
                try:
                    client.reconnect()
                except Exception as e:
                    print(f"  [MQTT] Reconnect failed: {e}")

            self._client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=CLIENT_ID,
                protocol=mqtt.MQTTv5
            )
            self._client.on_connect    = on_connect
            self._client.on_publish    = on_publish
            self._client.on_disconnect = on_disconnect

            self._client.connect_async(BROKER_HOST, BROKER_PORT, KEEPALIVE)
            self._client.loop_start()
            time.sleep(1.5)   # Allow handshake

        except ImportError:
            print("  [MQTT] paho-mqtt not installed → console-only mode.")
            print("         pip install paho-mqtt")

    # ── Public Methods ────────────────────────────────────────────────────────
    def publish_reading(self, reading: dict):
        """Publish bin telemetry + optional alert message."""
        bid     = reading["bin_id"]
        payload = build_telemetry_payload(reading)
        topic   = f"{TOPIC_ROOT}/{bid}/telemetry"
        self._publish(topic, payload)

        # Alert topic
        alert_msg   = "COLLECT NOW" if reading.get("alert") else "OK"
        alert_topic = f"{TOPIC_ROOT}/{bid}/alert"
        self._publish(alert_topic, alert_msg)

        if reading.get("alert"):
            print(f"  [MQTT] 🚨  Alert published → {alert_topic} : {alert_msg}")

    def publish_fleet_summary(self, summary: dict):
        topic   = f"{TOPIC_ROOT}/fleet/summary"
        payload = build_fleet_payload(summary)
        self._publish(topic, payload)

    def disconnect(self):
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()

    # ── Internal ──────────────────────────────────────────────────────────────
    def _publish(self, topic: str, payload: str):
        if SIMULATE_ONLY or not self._client:
            print(f"  [MQTT-SIM] {topic} → {payload[:80]}{'...' if len(payload)>80 else ''}")
            return

        if self._connected:
            with self._lock:
                self._client.publish(topic, payload, qos=QOS)
        else:
            print(f"  [MQTT] Not connected — dropped: {topic}")


# ─── Node-RED Integration Notes ───────────────────────────────────────────────
NODE_RED_FLOW_HINT = """
Node-RED Integration
====================
1. Install Node-RED:  npm install -g --unsafe-perm node-red
2. Install dashboard: npm install node-red-dashboard  (in ~/.node-red)
3. Open browser:      http://localhost:1880

Suggested flow:
  [MQTT In]  topic: smartwaste/#
      ↓
  [JSON]     parse payload
      ↓
  [Function] extract fill_percentage, bin_id
      ↓
  [Gauge]    ui_gauge — Fill Level
  [Chart]    ui_chart — History
  [Switch]   alert → [Notification] Node-RED alert popup

Import the flow from: docs/node_red_flow.json
"""

if __name__ == "__main__":
    print(NODE_RED_FLOW_HINT)
    print("\nTo publish simulated data via MQTT, import this module:")
    print("  from python_simulation.mqtt_publisher import MQTTPublisher")
    print("  from python_simulation.smart_waste_simulator import run_simulation")
    print("  OR run main.py which does both automatically.\n")