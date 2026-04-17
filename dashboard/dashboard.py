"""
DTFP Demo Dashboard
===================
풀 파이프라인 시연 + 클라이언트 데모용 Streamlit 대시보드

실행:
    uv run streamlit run dashboard/dashboard.py
"""
from __future__ import annotations

import json
import queue
import threading
import time
from datetime import datetime

import paho.mqtt.client as mqtt
import streamlit as st

# ── Constants ─────────────────────────────────────────────────────────────────

SENSOR_TOPICS = [
    "sensors/device01/data",
    "sensors/device02/data",
    "sensors/device03/data",
    "sensors/device04/data",
]
AI_TOPIC = "sb/dashboard/data"

PROJECT_SENSORS = {
    "Project 1 — 전기 구조 모니터링": {
        "types": ["temperature", "humidity", "arc", "vibration"],
        "units": {"temperature": "°C", "humidity": "%", "arc": "—", "vibration": "Hz"},
        "labels": {"temperature": "🌡 온도", "humidity": "💧 습도", "arc": "⚡ 아크", "vibration": "📳 진동"},
    },
    "Project 2 — 화재/가스 감지 (포유파워)": {
        "types": ["temperature", "vibration", "co", "tobacco"],
        "units": {"temperature": "°C", "vibration": "Hz", "co": "PPM", "tobacco": "%"},
        "labels": {"temperature": "🌡 온도", "vibration": "📳 진동", "co": "☁️ CO", "tobacco": "🚬 연기"},
    },
}

THREAT_COLORS = {
    "normal":           "#888888",
    "insulation_aging": "#ccaa00",
    "fire_overload":    "#cc2222",
    "condensation":     "#4488bb",
    "breakdown":        "#9944aa",
}

WARNING_COLORS = {
    "Normal (정상)":   "#33aa55",
    "Caution (주의)":  "#ccaa00",
    "Warning (경고)":  "#dd8800",
    "Danger (위험)":   "#cc2222",
}

# ── Session state init ────────────────────────────────────────────────────────

def _init_state():
    defaults = {
        "mqtt_client":   None,
        "connected":     False,
        "msg_queue":     queue.Queue(maxsize=200),
        "sensor_latest": {},     # type → latest value
        "ai_latest":     {},     # latest AI result dict
        "sensor_history":{},     # type → list of (ts, value)
        "schema_errors": [],
        "msg_counts":    {"sensor": 0, "ai": 0, "error": 0},
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

# ── MQTT ──────────────────────────────────────────────────────────────────────

def _mqtt_connect(broker: str, port: int):
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        client = mqtt.Client()

    def on_connect(c, *args):
        for t in SENSOR_TOPICS + [AI_TOPIC]:
            c.subscribe(t)
        st.session_state.connected = True

    def on_disconnect(*args):
        st.session_state.connected = False

    def on_message(c, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8", errors="ignore"))
            st.session_state.msg_queue.put_nowait(
                {"topic": msg.topic, "data": data}
            )
        except Exception:
            pass

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect(broker, port)
    client.loop_start()
    return client


def _drain_queue(active_types: list[str]):
    q = st.session_state.msg_queue
    processed = 0
    while not q.empty() and processed < 50:
        item = q.get_nowait()
        topic = item["topic"]
        data  = item["data"]
        processed += 1

        if topic == AI_TOPIC:
            st.session_state.ai_latest = data
            st.session_state.msg_counts["ai"] += 1
        else:
            sensor_type = data.get("type", "")
            value = data.get("value")
            if sensor_type in active_types and isinstance(value, (int, float)):
                st.session_state.sensor_latest[sensor_type] = data
                st.session_state.msg_counts["sensor"] += 1
                ts = datetime.now()
                hist = st.session_state.sensor_history.setdefault(sensor_type, [])
                hist.append((ts, float(value)))
                if len(hist) > 60:
                    hist.pop(0)

# ── UI ────────────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="DTFP Demo Dashboard",
        page_icon="🛡️",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _init_state()

    # ── Sidebar ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.title("🛡️ DTFP Demo")
        st.caption("AI 기반 배전반 예측 유지보수 시스템")
        st.divider()

        st.subheader("📡 MQTT 연결")
        broker = st.text_input("Broker", value="broker.emqx.io")
        port   = st.number_input("Port", value=1883, step=1)

        col1, col2 = st.columns(2)
        with col1:
            connect_btn = st.button("🔌 연결", use_container_width=True, type="primary")
        with col2:
            disconnect_btn = st.button("⏹ 해제", use_container_width=True)

        if connect_btn:
            if st.session_state.mqtt_client:
                st.session_state.mqtt_client.loop_stop()
                st.session_state.mqtt_client.disconnect()
            try:
                st.session_state.mqtt_client = _mqtt_connect(broker, port)
                st.success(f"연결 요청: {broker}:{port}")
            except Exception as e:
                st.error(f"연결 실패: {e}")

        if disconnect_btn and st.session_state.mqtt_client:
            st.session_state.mqtt_client.loop_stop()
            st.session_state.mqtt_client.disconnect()
            st.session_state.connected = False
            st.session_state.mqtt_client = None

        st.divider()
        st.subheader("🧩 프로젝트 프로필")
        profile_name = st.selectbox("", list(PROJECT_SENSORS.keys()), label_visibility="collapsed")
        profile = PROJECT_SENSORS[profile_name]
        active_types = profile["types"]

        st.divider()
        st.subheader("📊 통계")
        mc = st.session_state.msg_counts
        st.metric("센서 수신", mc["sensor"])
        st.metric("AI 결과", mc["ai"])
        err_color = "normal" if mc["error"] == 0 else "inverse"
        st.metric("스키마 오류", mc["error"], delta_color=err_color)

        if st.button("🔄 초기화", use_container_width=True):
            st.session_state.sensor_latest = {}
            st.session_state.ai_latest = {}
            st.session_state.sensor_history = {}
            st.session_state.msg_counts = {"sensor": 0, "ai": 0, "error": 0}

    # ── Main area ─────────────────────────────────────────────────────────────
    _drain_queue(active_types)

    # Connection status banner
    if st.session_state.connected:
        st.success(f"🟢 MQTT 연결됨 | 구독 토픽: {len(SENSOR_TOPICS + [AI_TOPIC])}개")
    else:
        st.warning("🔴 오프라인 — 사이드바에서 브로커 연결하세요")

    st.divider()

    # ── AI Result Banner ──────────────────────────────────────────────────────
    ai = st.session_state.ai_latest
    if ai:
        state_str = ai.get("state", "unknown")
        parts = state_str.rsplit("_", 1)
        pred_class = parts[0] if len(parts) == 2 else state_str
        severity   = parts[1].upper() if len(parts) == 2 else "UNKNOWN"

        color = WARNING_COLORS.get(
            {"critical": "Danger (위험)", "warning": "Warning (경고)",
             "caution": "Caution (주의)", "normal": "Normal (정상)"}.get(severity.lower(), "Normal (정상)"),
            "#888888"
        )
        st.markdown(
            f'<div style="background:{color};padding:12px 20px;border-radius:8px;'
            f'color:white;font-size:18px;font-weight:bold;text-align:center;">'
            f'AI 판정: {pred_class.upper()} — {severity}</div>',
            unsafe_allow_html=True,
        )
        st.caption(f"마지막 추론: {ai.get('timestamp', '—')}")
        st.divider()

    # ── Sensor Metrics ────────────────────────────────────────────────────────
    st.subheader("📈 실시간 센서 데이터")
    cols = st.columns(len(active_types))
    for i, sensor_type in enumerate(active_types):
        label = profile["labels"][sensor_type]
        unit  = profile["units"][sensor_type]
        with cols[i]:
            data = st.session_state.sensor_latest.get(sensor_type)
            if data:
                val = data.get("value", 0)
                st.metric(label, f"{val:.1f} {unit}")
                st.caption(f"ts: {data.get('ts', '—')[-8:]}")
            else:
                st.metric(label, "—")
                st.caption("수신 대기중")

    st.divider()

    # ── AI Probability Bars ───────────────────────────────────────────────────
    if ai:
        st.subheader("🎯 위협 분류 확률")
        ir = ai.get("inference_result", {})
        cols = st.columns(len(ir))
        for i, (cls, prob) in enumerate(sorted(ir.items(), key=lambda x: -x[1])):
            with cols[i]:
                color = THREAT_COLORS.get(cls, "#888888")
                st.markdown(
                    f'<div style="text-align:center;">'
                    f'<div style="font-size:13px;font-weight:bold;color:{color}">{cls}</div>'
                    f'<div style="font-size:22px;font-weight:bold;">{prob:.1%}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                st.progress(float(prob))

    # ── Auto-refresh ──────────────────────────────────────────────────────────
    if st.session_state.connected or not st.session_state.msg_queue.empty():
        time.sleep(0.5)
        st.rerun()


if __name__ == "__main__":
    main()
