"""
spec_loader.py — DTFP Interface Spec Loader
============================================
interface_spec.json (Single Source of Truth) 를 로드하는 공통 유틸.

탐색 순서:
  1. 환경변수 DTFP_SPEC_PATH
  2. 현재 실행 디렉토리 / interface_spec.json
  3. 부모 디렉토리 최대 4단계 탐색
  4. 이 파일과 같은 디렉토리

exe 번들링 시: interface_spec.json 을 exe 옆에 두면 자동 인식.

사용 예:
    from spec_loader import load_spec, get_sensor, get_project_sensors

    spec = load_spec()
    temp = get_sensor("temperature")   # → {"unit": "C", "label_ko": "온도", ...}
    sensors = get_project_sensors("project1")  # → ["temperature", "humidity", ...]
"""
from __future__ import annotations

import json
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

_SPEC_FILENAME = "interface_spec.json"


def _find_spec_path() -> Path:
    # 1. 환경변수
    env_path = os.environ.get("DTFP_SPEC_PATH")
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return p
        if p.is_dir():
            candidate = p / _SPEC_FILENAME
            if candidate.is_file():
                return candidate

    # 2. exe 번들 (PyInstaller sys._MEIPASS)
    if hasattr(sys, "_MEIPASS"):
        candidate = Path(sys._MEIPASS) / _SPEC_FILENAME  # type: ignore[attr-defined]
        if candidate.is_file():
            return candidate

    # 3. 실행 파일/스크립트 디렉토리에서 상위로 탐색
    search_roots = [
        Path.cwd(),
        Path(sys.argv[0]).resolve().parent if sys.argv[0] else Path.cwd(),
        Path(__file__).resolve().parent,
    ]
    for root in search_roots:
        for level in range(5):
            candidate = root / (_SPEC_FILENAME if level == 0 else "../" * level + _SPEC_FILENAME)
            candidate = candidate.resolve()
            if candidate.is_file():
                return candidate

    raise FileNotFoundError(
        f"'{_SPEC_FILENAME}' 을 찾을 수 없습니다.\n"
        f"환경변수 DTFP_SPEC_PATH 에 경로를 지정하거나, "
        f"실행 디렉토리 또는 상위 폴더에 파일을 위치시키세요."
    )


@lru_cache(maxsize=1)
def load_spec() -> dict[str, Any]:
    """interface_spec.json 을 로드하고 캐싱합니다."""
    path = _find_spec_path()
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def reload_spec() -> dict[str, Any]:
    """캐시를 무효화하고 spec 을 다시 로드합니다 (핫리로드용)."""
    load_spec.cache_clear()
    return load_spec()


# ── 편의 함수 ────────────────────────────────────────────────────────────────

def get_sensor(sensor_type: str) -> dict[str, Any]:
    """센서 스펙 반환. 예: get_sensor("temperature") → {"unit": "C", ...}"""
    sensors = load_spec()["sensors"]
    if sensor_type not in sensors:
        raise KeyError(f"Unknown sensor type: '{sensor_type}'. Available: {list(sensors)}")
    return sensors[sensor_type]


def get_all_sensors() -> dict[str, dict[str, Any]]:
    """전체 센서 스펙 딕셔너리 반환."""
    return load_spec()["sensors"]


def get_project(project_id: str) -> dict[str, Any]:
    """프로젝트 스펙 반환. 예: get_project("project1")"""
    projects = load_spec()["projects"]
    if project_id not in projects:
        raise KeyError(f"Unknown project: '{project_id}'. Available: {list(projects)}")
    return projects[project_id]


def get_project_sensors(project_id: str) -> list[str]:
    """프로젝트에 속한 센서 타입 리스트 반환."""
    return get_project(project_id)["sensors"]


def get_all_projects() -> dict[str, dict[str, Any]]:
    """전체 프로젝트 스펙 반환."""
    return load_spec()["projects"]


def get_thresholds(sensor_type: str) -> list[tuple[float, str]]:
    """임계값 리스트 반환. [(값, 색상코드), ...]"""
    thresholds = load_spec().get("thresholds", {})
    return [(t[0], t[1]) for t in thresholds.get(sensor_type, [])]


def get_threat_classes() -> dict[str, dict[str, Any]]:
    """위협 클래스 스펙 반환 (label_ko, color)."""
    return load_spec()["threat_classes"]


def get_severity_levels() -> dict[str, dict[str, Any]]:
    """심각도 레벨 스펙 반환 (color, icon)."""
    return load_spec()["severity_levels"]


def get_mqtt_config() -> dict[str, Any]:
    """MQTT 설정 반환 (topic 패턴, AI 발행 토픽, 기본 브로커)."""
    return load_spec()["mqtt"]


def get_sensor_topic(sensor_type: str) -> str:
    """센서 타입으로 MQTT 토픽 반환. 예: "sensors/device01/data" """
    return get_sensor(sensor_type)["topic"]


def get_feature_topic_map() -> dict[str, str]:
    """mqtt_client.py 호환: {sensor_type: device_suffix} 딕셔너리 반환."""
    return {k: v["device_suffix"] for k, v in get_all_sensors().items()}


def get_sensor_registry_args() -> dict[str, tuple[str, str, str, str, str]]:
    """Generater.py 호환: {DisplayName: (sb_id, device_id, type, unit, device_suffix)}"""
    spec = load_spec()
    sb_id = spec["sb_id"]
    result = {}
    for type_name, s in spec["sensors"].items():
        display = s["label_en"]
        result[display] = (sb_id, s["device_id"], type_name, s["unit"], s["device_suffix"])
    return result


def build_project_sensors_dict() -> dict[str, dict[str, Any]]:
    """dashboard.py 호환: PROJECT_SENSORS 구조 빌드."""
    spec = load_spec()
    result = {}
    for proj_id, proj in spec["projects"].items():
        sensor_types = proj["sensors"]
        entry: dict[str, Any] = {
            "types":  sensor_types,
            "units":  {t: spec["sensors"][t]["unit"]     for t in sensor_types},
            "labels": {t: spec["sensors"][t]["label_ko"] for t in sensor_types},
            "icons":  {t: spec["sensors"][t]["icon"]     for t in sensor_types},
        }
        result[proj["display_ko"]] = entry
    return result
