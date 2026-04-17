"""
Schema Validation Tests
=======================
인터페이스 문서 v1.9 기준 페이로드 포맷 자동 검증

실행:
    uv run pytest tests/test_schema.py -v
    uv run pytest tests/test_schema.py -v --tb=short
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# ── Interface Spec v1.9 ───────────────────────────────────────────────────────

REQUIRED_KEYS = {"sb_id", "device_id", "type", "value", "unit", "ts"}

SENSOR_SPECS = {
    "temperature": {"unit": "C",   "device_id": "SS-P001", "topic": "sensors/device01/data"},
    "humidity":    {"unit": "%",   "device_id": "SS-P002", "topic": "sensors/device02/data"},
    "arc":         {"unit": "-",   "device_id": "SS-P003", "topic": "sensors/device03/data"},
    "vibration":   {"unit": "Hz",  "device_id": "SS-P004", "topic": "sensors/device04/data"},
    "co":          {"unit": "PPM", "device_id": "SS-P002", "topic": "sensors/device02/data"},
    "tobacco":     {"unit": "%",   "device_id": "SS-P003", "topic": "sensors/device03/data"},
}

PROJECT_PROFILES = {
    "project1": ["temperature", "humidity", "arc", "vibration"],
    "project2": ["temperature", "vibration", "co", "tobacco"],
}

AI_TOPIC = "sb/dashboard/data"

SCENARIOS_DIR = Path(__file__).parent / "scenarios"


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_scenario(name: str) -> dict:
    path = SCENARIOS_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


# ── Sensor Payload Tests ──────────────────────────────────────────────────────

class TestSensorPayloadStructure:
    """Interface spec: sensor payload must have required fields with correct types."""

    @pytest.mark.parametrize("sensor_type", list(SENSOR_SPECS.keys()))
    def test_required_keys_present(self, sensor_type):
        scenario = load_scenario("normal")
        packets = scenario.get("sensor_packets", {})
        if sensor_type not in packets:
            pytest.skip(f"Sensor '{sensor_type}' not in scenario")
        packet = packets[sensor_type]
        missing = REQUIRED_KEYS - set(packet.keys())
        assert not missing, f"Missing keys in '{sensor_type}' packet: {missing}"

    @pytest.mark.parametrize("sensor_type", list(SENSOR_SPECS.keys()))
    def test_value_is_numeric(self, sensor_type):
        scenario = load_scenario("normal")
        packets = scenario.get("sensor_packets", {})
        if sensor_type not in packets:
            pytest.skip(f"Sensor '{sensor_type}' not in scenario")
        packet = packets[sensor_type]
        value = packet.get("value")
        assert isinstance(value, (int, float)), f"value must be numeric, got {type(value)}"

    @pytest.mark.parametrize("sensor_type", list(SENSOR_SPECS.keys()))
    def test_value_precision_one_decimal(self, sensor_type):
        """Interface spec: value must have at most 1 decimal place."""
        scenario = load_scenario("normal")
        packets = scenario.get("sensor_packets", {})
        if sensor_type not in packets:
            pytest.skip(f"Sensor '{sensor_type}' not in scenario")
        value = packets[sensor_type].get("value")
        if not isinstance(value, float):
            return
        assert round(value, 1) == value or abs(value - round(value, 1)) < 1e-9, \
            f"'{sensor_type}' value {value} has more than 1 decimal place"

    @pytest.mark.parametrize("sensor_type,spec", SENSOR_SPECS.items())
    def test_unit_matches_spec(self, sensor_type, spec):
        scenario = load_scenario("normal")
        packets = scenario.get("sensor_packets", {})
        if sensor_type not in packets:
            pytest.skip(f"Sensor '{sensor_type}' not in scenario")
        actual_unit = packets[sensor_type].get("unit")
        assert actual_unit == spec["unit"], \
            f"Unit mismatch for '{sensor_type}': got '{actual_unit}', expected '{spec['unit']}'"

    @pytest.mark.parametrize("sensor_type,spec", SENSOR_SPECS.items())
    def test_device_id_matches_spec(self, sensor_type, spec):
        scenario = load_scenario("normal")
        packets = scenario.get("sensor_packets", {})
        if sensor_type not in packets:
            pytest.skip(f"Sensor '{sensor_type}' not in scenario")
        actual_did = packets[sensor_type].get("device_id")
        assert actual_did == spec["device_id"], \
            f"device_id mismatch for '{sensor_type}': got '{actual_did}', expected '{spec['device_id']}'"

    @pytest.mark.parametrize("sensor_type", list(SENSOR_SPECS.keys()))
    def test_timestamp_format(self, sensor_type):
        scenario = load_scenario("normal")
        packets = scenario.get("sensor_packets", {})
        if sensor_type not in packets:
            pytest.skip(f"Sensor '{sensor_type}' not in scenario")
        ts = packets[sensor_type].get("ts", "")
        assert isinstance(ts, str) and len(ts) >= 10, \
            f"Invalid timestamp for '{sensor_type}': '{ts}'"
        assert "T" in ts and ts.endswith("Z"), \
            f"Timestamp must be ISO 8601 UTC (ending in Z): '{ts}'"


class TestTopicStructure:
    """Interface spec: topic = sensors/{deviceXX}/data (no sb_id in path)."""

    @pytest.mark.parametrize("sensor_type,spec", SENSOR_SPECS.items())
    def test_topic_no_sb_id(self, sensor_type, spec):
        topic = spec["topic"]
        parts = topic.split("/")
        assert parts[0] == "sensors", f"Topic must start with 'sensors/': {topic}"
        assert parts[-1] == "data",   f"Topic must end with '/data': {topic}"
        assert len(parts) == 3,       f"Topic must be 3 parts (sensors/deviceXX/data): {topic}"

    def test_ai_topic(self):
        assert AI_TOPIC == "sb/dashboard/data", \
            f"AI topic must be 'sb/dashboard/data', got '{AI_TOPIC}'"


class TestProjectProfiles:
    """Project 1 and Project 2 must use correct and distinct sensor sets."""

    def test_project1_sensors(self):
        p1 = set(PROJECT_PROFILES["project1"])
        assert p1 == {"temperature", "humidity", "arc", "vibration"}

    def test_project2_sensors(self):
        p2 = set(PROJECT_PROFILES["project2"])
        assert p2 == {"temperature", "vibration", "co", "tobacco"}

    def test_projects_share_temperature_and_vibration(self):
        shared = set(PROJECT_PROFILES["project1"]) & set(PROJECT_PROFILES["project2"])
        assert "temperature" in shared
        assert "vibration" in shared

    def test_project1_has_no_gas_sensors(self):
        p1 = set(PROJECT_PROFILES["project1"])
        assert "co" not in p1
        assert "tobacco" not in p1

    def test_project2_has_no_electrical_sensors(self):
        p2 = set(PROJECT_PROFILES["project2"])
        assert "humidity" not in p2
        assert "arc" not in p2


class TestScenarioPackets:
    """Scenario JSON files must produce valid packets for both projects."""

    @pytest.mark.parametrize("scenario_name", ["normal", "fire_overload", "breakdown"])
    def test_scenario_has_required_fields(self, scenario_name):
        scenario = load_scenario(scenario_name)
        assert "scenario" in scenario
        assert "profile" in scenario
        assert "sensor_packets" in scenario

    @pytest.mark.parametrize("scenario_name", ["normal", "fire_overload", "breakdown"])
    def test_scenario_packets_valid(self, scenario_name):
        scenario = load_scenario(scenario_name)
        packets = scenario.get("sensor_packets", {})
        for sensor_type, packet in packets.items():
            missing = REQUIRED_KEYS - set(packet.keys())
            assert not missing, \
                f"[{scenario_name}] Packet '{sensor_type}' missing keys: {missing}"
            assert isinstance(packet.get("value"), (int, float)), \
                f"[{scenario_name}] Packet '{sensor_type}' value must be numeric"
