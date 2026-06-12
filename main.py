"""
=============================================================================
Smart Waste Management & Bin Level Detection System
File: main.py
Description:
    Main entry point for the Smart Waste Management project.

    Usage:
        python main.py                    # Full simulation + report
        python main.py --mode simulate    # Simulation only
        python main.py --mode report      # Generate reports from existing data
        python main.py --mode api         # Start Flask REST API + dashboard
        python main.py --mode mqtt        # Simulate + publish via MQTT
        python main.py --cycles 50        # Custom cycle count

    Make sure you have installed requirements:
        pip install -r requirements.txt
=============================================================================
"""

import os
import sys
import argparse
from colorama import Fore, Style, init

init(autoreset=True)

BANNER = f"""
{Fore.GREEN}
╔══════════════════════════════════════════════════════════════════╗
║     🚮  Smart Waste Management & Bin Level Detection System      ║
║                                                                  ║
║     IoT Simulation  |  Python + ESP32  |  MQTT + Dashboard       ║
╚══════════════════════════════════════════════════════════════════╝
{Style.RESET_ALL}"""

def parse_args():
    parser = argparse.ArgumentParser(
        description="Smart Waste Management System — Main Runner",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=["simulate", "report", "api", "mqtt", "full"],
        default="full",
        help=(
            "simulate  — run bin level simulation only\n"
            "report    — generate CSV + PDF reports from existing data\n"
            "api       — start Flask REST API (live dashboard backend)\n"
            "mqtt      — simulate and publish via MQTT broker\n"
            "full      — simulate + report (default)"
        ),
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=25,
        help="Number of simulation cycles (default: 25)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Seconds between simulation cycles (default: 1.0)",
    )
    parser.add_argument(
        "--no-mqtt",
        action="store_true",
        default=True,
        help="Disable MQTT publishing (default: disabled for offline use)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Flask API port (default: 5000)",
    )
    return parser.parse_args()


def mode_simulate(cycles: int, interval: float):
    """Run the Python simulation with console output."""
    from python_simulation.smart_waste_simulator import run_simulation
    run_simulation(cycles=cycles, interval_seconds=interval)


def mode_report():
    """Generate all reports from existing CSV log."""
    from python_simulation.report_generator import generate_all_reports
    generate_all_reports()


def mode_api(port: int):
    """Start the Flask REST API + live dashboard."""
    from python_simulation.flask_api import start_server
    start_server(port=port)


def mode_mqtt(cycles: int, interval: float):
    """Run simulation and publish each reading over MQTT."""
    import time
    from python_simulation.smart_waste_simulator import (
        WasteFleetManager, CSVLogger, CSV_LOG_PATH
    )
    from python_simulation.mqtt_publisher import MQTTPublisher

    print(f"\n{Fore.CYAN}  📡  Starting MQTT simulation mode...{Style.RESET_ALL}")
    logger    = CSVLogger(CSV_LOG_PATH)
    manager   = WasteFleetManager(logger)
    publisher = MQTTPublisher()

    for _ in range(cycles):
        readings = manager.run_cycle()
        for r in readings:
            publisher.publish_reading(r.as_dict())
        publisher.publish_fleet_summary(manager.get_summary())
        time.sleep(interval)

    publisher.disconnect()
    print(f"\n{Fore.GREEN}  ✅  MQTT simulation complete.{Style.RESET_ALL}")


def mode_full(cycles: int, interval: float):
    """Default: run simulation then generate reports."""
    mode_simulate(cycles, interval)
    print(f"\n{Fore.YELLOW}  📊  Generating reports...{Style.RESET_ALL}")
    mode_report()


# ─── Entry Point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(BANNER)

    args = parse_args()

    print(f"  Mode     : {Fore.CYAN}{args.mode.upper()}{Style.RESET_ALL}")
    print(f"  Cycles   : {args.cycles}")
    print(f"  Interval : {args.interval}s\n")

    if args.mode == "simulate":
        mode_simulate(args.cycles, args.interval)

    elif args.mode == "report":
        mode_report()

    elif args.mode == "api":
        mode_api(args.port)

    elif args.mode == "mqtt":
        mode_mqtt(args.cycles, args.interval)

    else:   # "full" (default)
        mode_full(args.cycles, args.interval)