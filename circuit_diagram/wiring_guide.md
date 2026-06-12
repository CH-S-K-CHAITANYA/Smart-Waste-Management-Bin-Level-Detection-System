# Smart Waste Bin — Circuit Diagram & Wiring Guide

```
                    ┌─────────────────────────────────────────────┐
                    │                                             │
                    │   HC-SR04 Ultrasonic Sensor                 │
                    │   ┌─────────────────────┐                  │
                    │   │  VCC  TRIG ECHO GND  │                  │
                    └───│   │    │    │   │    │                  │
                        └─┬─┘  ─┘  ──┘ ──┘    │                  │
                          │    │    │    │                        │
                    3.3V──┘    │    │   GND                       │
                               │    │                             │
                          GPIO5┘    └GPIO18                       │
                                                                  │
             ┌────────────────────────────────────────────────┐   │
             │                   ESP32                        │   │
             │  ┌──────────────────────────────────────────┐  │   │
             │  │  GPIO5  ── TRIG (HC-SR04)                │  │   │
             │  │  GPIO18 ── ECHO (HC-SR04) via 1kΩ divider│  │   │
             │  │  GPIO21 ── SDA  (OLED I²C)               │  │   │
             │  │  GPIO22 ── SCL  (OLED I²C)               │  │   │
             │  │  GPIO14 ── LED GREEN (+ 220Ω resistor)   │  │   │
             │  │  GPIO27 ── LED YELLOW (+ 220Ω resistor)  │  │   │
             │  │  GPIO26 ── LED RED   (+ 220Ω resistor)   │  │   │
             │  │  GPIO25 ── BUZZER (+)                    │  │   │
             │  │  3.3V   ── VCC  (HC-SR04, OLED)          │  │   │
             │  │  GND    ── GND  (All components)         │  │   │
             │  └──────────────────────────────────────────┘  │   │
             └────────────────────────────────────────────────┘   │
```

## Voltage Divider for ECHO pin (IMPORTANT!)
```
HC-SR04 ECHO (5V) ──── 1kΩ ──┬──── ESP32 GPIO18 (3.3V max)
                              │
                             2kΩ
                              │
                            GND
```
> ⚠️  HC-SR04 operates at 5V but ESP32 GPIO is 3.3V tolerant.
> Always use a voltage divider on the ECHO pin!
> VCC of HC-SR04 connects to 5V (VIN pin on ESP32).

---

## Component Wiring Table

| Component       | Pin/Lead         | ESP32 Pin   | Notes                        |
|-----------------|------------------|-------------|------------------------------|
| HC-SR04         | VCC              | VIN (5V)    | Must be 5V for max range     |
| HC-SR04         | GND              | GND         |                              |
| HC-SR04         | TRIG             | GPIO 5      | Output — send pulse          |
| HC-SR04         | ECHO             | GPIO 18     | Input — via voltage divider  |
| OLED SSD1306    | VCC              | 3.3V        |                              |
| OLED SSD1306    | GND              | GND         |                              |
| OLED SSD1306    | SDA              | GPIO 21     | I²C Data                     |
| OLED SSD1306    | SCL              | GPIO 22     | I²C Clock                    |
| LED Green       | Anode (+)        | GPIO 14     | Series 220Ω resistor         |
| LED Green       | Cathode (–)      | GND         |                              |
| LED Yellow      | Anode (+)        | GPIO 27     | Series 220Ω resistor         |
| LED Yellow      | Cathode (–)      | GND         |                              |
| LED Red         | Anode (+)        | GPIO 26     | Series 220Ω resistor         |
| LED Red         | Cathode (–)      | GND         |                              |
| Buzzer (active) | + (long lead)    | GPIO 25     | Active buzzer (not passive)  |
| Buzzer          | – (short lead)   | GND         |                              |

---

## LED Resistor Calculation
```
V_supply = 3.3V
V_LED    = 2.0V (typical red/yellow), 2.2V (green)
I_LED    = 10mA (safe for GPIO)

R = (V_supply - V_LED) / I_LED
  = (3.3 - 2.0) / 0.01
  = 130Ω  → Use 220Ω (next standard value, safer)
```

---

## HC-SR04 Working Principle
```
ESP32 GPIO5 ──[TRIG]──► 10µs HIGH pulse
                         │
                    Sensor emits 8× 40kHz ultrasonic bursts
                         │
                    Sound travels to waste surface and reflects back
                         │
HC-SR04 [ECHO] ──────────► HIGH pulse duration = round-trip time

Distance = (pulse_width_µs / 58.0) cm
         = (pulse_width_µs × 0.0343 / 2) cm

Fill % = (1 - (distance - offset) / usable_height) × 100
```

---

## Power Supply Options
| Source         | Voltage | Notes                              |
|----------------|---------|-------------------------------------|
| USB (laptop)   | 5V      | Best for development/demo           |
| USB power bank | 5V      | Good for portable demo              |
| 18650 Li-Ion   | 3.7V    | Use TP4056 module + boost to 5V     |
| DC adapter     | 5V 2A   | Recommended for permanent install   |

---

## Tinkercad Simulation Setup
1. Go to https://www.tinkercad.com
2. New Circuit → Add Arduino Uno (acts like ESP32 for sim)
3. Add HC-SR04 → connect TRIG to pin 5, ECHO to pin 18
4. Add LEDs with 220Ω resistors to pins 8, 9, 10
5. Add Piezo buzzer to pin 11
6. Use the simulation code from: `arduino_code/tinkercad_simulation.ino`
