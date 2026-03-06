"""
EET321 Lab 3 - SCR On-Time Characterization (Automated)
========================================================
Steps a DS1804-010 digital potentiometer from 10 kΩ (position 99) down to
minimum (position 0) in 1-second intervals via an Arduino, and at each step
queries a SIGLENT SDS1000X-E oscilloscope over VISA to measure the SCR on-time.

Hardware connections
--------------------
  Arduino pin 2  →  DS1804 CS
  Arduino pin 3  →  DS1804 U/D
  Arduino pin 4  →  DS1804 INC
  Oscilloscope CH1 probe  →  SCR anode (or across load, per your circuit)
  Arduino USB  →  PC USB
  Oscilloscope USB-B (rear) → PC USB   (or use LAN — see SCOPE_RESOURCE below)

SIGLENT SDS1000X-E SCPI notes
------------------------------
  The SDS1000X-E does NOT use standard IEEE SCPI hierarchy (no :MEASure:NWIDth).
  It uses Siglent's legacy command set:
    CHDR OFF           — suppress response headers for clean numeric reads
    PACU NWID,C1       — activate Negative Width measurement on CH1
    C1:PAVA? NWID      — query the current NWID value on CH1
  Response format (CHDR OFF):  <value><unit>  e.g.  8.320000E-03s
  Invalid/no-signal returns:   9.9E+37 (scope's sentinel for "no measurement")

Dependencies (install once)
---------------------------
  pip install pyserial pyvisa pyvisa-py pandas matplotlib
  # NI-VISA or pyvisa-py backend required.  For USB-TMC on Windows install
  # the Siglent USB driver (or use Zadig to bind WinUSB/libusb-win32).

Configuration
-------------
  Edit the constants in the CONFIG block below before running.
  Run:  python scr_characterization.py
"""

import time
import re
import sys
import csv
import datetime
import serial
import serial.tools.list_ports
import pyvisa
import pandas as pd
import matplotlib.pyplot as plt

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG — Edit these values to match your setup
# ═══════════════════════════════════════════════════════════════════════════════

# ── Arduino serial port ───────────────────────────────────────────────────────
# Leave as None to auto-detect, or set explicitly e.g. "COM3" or "/dev/ttyUSB0"
ARDUINO_PORT = None
ARDUINO_BAUD = 9600

# ── Oscilloscope VISA resource string ────────────────────────────────────────
# SIGLENT SDS1000X-E USB VID:PID = 0xF4ED:0xEE3A
# Run with SCOPE_RESOURCE = None first to print all available resources,
# then paste the correct string here.
#
# USB example:  "USB0::0xF4ED::0xEE3A::SDS1XXXX000000::INSTR"
#               (replace SDS1XXXX000000 with your scope's serial number)
# LAN example:  "TCPIP0::192.168.1.50::INSTR"
#               (VXI-11; set IP on scope under Utility → I/O → LAN)
# Leave as None to list available resources and exit.
SCOPE_RESOURCE = None

# ── Oscilloscope channel where SCR output is probed ──────────────────────────
# SIGLENT SDS1000X-E channel names: "C1", "C2", "C3", "C4"
SCOPE_CHANNEL = "C1"

# ── DS1804 parameters ────────────────────────────────────────────────────────
POT_MAX_POS    = 99          # wiper position for full 10 kΩ
POT_MIN_POS    = 0
POT_TOTAL_OHMS = 10_000      # Ω end-to-end (DS1804-010)
POT_POSITIONS  = 100         # positions 0-99

# ── Measurement timing ───────────────────────────────────────────────────────
STEP_INTERVAL_S  = 1.0       # seconds between steps
SETTLE_TIME_S    = 0.2       # seconds after pot moves before triggering scope

# ── On-time measurement ───────────────────────────────────────────────────────
# SIGLENT SDS1000X-E uses its own command set (not standard SCPI hierarchy).
#
# Measurement parameter keyword for Negative Width: NWID
# Full list of time-parameter keywords (from Siglent programming guide):
#   PERI  Period        FREQ  Frequency      PWID  Positive width
#   NWID  Negative width (← SCR on-time)    DUTY  Duty cycle
#   RISE  Rise time     FALL  Fall time      DELA  Delay
#
# Command flow:
#   CHDR OFF           → strip headers from all responses (cleaner parsing)
#   PACU NWID,C1       → enable NWID measurement display on CH1
#   C1:PAVA? NWID      → read the current NWID value
#
# Response (CHDR OFF): numeric string with SI unit suffix, e.g. "8.320000E-03s"
# No-signal / invalid sentinel value: 9.9E+37 (Siglent standard)

# ── Output files ──────────────────────────────────────────────────────────────
TIMESTAMP   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
CSV_OUTPUT  = f"scr_ontime_{TIMESTAMP}.csv"
PLOT_OUTPUT = f"scr_ontime_{TIMESTAMP}.png"

# ═══════════════════════════════════════════════════════════════════════════════
# END CONFIG
# ═══════════════════════════════════════════════════════════════════════════════


def ideal_resistance(pos: int) -> float:
    """
    DS1804 ideal wiper resistance at position n (0-99).
    R(n) = (n / 99) * R_total   (position 0 = ~0 Ω wiper resistance)
    """
    return (pos / (POT_POSITIONS - 1)) * POT_TOTAL_OHMS


def find_arduino_port() -> str:
    """Auto-detect the first Arduino-like serial port."""
    ports = serial.tools.list_ports.comports()
    for p in ports:
        desc = (p.description or "").lower()
        mfr  = (p.manufacturer or "").lower()
        if "arduino" in desc or "arduino" in mfr or "ch340" in mfr or "ftdi" in mfr:
            print(f"  Auto-detected Arduino on {p.device}")
            return p.device
    if ports:
        print(f"  No Arduino found by name; using first port: {ports[0].device}")
        return ports[0].device
    raise RuntimeError("No serial ports found. Connect the Arduino and try again.")


class Arduino:
    """Thin wrapper around pyserial for Arduino communication."""

    def __init__(self, port: str, baud: int = 9600):
        self.ser = serial.Serial(port, baud, timeout=3)
        time.sleep(2)          # Wait for Arduino reset on connect
        self._flush()

    def _flush(self):
        self.ser.reset_input_buffer()

    def send(self, cmd: str) -> str:
        self._flush()
        self.ser.write((cmd + "\n").encode())
        response = self.ser.readline().decode(errors="replace").strip()
        return response

    def handshake(self):
        resp = self.send("READY?")
        if resp != "READY":
            raise RuntimeError(f"Arduino handshake failed. Got: '{resp}'")
        print("  Arduino handshake OK")

    def goto(self, pos: int) -> int:
        """Move to absolute position. Returns confirmed position."""
        resp = self.send(f"SET:{pos}")
        m = re.match(r"OK:(\d+)", resp)
        if not m:
            raise RuntimeError(f"Unexpected Arduino response to SET:{pos} → '{resp}'")
        return int(m.group(1))

    def get_pos(self) -> int:
        return int(self.send("POS?"))

    def close(self):
        self.ser.close()


class Oscilloscope:
    """
    SIGLENT SDS1000X-E oscilloscope driver via pyvisa.

    Key syntax differences from standard SCPI:
      - Channel prefix:  "C1:" not ":CHANnel1"
      - Measurement query:  "C1:PAVA? NWID"  (Parameter Value)
      - Measurement setup:  "PACU NWID,C1"   (Parameter Custom)
      - Header control:  "CHDR OFF" for clean numeric responses
      - Response for invalid/no-signal: 9.9E+37 (Siglent sentinel)
    """

    # Siglent's no-measurement sentinel (returned when signal is absent or
    # the measurement cannot be computed on the current waveform)
    INVALID_SENTINEL = 9.0e+36   # anything above this is treated as NaN

    def __init__(self, resource: str):
        rm = pyvisa.ResourceManager()
        self.inst = rm.open_resource(resource)
        self.inst.timeout = 5000          # ms
        self.inst.write_termination = "\n"
        self.inst.read_termination  = "\n"

        idn = self.inst.query("*IDN?").strip()
        print(f"  Scope identified: {idn}")

        # Suppress response headers so we get bare numeric strings.
        # e.g. without CHDR OFF:  "C1:PAVA NWID,8.32E-03s"
        #      with    CHDR OFF:  "8.32E-03s"
        self.inst.write("CHDR OFF")
        time.sleep(0.1)

    def setup_measurement(self):
        """
        Activate the Negative Width measurement on the configured channel.
        PACU (Parameter Custom) adds the measurement to the display and
        makes it available for PAVA? queries.
        """
        self.inst.write(f"PACU NWID,{SCOPE_CHANNEL}")
        time.sleep(0.2)   # give the scope a moment to compute the first value

    def _parse_siglent_value(self, raw: str) -> float:
        """
        Parse a Siglent PAVA response into a plain float (seconds).

        With CHDR OFF the scope returns strings like:
          "8.320000E-03s"   →  0.00832
          "9.9E+37"         →  NaN  (sentinel for no/invalid measurement)
          "---"             →  NaN  (some firmware versions)

        The unit suffix (s, ms, µs, ns) is stripped and SI conversion applied.
        """
        raw = raw.strip()

        if not raw or raw == "---":
            return float("nan")

        # Strip common unit suffixes.  Siglent always returns SI base units
        # when CHDR is OFF, so the suffix should always be 's', but be safe.
        unit_map = {"ns": 1e-9, "us": 1e-6, "µs": 1e-6, "ms": 1e-3, "s": 1.0}
        for suffix, scale in unit_map.items():
            if raw.endswith(suffix):
                raw = raw[: -len(suffix)]
                try:
                    val = float(raw) * scale
                except ValueError:
                    return float("nan")
                break
        else:
            try:
                val = float(raw)   # plain number, already in seconds
            except ValueError:
                return float("nan")

        if val > self.INVALID_SENTINEL:
            return float("nan")

        return val

    def measure_on_time(self) -> float:
        """
        Query Negative Width (NWID) on the configured channel.
        Returns on-time in seconds, or NaN if the scope cannot measure.
        """
        try:
            raw = self.inst.query(f"{SCOPE_CHANNEL}:PAVA? NWID").strip()
            return self._parse_siglent_value(raw)
        except pyvisa.errors.VisaIOError:
            return float("nan")

    def close(self):
        # Restore default header mode before disconnecting
        try:
            self.inst.write("CHDR SHORT")
        except Exception:
            pass
        self.inst.close()


def list_visa_resources():
    rm = pyvisa.ResourceManager()
    resources = rm.list_resources()
    print("\nAvailable VISA resources:")
    if resources:
        for r in resources:
            tag = "  ← likely your SIGLENT scope" if "F4ED" in r.upper() else ""
            print(f"  {r}{tag}")
    else:
        print("  None found.")
        print("  • Check the USB cable is plugged into the scope's USB-B (rear) port.")
        print("  • On Windows: install the Siglent USB driver or use Zadig to bind")
        print("    VID 0xF4ED / PID 0xEE3A to WinUSB/libusb-win32.")
        print("  • LAN alternative: enable LAN on the scope (Utility → I/O → LAN)")
        print("    then use resource string  \"TCPIP0::<scope_ip>::INSTR\"")
    print("\nSet SCOPE_RESOURCE in the CONFIG block to one of the above, then re-run.")


def run_sweep(arduino: Arduino, scope: Oscilloscope) -> pd.DataFrame:
    """
    Sweep wiper from position 99 (10 kΩ) down to 0, measuring on-time
    at each step with STEP_INTERVAL_S between steps.
    """
    results = []

    print(f"\n{'Pos':>4}  {'R_ideal (Ω)':>12}  {'On-time (µs)':>14}")
    print("-" * 36)

    # Start at maximum resistance
    arduino.goto(POT_MAX_POS)
    time.sleep(SETTLE_TIME_S)
    scope.setup_measurement()

    for pos in range(POT_MAX_POS, POT_MIN_POS - 1, -1):
        # Move pot
        confirmed_pos = arduino.goto(pos)
        time.sleep(SETTLE_TIME_S)

        # Measure
        on_time_s = scope.measure_on_time()
        on_time_us = on_time_s * 1e6 if not (on_time_s != on_time_s) else float("nan")

        r_ideal = ideal_resistance(pos)

        print(f"{confirmed_pos:>4}  {r_ideal:>12.1f}  {on_time_us:>13.2f} µs")

        results.append({
            "position":     confirmed_pos,
            "R_ideal_ohm":  round(r_ideal, 2),
            "on_time_s":    on_time_s,
            "on_time_us":   on_time_us,
        })

        # Wait the remainder of the 1-second interval
        time.sleep(max(0, STEP_INTERVAL_S - SETTLE_TIME_S))

    return pd.DataFrame(results)


def save_csv(df: pd.DataFrame):
    df.to_csv(CSV_OUTPUT, index=False)
    print(f"\nData saved to: {CSV_OUTPUT}")


def plot_results(df: pd.DataFrame):
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("EET321 Lab 3 – SCR On-Time Characterization", fontsize=13, fontweight="bold")

    # On-time vs. wiper position
    ax1 = axes[0]
    ax1.plot(df["position"], df["on_time_us"], "o-", color="steelblue", markersize=4)
    ax1.set_xlabel("Wiper Position (0 = min, 99 = 10 kΩ)")
    ax1.set_ylabel("SCR On-Time (µs)")
    ax1.set_title("On-Time vs. Wiper Position")
    ax1.grid(True, alpha=0.4)
    ax1.invert_xaxis()  # 99→0 left-to-right mirrors the sweep

    # On-time vs. ideal resistance
    ax2 = axes[1]
    ax2.plot(df["R_ideal_ohm"], df["on_time_us"], "o-", color="darkorange", markersize=4)
    ax2.set_xlabel("Ideal Resistance (Ω)")
    ax2.set_ylabel("SCR On-Time (µs)")
    ax2.set_title("On-Time vs. Gate Resistance")
    ax2.grid(True, alpha=0.4)

    plt.tight_layout()
    plt.savefig(PLOT_OUTPUT, dpi=150)
    print(f"Plot saved to:  {PLOT_OUTPUT}")
    plt.show()


def main():
    print("=" * 60)
    print("  EET321 Lab 3 — SCR Characterization (Automated)")
    print("=" * 60)

    # ── Scope resource check ──────────────────────────────────────────────────
    if SCOPE_RESOURCE is None:
        print("\nSCOPE_RESOURCE is not set. Listing available VISA resources...\n")
        list_visa_resources()
        sys.exit(0)

    # ── Connect Arduino ───────────────────────────────────────────────────────
    port = ARDUINO_PORT or find_arduino_port()
    print(f"\n[1/3] Connecting to Arduino on {port}...")
    arduino = Arduino(port, ARDUINO_BAUD)
    arduino.handshake()

    # ── Connect oscilloscope ──────────────────────────────────────────────────
    print(f"\n[2/3] Connecting to oscilloscope ({SCOPE_RESOURCE})...")
    scope = Oscilloscope(SCOPE_RESOURCE)
    scope.setup_measurement()

    # ── Run sweep ─────────────────────────────────────────────────────────────
    print(f"\n[3/3] Starting sweep: position 99 → 0 ({POT_TOTAL_OHMS} Ω → 0 Ω)")
    print(f"      {STEP_INTERVAL_S}s interval per step  |  ~{POT_POSITIONS}s total\n")

    try:
        df = run_sweep(arduino, scope)
    finally:
        # Always return pot to minimum before disconnecting
        arduino.goto(POT_MIN_POS)
        arduino.close()
        scope.close()

    # ── Save & plot ───────────────────────────────────────────────────────────
    save_csv(df)
    plot_results(df)

    # ── Summary stats ─────────────────────────────────────────────────────────
    valid = df["on_time_us"].dropna()
    print(f"\nSummary:")
    print(f"  Positions measured : {len(df)}")
    print(f"  Valid readings     : {len(valid)}")
    print(f"  On-time range      : {valid.min():.2f} µs  –  {valid.max():.2f} µs")
    print(f"  Mean on-time       : {valid.mean():.2f} µs")


if __name__ == "__main__":
    main()
