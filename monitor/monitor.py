"""
DTFP Pipeline Monitor
=====================
MQTT 토픽 실시간 감청 + 페이로드 스키마 자동 검증

실행:
    uv run python monitor/monitor.py
    uv run python monitor/monitor.py --broker broker.emqx.io --profile project2
    uv run python monitor/monitor.py --broker 192.168.0.100 --verbose
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from typing import Any

import paho.mqtt.client as mqtt
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# ── Interface Spec v1.9 ─────────────────────────────────────────────────────

SENSOR_TOPICS = [
    "sensors/device01/data",
    "sensors/device02/data",
    "sensors/device03/data",
    "sensors/device04/data",
    "sensors/device05/data",
]
AI_TOPIC = "sb/dashboard/data"
REQUIRED_KEYS = {"sb_id", "device_id", "type", "value", "unit", "ts"}

EXPECTED_SCHEMA: dict[str, dict] = {
    "temperature": {"unit": "C",   "range": (0, 200)},
    "humidity":    {"unit": "%",   "range": (0, 100)},
    "arc":         {"unit": "-",   "range": (0, 1)},
    "vibration":   {"unit": "Hz",  "range": (0, 200)},
    "co":          {"unit": "PPM", "range": (0, 500)},
    "tobacco":     {"unit": "%",   "range": (0, 100)},
}

PROJECT_PROFILES = {
    "project1": ["temperature", "humidity", "arc", "vibration"],
    "project2": ["temperature", "vibration", "co", "tobacco"],
    "all":      list(EXPECTED_SCHEMA.keys()),
}

# ── State ────────────────────────────────────────────────────────────────────

console = Console()

class MonitorState:
    def __init__(self, profile: str, verbose: bool):
        self.profile = profile
        self.verbose = verbose
        self.expected_types = set(PROJECT_PROFILES.get(profile, PROJECT_PROFILES["all"]))
        self.sensor_log: list[dict] = []       # last N sensor messages
        self.ai_log: list[dict] = []           # last N AI result messages
        self.schema_errors: list[str] = []     # schema violations
        self.msg_count = {"sensor": 0, "ai": 0, "error": 0}
        self.last_update = datetime.now()
        self.connected = False
        self.broker = ""

    def add_sensor(self, topic: str, data: dict, violations: list[str]) -> None:
        self.msg_count["sensor"] += 1
        if violations:
            self.msg_count["error"] += len(violations)
            self.schema_errors.extend(violations[-3:])
        entry = {"topic": topic, "data": data, "violations": violations, "ts": datetime.now()}
        self.sensor_log.append(entry)
        if len(self.sensor_log) > 20:
            self.sensor_log.pop(0)
        self.last_update = datetime.now()

    def add_ai(self, data: dict) -> None:
        self.msg_count["ai"] += 1
        self.ai_log.append({"data": data, "ts": datetime.now()})
        if len(self.ai_log) > 5:
            self.ai_log.pop(0)
        self.last_update = datetime.now()


def validate_sensor_payload(payload: dict[str, Any], profile_types: set[str]) -> list[str]:
    """Returns list of schema violations (empty = valid)."""
    violations = []

    # Required keys
    missing = REQUIRED_KEYS - payload.keys()
    if missing:
        violations.append(f"Missing keys: {missing}")
        return violations  # Can't check further without keys

    sensor_type = payload.get("type", "")
    value = payload.get("value")
    unit = payload.get("unit", "")

    # Type recognition
    if sensor_type not in EXPECTED_SCHEMA:
        violations.append(f"Unknown type: '{sensor_type}'")
        return violations

    spec = EXPECTED_SCHEMA[sensor_type]

    # Unit check
    if unit != spec["unit"]:
        violations.append(f"Unit mismatch: got '{unit}', expected '{spec['unit']}'")

    # Value type
    if not isinstance(value, (int, float)):
        violations.append(f"value is not numeric: {type(value).__name__}")
    else:
        lo, hi = spec["range"]
        if not (lo <= value <= hi):
            violations.append(f"Value {value} out of range [{lo}, {hi}]")

        # Decimal precision (spec: 1 decimal place)
        rounded = round(value, 1)
        if abs(value - rounded) > 0.05:
            violations.append(f"Precision: {value} has more than 1 decimal place")

    # Timestamp format
    ts = payload.get("ts", "")
    if not isinstance(ts, str) or len(ts) < 10:
        violations.append(f"Invalid timestamp: '{ts}'")

    return violations


# ── Rendering ────────────────────────────────────────────────────────────────

def build_table(state: MonitorState) -> Table:
    table = Table(
        title=f"DTFP Pipeline Monitor — Profile: [bold cyan]{state.profile}[/] | "
              f"Broker: [dim]{state.broker}[/]",
        show_lines=True,
        expand=True,
    )
    table.add_column("Time", width=10, style="dim")
    table.add_column("Topic", width=24, style="cyan")
    table.add_column("Type", width=12)
    table.add_column("Value", width=10, justify="right")
    table.add_column("Unit", width=6)
    table.add_column("Schema", width=8)
    table.add_column("sb_id", width=22, style="dim")

    # Show last 12 sensor messages
    for entry in state.sensor_log[-12:]:
        d = entry["data"]
        ts_str = entry["ts"].strftime("%H:%M:%S")
        t = d.get("type", "?")
        v = d.get("value", "?")
        u = d.get("unit", "?")
        sb = d.get("sb_id", "?")
        topic = entry["topic"].replace("sensors/", "s/")

        if entry["violations"]:
            schema_cell = Text("❌ ERR", style="bold red")
        else:
            schema_cell = Text("✅ OK", style="green")

        val_str = f"{v:.1f}" if isinstance(v, float) else str(v)
        table.add_row(ts_str, topic, t, val_str, u, schema_cell, sb)

    return table


def build_ai_panel(state: MonitorState) -> Panel:
    if not state.ai_log:
        return Panel("[dim]Waiting for AI results on sb/dashboard/data...[/]",
                     title="🤖 AI Inference", border_style="dim")

    latest = state.ai_log[-1]["data"]
    lines = []

    ir = latest.get("inference_result", {})
    state_str = latest.get("state", "—")
    ts = latest.get("timestamp", "—")

    lines.append(f"[bold]State:[/] [yellow]{state_str}[/]   ts: [dim]{ts}[/]")
    lines.append("")

    for cls, prob in sorted(ir.items(), key=lambda x: -x[1]):
        bar_len = int(prob * 30)
        bar = "█" * bar_len + "░" * (30 - bar_len)
        color = "red" if prob > 0.7 else "yellow" if prob > 0.3 else "green"
        lines.append(f"[{color}]{cls:<20}[/] [{color}]{bar}[/] {prob:.4f}")

    return Panel("\n".join(lines), title="🤖 AI Inference", border_style="blue")


def build_stats(state: MonitorState) -> str:
    conn = "[green]CONNECTED[/]" if state.connected else "[red]DISCONNECTED[/]"
    errs = f"[red]{state.msg_count['error']}[/]" if state.msg_count["error"] else "[green]0[/]"
    last = state.last_update.strftime("%H:%M:%S")
    return (
        f"{conn}  Sensor msgs: [cyan]{state.msg_count['sensor']}[/]  "
        f"AI msgs: [blue]{state.msg_count['ai']}[/]  "
        f"Schema errors: {errs}  "
        f"Last msg: [dim]{last}[/]"
    )


# ── MQTT Handlers ─────────────────────────────────────────────────────────────

def make_handlers(state: MonitorState, verbose: bool):
    def on_connect(client, userdata, flags, rc, *args):
        state.connected = True
        topics = SENSOR_TOPICS + [AI_TOPIC]
        for t in topics:
            client.subscribe(t)
        if verbose:
            console.log(f"[green]Connected. Subscribed to {len(topics)} topics.[/]")

    def on_disconnect(client, userdata, rc, *args):
        state.connected = False

    def on_message(client, userdata, msg):
        try:
            raw = msg.payload.decode("utf-8", errors="ignore")
            data = json.loads(raw)
        except Exception:
            state.msg_count["error"] += 1
            return

        topic = msg.topic
        if topic == AI_TOPIC:
            state.add_ai(data)
        else:
            violations = validate_sensor_payload(data, state.expected_types)
            state.add_sensor(topic, data, violations)
            if verbose and violations:
                console.log(f"[red]Schema violation on {topic}: {violations}[/]")

    return on_connect, on_disconnect, on_message


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="DTFP Pipeline Monitor")
    parser.add_argument("--broker", default="broker.emqx.io")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--profile", choices=["project1", "project2", "all"], default="all")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    state = MonitorState(profile=args.profile, verbose=args.verbose)
    state.broker = f"{args.broker}:{args.port}"

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        client = mqtt.Client()

    on_connect, on_disconnect, on_message = make_handlers(state, args.verbose)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    console.print(f"[bold]DTFP Monitor[/] connecting to [cyan]{args.broker}:{args.port}[/]...")
    try:
        client.connect(args.broker, args.port)
        client.loop_start()
    except Exception as e:
        console.print(f"[red]Connection failed: {e}[/]")
        sys.exit(1)

    try:
        with Live(console=console, refresh_per_second=2) as live:
            while True:
                from rich.columns import Columns
                sensor_table = build_table(state)
                ai_panel = build_ai_panel(state)
                stats_text = build_stats(state)
                live.update(
                    Panel(
                        Columns([sensor_table, ai_panel], equal=False),
                        subtitle=stats_text,
                        border_style="dim",
                    )
                )
                time.sleep(0.5)
    except KeyboardInterrupt:
        console.print("\n[yellow]Monitor stopped.[/]")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
