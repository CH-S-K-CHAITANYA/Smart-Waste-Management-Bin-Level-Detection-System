"""
=============================================================================
Smart Waste Management & Bin Level Detection System
File: python_simulation/report_generator.py
Description:
    Reads collected CSV log data and generates:
    1. A formatted CSV summary report
    2. A professional PDF waste monitoring report using fpdf2
=============================================================================
"""

import os
import csv
import json
import math
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Any

# ─── Path Configuration ───────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR    = os.path.join(BASE_DIR, "data")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
LOG_PATH    = os.path.join(DATA_DIR, "bin_logs.csv")
REPORT_CSV  = os.path.join(REPORTS_DIR, "waste_monitoring_report.csv")
REPORT_PDF  = os.path.join(REPORTS_DIR, "waste_monitoring_report.pdf")
REPORT_JSON = os.path.join(REPORTS_DIR, "summary_stats.json")

os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(DATA_DIR,    exist_ok=True)

# ─── Data Loading ─────────────────────────────────────────────────────────────
def load_logs(filepath: str = LOG_PATH) -> List[Dict]:
    """Load all readings from the CSV log file."""
    if not os.path.exists(filepath):
        print(f"⚠  Log file not found: {filepath}")
        print("   Run python_simulation/smart_waste_simulator.py first.")
        return []

    with open(filepath, "r", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)

# ─── Statistical Analysis ─────────────────────────────────────────────────────
def compute_bin_stats(records: List[Dict]) -> Dict[str, Dict]:
    """
    Per-bin statistics: average fill, max fill, alert count, collection events.
    """
    grouped: Dict[str, List[float]] = defaultdict(list)
    alerts:  Dict[str, int]         = defaultdict(int)
    locs:    Dict[str, str]         = {}

    for r in records:
        bid = r["bin_id"]
        try:
            fill = float(r["fill_percentage"])
        except ValueError:
            continue
        grouped[bid].append(fill)
        if r["alert"].lower() in ("true", "1", "yes"):
            alerts[bid] += 1
        locs[bid] = r["location"]

    stats = {}
    for bid, fills in grouped.items():
        stats[bid] = {
            "location":          locs[bid],
            "readings":          len(fills),
            "avg_fill":          round(sum(fills) / len(fills), 1),
            "max_fill":          round(max(fills), 1),
            "min_fill":          round(min(fills), 1),
            "alert_count":       alerts[bid],
            "fill_distribution": _fill_distribution(fills),
        }
    return stats

def _fill_distribution(fills: List[float]) -> Dict[str, int]:
    """Bucket fill values into status categories."""
    dist = {"EMPTY": 0, "QUARTER": 0, "HALF": 0, "THREE_Q": 0, "FULL": 0}
    for f in fills:
        if f <= 20:    dist["EMPTY"]   += 1
        elif f <= 40:  dist["QUARTER"] += 1
        elif f <= 60:  dist["HALF"]    += 1
        elif f <= 80:  dist["THREE_Q"] += 1
        else:          dist["FULL"]    += 1
    return dist

def fleet_summary(records: List[Dict], bin_stats: Dict) -> Dict:
    """Overall fleet-level summary."""
    total_readings = len(records)
    total_alerts   = sum(
        1 for r in records if r["alert"].lower() in ("true", "1", "yes")
    )
    all_fills = []
    for r in records:
        try:
            all_fills.append(float(r["fill_percentage"]))
        except ValueError:
            pass

    return {
        "generated_at":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_bins":     len(bin_stats),
        "total_readings": total_readings,
        "total_alerts":   total_alerts,
        "avg_fill_fleet": round(sum(all_fills) / len(all_fills), 1) if all_fills else 0,
        "max_fill_ever":  round(max(all_fills), 1) if all_fills else 0,
        "alert_rate_pct": round(total_alerts / total_readings * 100, 1) if total_readings else 0,
    }

# ─── CSV Summary Report ───────────────────────────────────────────────────────
def generate_csv_report(records: List[Dict], filepath: str = REPORT_CSV):
    """Write per-reading summary CSV with extra computed columns."""
    with open(filepath, "w", newline="") as f:
        fieldnames = [
            "timestamp", "bin_id", "location",
            "distance_cm", "fill_percentage", "bin_status",
            "alert", "temperature_c", "humidity_pct",
            "fill_bar",           # ASCII bar for visual
            "priority_score",     # Simple urgency score
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for r in records:
            try:
                fill = float(r["fill_percentage"])
            except ValueError:
                fill = 0.0

            bar_len  = int(fill / 10)
            fill_bar = "#" * bar_len + "-" * (10 - bar_len) + f" {fill:.0f}%"
            priority = round(fill / 20, 1)   # 0–5 scale

            writer.writerow({
                **{k: r[k] for k in [
                    "timestamp", "bin_id", "location",
                    "distance_cm", "fill_percentage", "bin_status",
                    "alert", "temperature_c", "humidity_pct"
                ]},
                "fill_bar":      fill_bar,
                "priority_score":priority,
            })

    print(f"  ✅  CSV report saved → {filepath}")

# ─── PDF Report ───────────────────────────────────────────────────────────────
def generate_pdf_report(
    records:   List[Dict],
    bin_stats: Dict,
    summary:   Dict,
    filepath:  str = REPORT_PDF,
):
    """Generate a professional waste-monitoring PDF using fpdf2."""
    try:
        from fpdf import FPDF, XPos, YPos
    except ImportError:
        print("  ⚠  fpdf2 not installed.  Run:  pip install fpdf2")
        return

    class WasteReport(FPDF):
        def header(self):
            self.set_fill_color(10, 25, 60)
            self.rect(0, 0, 210, 20, "F")
            self.set_font("Helvetica", "B", 13)
            self.set_text_color(255, 255, 255)
            self.cell(0, 10, "  Smart Waste Management - Bin Level Monitoring Report",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
            self.set_text_color(0, 0, 0)
            self.ln(4)

        def footer(self):
            self.set_y(-15)
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(120, 120, 120)
            self.cell(0, 10, f"Page {self.page_no()}  |  Generated {summary['generated_at']}", align="C")

    pdf = WasteReport()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # ── Cover Info ────────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(10, 25, 60)
    pdf.cell(0, 10, "Fleet Monitoring Summary", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 6, f"Report Date : {summary['generated_at']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    # ── KPI Row ───────────────────────────────────────────────────────────────
    kpis = [
        ("Total Bins",     str(summary["total_bins"])),
        ("Total Readings", str(summary["total_readings"])),
        ("Avg Fill",       f"{summary['avg_fill_fleet']}%"),
        ("Total Alerts",   str(summary["total_alerts"])),
        ("Alert Rate",     f"{summary['alert_rate_pct']}%"),
    ]
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(230, 240, 255)
    pdf.set_text_color(10, 25, 60)
    col_w = 37
    for label, value in kpis:
        pdf.set_fill_color(230, 240, 255)
        pdf.cell(col_w, 12, f"{label}\n{value}", border=1, fill=True, align="C")
    pdf.ln(16)

    # ── Per-Bin Statistics Table ───────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(10, 25, 60)
    pdf.cell(0, 8, "Per-Bin Statistics", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(10, 25, 60)
    pdf.set_text_color(255, 255, 255)
    headers = ["Bin ID", "Location", "Readings", "Avg Fill%", "Max Fill%", "Alerts"]
    widths  = [20, 60, 20, 25, 25, 20]
    for h, w in zip(headers, widths):
        pdf.cell(w, 8, h, border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(0, 0, 0)
    for bid, s in bin_stats.items():
        pdf.set_fill_color(245, 248, 255)
        row = [bid, s["location"], str(s["readings"]),
               f"{s['avg_fill']}%", f"{s['max_fill']}%", str(s["alert_count"])]
        for val, w in zip(row, widths):
            pdf.cell(w, 7, val, border=1, fill=True, align="C")
        pdf.ln()

    pdf.ln(6)

    # ── Last 20 Readings Table ─────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(10, 25, 60)
    pdf.cell(0, 8, "Recent Readings (last 20)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(10, 25, 60)
    pdf.set_text_color(255, 255, 255)
    cols  = ["Timestamp", "Bin ID", "Location", "Dist(cm)", "Fill%", "Status", "Alert"]
    cwidths = [38, 15, 48, 18, 14, 30, 12]
    for h, w in zip(cols, cwidths):
        pdf.cell(w, 7, h, border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(0, 0, 0)
    for r in records[-20:]:
        pdf.set_fill_color(250, 252, 255)
        alert_lbl = "! YES" if r["alert"].lower() in ("true", "1", "yes") else "No"
        row_data  = [
            r["timestamp"], r["bin_id"], r["location"],
            r["distance_cm"], r["fill_percentage"], r["bin_status"], alert_lbl
        ]
        for val, w in zip(row_data, cwidths):
            pdf.cell(w, 6, str(val), border=1, fill=True, align="C")
        pdf.ln()

    pdf.output(filepath)
    print(f"  ✅  PDF report saved → {filepath}")

# ─── JSON Summary ─────────────────────────────────────────────────────────────
def generate_json_summary(summary: Dict, bin_stats: Dict, filepath: str = REPORT_JSON):
    """Export JSON summary for dashboard API consumption."""
    payload = {"fleet_summary": summary, "bin_stats": bin_stats}
    with open(filepath, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"  ✅  JSON summary saved → {filepath}")

# ─── Entry Point ──────────────────────────────────────────────────────────────
def generate_all_reports():
    print("\n  📊  Smart Waste Management — Report Generator")
    print("  " + "─" * 52)

    records = load_logs()
    if not records:
        print("  No data to report. Run the simulator first.\n")
        return

    bin_stats = compute_bin_stats(records)
    summary   = fleet_summary(records, bin_stats)

    print(f"  Loaded {len(records)} readings from {len(bin_stats)} bins.\n")

    generate_csv_report(records)
    generate_pdf_report(records, bin_stats, summary)
    generate_json_summary(summary, bin_stats)

    print("\n  Fleet Summary:")
    print(f"    Total Bins     : {summary['total_bins']}")
    print(f"    Total Readings : {summary['total_readings']}")
    print(f"    Fleet Avg Fill : {summary['avg_fill_fleet']}%")
    print(f"    Total Alerts   : {summary['total_alerts']}")
    print(f"    Alert Rate     : {summary['alert_rate_pct']}%")
    print()

if __name__ == "__main__":
    generate_all_reports()