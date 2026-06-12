"""
=============================================================================
Smart Waste Management & Bin Level Detection System
File: python_simulation/smart_waste_simulator.py
Author: IoT Smart Waste Project
Description:
    Simulates multiple smart waste bins with ultrasonic sensor readings,
    fill-level calculations, alert generation, and CSV logging.
    Mirrors the exact behaviour of the ESP32 + HC-SR04 hardware setup.
=============================================================================
"""

import os
import csv
import time
import math
import random
import threading
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from colorama import Fore, Style, init

# ─── Initialise colorama for coloured terminal output ────────────────────────
init(autoreset=True)

# ─── Constants ───────────────────────────────────────────────────────────────
BIN_HEIGHT_CM      = 60       # Total bin depth in centimetres
SENSOR_OFFSET_CM   = 2        # HC-SR04 sits 2 cm above the bin rim
USABLE_HEIGHT_CM   = BIN_HEIGHT_CM - SENSOR_OFFSET_CM   # 58 cm usable space
SPEED_OF_SOUND     = 34300    # cm/s at 25 °C

THRESHOLD_EMPTY    = 20       # ≤ 20% → EMPTY
THRESHOLD_QUARTER  = 40       # 21–40% → QUARTER FULL
THRESHOLD_HALF     = 60       # 41–60% → HALF FULL
THRESHOLD_THREE_Q  = 80       # 61–80% → THREE QUARTERS
THRESHOLD_FULL     = 100      # 81–100% → FULL / ALERT

# Simulated waste accumulation speed per bin (% per cycle)
FILL_RATE_MAP = {
    "BIN-A": 3.5,   # High-traffic → fills faster
    "BIN-B": 2.0,
    "BIN-C": 1.5,
    "BIN-D": 4.0,   # Busiest zone
}

CSV_LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "bin_logs.csv")
CSV_HEADER   = [
    "timestamp", "bin_id", "location",
    "distance_cm", "fill_percentage", "bin_status",
    "alert", "temperature_c", "humidity_pct"
]

# ─── Data Classes ─────────────────────────────────────────────────────────────
@dataclass
class BinConfig:
    """Static configuration for each physical bin."""
    bin_id:   str
    location: str
    zone:     str
    lat:      float
    lon:      float
    capacity_litres: int = 120

@dataclass
class BinReading:
    """One telemetry snapshot from a smart bin."""
    timestamp:      str
    bin_id:         str
    location:       str
    distance_cm:    float
    fill_percentage:float
    bin_status:     str
    alert:          bool
    temperature_c:  float
    humidity_pct:   float

    def as_dict(self) -> Dict:
        return {
            "timestamp":       self.timestamp,
            "bin_id":          self.bin_id,
            "location":        self.location,
            "distance_cm":     round(self.distance_cm, 2),
            "fill_percentage": round(self.fill_percentage, 1),
            "bin_status":      self.bin_status,
            "alert":           self.alert,
            "temperature_c":   round(self.temperature_c, 1),
            "humidity_pct":    round(self.humidity_pct, 1),
        }

# ─── Bin Registry ─────────────────────────────────────────────────────────────
BIN_CONFIGS: List[BinConfig] = [
    BinConfig("BIN-A", "Main Entrance Gate",     "Zone-1",  12.9716, 77.5946, 120),
    BinConfig("BIN-B", "Cafeteria Block",        "Zone-2",  12.9718, 77.5950, 80),
    BinConfig("BIN-C", "Library Corridor",       "Zone-3",  12.9720, 77.5955, 100),
    BinConfig("BIN-D", "Sports Ground Corner",   "Zone-4",  12.9714, 77.5940, 120),
]

# ─── Sensor Simulation Utilities ──────────────────────────────────────────────
def simulate_hcsr04_reading(fill_pct: float, noise_sigma: float = 0.4) -> float:
    """
    Converts a fill percentage back into a sensor distance reading (cm),
    adding realistic Gaussian noise to mimic the HC-SR04 sensor jitter.

    Physics:
        distance = sensor_offset + (1 - fill_pct/100) * usable_height
    """
    ideal_distance = SENSOR_OFFSET_CM + (1.0 - fill_pct / 100.0) * USABLE_HEIGHT_CM
    noise          = random.gauss(0, noise_sigma)
    raw_distance   = ideal_distance + noise
    # Clamp to physical limits
    return round(max(SENSOR_OFFSET_CM, min(BIN_HEIGHT_CM, raw_distance)), 2)

def distance_to_fill_pct(distance_cm: float) -> float:
    """
    Calculates fill percentage from the raw sensor distance.
    Fill % = (1 - (distance - offset) / usable_height) × 100
    """
    fill_pct = (1.0 - (distance_cm - SENSOR_OFFSET_CM) / USABLE_HEIGHT_CM) * 100.0
    return round(max(0.0, min(100.0, fill_pct)), 1)

def classify_bin_status(fill_pct: float) -> str:
    """Returns human-readable status from fill percentage."""
    if fill_pct <= THRESHOLD_EMPTY:
        return "EMPTY"
    elif fill_pct <= THRESHOLD_QUARTER:
        return "QUARTER FULL"
    elif fill_pct <= THRESHOLD_HALF:
        return "HALF FULL"
    elif fill_pct <= THRESHOLD_THREE_Q:
        return "THREE QUARTERS"
    else:
        return "FULL"

def should_alert(fill_pct: float) -> bool:
    """Trigger collection alert when bin exceeds 80%."""
    return fill_pct >= THRESHOLD_THREE_Q

def simulate_environment() -> tuple:
    """Simulate ambient temperature and humidity (DHT11-style)."""
    temperature = round(random.uniform(24.0, 38.0), 1)
    humidity    = round(random.uniform(40.0, 85.0), 1)
    return temperature, humidity

# ─── CSV Logger ───────────────────────────────────────────────────────────────
class CSVLogger:
    """Thread-safe CSV logger that appends readings to disk."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self._lock    = threading.Lock()
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        self._init_file()

    def _init_file(self):
        if not os.path.exists(self.filepath):
            with open(self.filepath, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
                writer.writeheader()

    def log(self, reading: BinReading):
        with self._lock:
            with open(self.filepath, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
                writer.writerow(reading.as_dict())

# ─── Smart Bin Simulator ──────────────────────────────────────────────────────
class SmartBin:
    """
    Represents one physical smart bin unit.
    Maintains internal state (fill level) and produces sensor readings.
    """

    def __init__(self, config: BinConfig, initial_fill: float = 0.0):
        self.config      = config
        self.fill_pct    = initial_fill
        self.fill_rate   = FILL_RATE_MAP.get(config.bin_id, 2.0)
        self._collected  = False          # True after a collection event
        self.history: List[BinReading] = []

    @property
    def bin_id(self) -> str:
        return self.config.bin_id

    def update(self) -> BinReading:
        """Advance one simulation cycle: accumulate waste, read sensor, log."""
        # ── Accumulate waste (with small random variation per cycle) ──────────
        increment   = self.fill_rate * random.uniform(0.7, 1.3)
        self.fill_pct = min(100.0, self.fill_pct + increment)

        # ── Simulate sensor ───────────────────────────────────────────────────
        distance_cm  = simulate_hcsr04_reading(self.fill_pct)
        measured_pct = distance_to_fill_pct(distance_cm)
        status       = classify_bin_status(measured_pct)
        alert        = should_alert(measured_pct)
        temp, hum    = simulate_environment()

        reading = BinReading(
            timestamp       = datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            bin_id          = self.config.bin_id,
            location        = self.config.location,
            distance_cm     = distance_cm,
            fill_percentage = measured_pct,
            bin_status      = status,
            alert           = alert,
            temperature_c   = temp,
            humidity_pct    = hum,
        )
        self.history.append(reading)
        return reading

    def collect(self):
        """Simulate a garbage truck emptying this bin."""
        self.fill_pct   = random.uniform(0.0, 5.0)   # Reset to near-empty
        self._collected = True
        print(f"{Fore.CYAN}🚛  {self.bin_id} emptied by collection truck!{Style.RESET_ALL}")

# ─── Fleet Manager ────────────────────────────────────────────────────────────
class WasteFleetManager:
    """
    Manages the entire fleet of smart bins.
    Runs simulation cycles, triggers collection alerts, and persists data.
    """

    def __init__(self, logger: CSVLogger):
        self.logger = logger
        # Start with varying initial fill levels for realism
        initial_fills = [5.0, 30.0, 55.0, 10.0]
        self.bins: List[SmartBin] = [
            SmartBin(cfg, initial_fill=initial_fills[i])
            for i, cfg in enumerate(BIN_CONFIGS)
        ]
        self.cycle_count  = 0
        self.latest_readings: Dict[str, BinReading] = {}

    def run_cycle(self) -> List[BinReading]:
        """Execute one monitoring cycle across all bins."""
        self.cycle_count += 1
        readings: List[BinReading] = []

        for smart_bin in self.bins:
            reading = smart_bin.update()
            readings.append(reading)
            self.logger.log(reading)
            self.latest_readings[reading.bin_id] = reading

            # Auto-collect if bin is completely full
            if reading.fill_percentage >= 100.0:
                smart_bin.collect()

        return readings

    def get_summary(self) -> Dict:
        """Returns a fleet-wide summary dict for dashboard consumption."""
        total = len(self.bins)
        full_bins  = sum(1 for r in self.latest_readings.values() if r.fill_percentage >= 80)
        empty_bins = sum(1 for r in self.latest_readings.values() if r.fill_percentage <= 20)
        avg_fill   = (
            sum(r.fill_percentage for r in self.latest_readings.values()) / total
            if self.latest_readings else 0.0
        )
        return {
            "total_bins":  total,
            "full_bins":   full_bins,
            "empty_bins":  empty_bins,
            "active_bins": total - empty_bins,
            "avg_fill_pct": round(avg_fill, 1),
            "alerts":      full_bins,
            "cycle":       self.cycle_count,
        }

# ─── Console Display ──────────────────────────────────────────────────────────
def display_readings(readings: List[BinReading], cycle: int):
    """Pretty-print a simulation cycle to the terminal."""
    print(f"\n{Fore.WHITE}{'═' * 72}")
    print(f"  📡  SMART WASTE MONITORING  │  Cycle #{cycle}  │  "
          f"{datetime.now().strftime('%H:%M:%S')}")
    print(f"{'═' * 72}{Style.RESET_ALL}")

    for r in readings:
        # Colour code by fill level
        if r.fill_percentage >= 80:
            colour = Fore.RED
            icon   = "🔴"
        elif r.fill_percentage >= 60:
            colour = Fore.YELLOW
            icon   = "🟡"
        elif r.fill_percentage >= 40:
            colour = Fore.GREEN
            icon   = "🟢"
        else:
            colour = Fore.CYAN
            icon   = "🔵"

        alert_str = f"{Fore.RED} ⚠  ALERT — COLLECT NOW!{Style.RESET_ALL}" if r.alert else ""
        print(
            f"  {icon}  {colour}{r.bin_id:<8}{Style.RESET_ALL}"
            f"  {r.location:<28}"
            f"  Dist: {r.distance_cm:>5.1f} cm"
            f"  Fill: {colour}{r.fill_percentage:>5.1f}%{Style.RESET_ALL}"
            f"  [{r.bin_status:<14}]"
            f"  {r.temperature_c}°C"
            f"{alert_str}"
        )
    print(f"{Fore.WHITE}{'─' * 72}{Style.RESET_ALL}")

# ─── Main Simulation Entry Point ──────────────────────────────────────────────
def run_simulation(
    cycles:           int   = 30,
    interval_seconds: float = 2.0,
    verbose:          bool  = True
) -> List[BinReading]:
    """
    Run the full fleet simulation for `cycles` cycles.

    Args:
        cycles:           Number of monitoring cycles to run.
        interval_seconds: Delay between cycles (seconds).
        verbose:          Print readings to console if True.

    Returns:
        Flat list of all BinReading objects generated.
    """
    print(f"\n{Fore.GREEN}{'█' * 72}")
    print("  🚮  Smart Waste Management & Bin Level Detection System  ")
    print("  Virtual Simulation — Python Edition                     ")
    print(f"{'█' * 72}{Style.RESET_ALL}\n")

    logger  = CSVLogger(CSV_LOG_PATH)
    manager = WasteFleetManager(logger)
    all_readings: List[BinReading] = []

    print(f"  Monitoring {len(manager.bins)} bins over {cycles} cycles "
          f"({interval_seconds}s interval)")
    print(f"  CSV log → {os.path.abspath(CSV_LOG_PATH)}\n")

    for _ in range(cycles):
        readings = manager.run_cycle()
        all_readings.extend(readings)

        if verbose:
            display_readings(readings, manager.cycle_count)

        time.sleep(interval_seconds)

    # ── Final summary ─────────────────────────────────────────────────────────
    summary = manager.get_summary()
    print(f"\n{Fore.GREEN}{'═' * 72}")
    print(f"  ✅  SIMULATION COMPLETE  │  {summary['cycle']} cycles")
    print(f"  Total Bins : {summary['total_bins']}")
    print(f"  Full Bins  : {summary['full_bins']}  (≥ 80%)")
    print(f"  Avg Fill   : {summary['avg_fill_pct']}%")
    print(f"  Alerts     : {summary['alerts']}")
    print(f"  Log saved  : {os.path.abspath(CSV_LOG_PATH)}")
    print(f"{'═' * 72}{Style.RESET_ALL}\n")

    return all_readings


if __name__ == "__main__":
    run_simulation(cycles=20, interval_seconds=1.5)