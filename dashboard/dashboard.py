"""
DTFP Demo Dashboard — v2
========================
풀 파이프라인 시연 + 클라이언트 데모용 Streamlit 대시보드

실행:
    uv run streamlit run dashboard/dashboard.py
"""
from __future__ import annotations

import json
import queue
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import paho.mqtt.client as mqtt
import streamlit as st

# ── 전역 MQTT 상태 (모듈 재로드 + rerun 사이클 모두 생존) ────────────────────
@st.cache_resource
def _get_mqtt_state() -> dict:
    """모듈 재로드와 rerun에서 모두 살아남는 MQTT 상태 컨테이너."""
    return {
        "client":    None,
        "queue":     queue.Queue(maxsize=500),
        "connected": threading.Event(),
    }


def _g_state() -> dict:
    return _get_mqtt_state()


def _g_client_get() -> mqtt.Client | None:
    return _g_state()["client"]


def _g_queue_get() -> queue.Queue:
    return _g_state()["queue"]


def _g_connected_get() -> threading.Event:
    return _g_state()["connected"]

# ── spec_loader 경로 추가 (dashboard/ 한 단계 위) ─────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from spec_loader import (  # noqa: E402
    build_project_sensors_dict,
    get_mqtt_config,
    get_severity_levels,
    get_threat_classes,
    get_thresholds,
    load_spec,
)

# ── Constants — interface_spec.json SSoT 로드 ─────────────────────────────────
# ⚠️  이 블록을 직접 수정하지 마세요. interface_spec.json 을 수정하세요.

_spec        = load_spec()
_mqtt_cfg    = get_mqtt_config()
_sev         = get_severity_levels()
_threats     = get_threat_classes()

# 구독할 센서 토픽 (중복 제거)
SENSOR_TOPICS: list[str] = list({
    s["topic"] for s in _spec["sensors"].values()
})
AI_TOPIC: str = _mqtt_cfg["ai_publish_topic"]

# 프로젝트별 센서 딕셔너리 (PROJECT_SENSORS 호환 구조)
PROJECT_SENSORS: dict = build_project_sensors_dict()

# 위협 클래스 색상
THREAT_COLORS: dict[str, str] = {k: v["color"] for k, v in _threats.items()}

# 심각도 색상/아이콘
SEVERITY_COLORS: dict[str, str] = {k: v["color"] for k, v in _sev.items()}
SEVERITY_ICONS:  dict[str, str] = {k: v["icon"]  for k, v in _sev.items()}

# 센서 임계값 (dashboard 렌더링용)
_THRESHOLDS: dict[str, list[tuple[float, str]]] = {
    s: get_thresholds(s) for s in _spec["sensors"]
}

# ── CSS ───────────────────────────────────────────────────────────────────────

_CSS = """
<style>
/* ── Streamlit chrome ───────────────────── */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.2rem; padding-bottom: 0.5rem; }

/* ── App background ─────────────────────── */
.stApp { background-color: #0d1117; }

/* ── Sidebar ────────────────────────────── */
[data-testid="stSidebar"] {
    background-color: #161b22;
    border-right: 1px solid #30363d;
}
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] .stCaption,
[data-testid="stSidebar"] label {
    color: #8b949e !important;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: #c9d1d9 !important;
}
[data-testid="stSidebar"] input {
    background-color: #0d1117 !important;
    color: #c9d1d9 !important;
    border-color: #30363d !important;
    border-radius: 6px !important;
}
[data-testid="stSidebar"] [data-testid="metric-container"] {
    background-color: #0d1117;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 6px 10px;
}
[data-testid="stSidebar"] [data-testid="stMetricValue"] { color: #c9d1d9 !important; font-size: 18px !important; }
[data-testid="stSidebar"] [data-testid="stMetricLabel"] { color: #8b949e !important; font-size: 11px !important; }

/* ── Buttons ────────────────────────────── */
.stButton > button {
    border-radius: 8px !important;
    font-weight: 600 !important;
    letter-spacing: 0.3px;
    transition: opacity 0.15s, transform 0.1s ease;
}
.stButton > button:hover {
    opacity: 0.88;
    transform: translateY(-1px);
}

/* ── Divider ────────────────────────────── */
hr { border-color: #21262d !important; opacity: 1 !important; }

/* ── Main text ──────────────────────────── */
h1, h2, h3 { color: #e6edf3 !important; }
p, span { color: #c9d1d9; }
.stCaption { color: #6e7681 !important; }
</style>
"""

# ── HTML component helpers ────────────────────────────────────────────────────

def _get_sensor_color(sensor_type: str, value: float) -> str:
    """Return threshold-based color for a sensor value."""
    thresholds = _THRESHOLDS.get(sensor_type, [])
    color = "#58a6ff"  # default: blue (in-range emphasis)
    for thresh, c in sorted(thresholds):
        if value >= thresh:
            color = c
    return color


def _sensor_card(icon: str, label: str, value: float | None,
                 unit: str, sensor_type: str, ts_short: str = "") -> str:
    """Render a styled sensor metric card."""
    if value is None:
        return (
            '<div style="background:#161b22;border:1px solid #21262d;border-radius:10px;'
            'padding:16px 12px;text-align:center;min-height:104px;'
            'display:flex;flex-direction:column;justify-content:center;">'
            f'<div style="font-size:20px;margin-bottom:6px;">{icon}</div>'
            f'<div style="font-size:11px;color:#8b949e;margin-bottom:8px;">{label}</div>'
            '<div style="font-size:24px;color:#30363d;font-weight:700;">—</div>'
            '<div style="font-size:10px;color:#484f58;margin-top:4px;">수신 대기</div>'
            '</div>'
        )

    color = _get_sensor_color(sensor_type, value)
    border_col = color if color != "#58a6ff" else "#21262d"
    dot = '<span style="font-size:8px;margin-left:3px;">●</span>' if color != "#58a6ff" else ""
    ts_row = (
        f'<div style="font-size:9px;color:#484f58;margin-top:3px;">{ts_short}</div>'
        if ts_short else ""
    )
    return (
        f'<div style="background:#161b22;border:1px solid {border_col};'
        f'border-top:3px solid {color};border-radius:10px;padding:16px 12px;text-align:center;">'
        f'<div style="font-size:18px;margin-bottom:4px;">{icon}</div>'
        f'<div style="font-size:11px;color:#8b949e;">{label}</div>'
        f'<div style="font-size:26px;font-weight:700;color:{color};'
        f'font-family:\'Courier New\',monospace;margin:6px 0;">{value:.1f}</div>'
        f'<div style="font-size:11px;color:#6e7681;">{unit}'
        f'<span style="color:{color}">{dot}</span></div>'
        f'{ts_row}'
        '</div>'
    )


def _ai_banner(state_str: str, timestamp: str, ai_data: dict) -> str:
    """Render severity-colored AI result banner."""
    parts      = state_str.rsplit("_", 1)
    pred_class = parts[0] if len(parts) == 2 else state_str
    severity   = parts[1].upper() if len(parts) == 2 else "UNKNOWN"

    color = SEVERITY_COLORS.get(severity, "#8b949e")
    icon  = SEVERITY_ICONS.get(severity, "⚪")
    display_class = pred_class.replace("_", " ").upper()
    ts_short = timestamp[-8:] if len(timestamp) >= 8 else timestamp

    ir = ai_data.get("inference_result", {})
    confidence = ir.get("confidence", 0.0) if ir else 0.0
    conf_text  = f"{confidence:.1%}" if confidence > 0 else "—"

    return (
        f'<div style="background:linear-gradient(90deg,{color}18 0%,{color}08 100%);'
        f'border:1px solid {color}44;border-left:4px solid {color};'
        'border-radius:8px;padding:14px 20px;margin:0 0 10px 0;">'
        '<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">'
        f'<div style="display:flex;align-items:center;gap:14px;">'
        f'<span style="font-size:30px;line-height:1;">{icon}</span>'
        '<div>'
        f'<div style="font-size:10px;color:{color}99;font-weight:700;letter-spacing:1.5px;">AI 판정 결과</div>'
        f'<div style="font-size:22px;font-weight:700;color:{color};letter-spacing:0.5px;">{display_class}</div>'
        '</div></div>'
        '<div style="display:flex;gap:24px;">'
        '<div style="text-align:center;">'
        '<div style="font-size:10px;color:#6e7681;margin-bottom:2px;">신뢰도</div>'
        f'<div style="font-size:18px;font-weight:700;font-family:monospace;color:{color};">{conf_text}</div>'
        '</div>'
        '<div style="text-align:center;">'
        '<div style="font-size:10px;color:#6e7681;margin-bottom:2px;">심각도</div>'
        f'<div style="font-size:16px;font-weight:600;color:{color};">{severity}</div>'
        '</div>'
        '<div style="text-align:center;">'
        '<div style="font-size:10px;color:#6e7681;margin-bottom:2px;">마지막 추론</div>'
        f'<div style="font-size:13px;font-family:monospace;color:#8b949e;">{ts_short}</div>'
        '</div>'
        '</div></div></div>'
    )


def _prob_bars_html(ir: dict, pred_class: str) -> str:
    """Render threat class probability bars with class-specific colors."""
    rows = []
    for cls_name, prob in sorted(ir.items(), key=lambda x: -x[1]):
        color    = THREAT_COLORS.get(cls_name, "#8b949e")
        is_pred  = cls_name == pred_class
        bar_col  = color if is_pred else "#21262d"
        name_col = color if is_pred else "#8b949e"
        val_col  = color if is_pred else "#484f58"
        weight   = "700" if is_pred else "400"
        marker   = " ◄" if is_pred else ""
        display  = cls_name.replace("_", " ").title()
        rows.append(
            f'<div style="margin-bottom:10px;">'
            f'<div style="display:flex;justify-content:space-between;margin-bottom:3px;">'
            f'<span style="font-size:12px;color:{name_col};font-weight:{weight};">{display}{marker}</span>'
            f'<span style="font-size:12px;font-family:monospace;color:{val_col};">{prob:.1%}</span>'
            '</div>'
            '<div style="height:7px;background:#21262d;border-radius:4px;overflow:hidden;">'
            f'<div style="height:100%;width:{prob * 100:.1f}%;background:{bar_col};border-radius:4px;"></div>'
            '</div></div>'
        )
    return "\n".join(rows)


def _section_label(text: str) -> str:
    return (
        f'<div style="font-size:10px;color:#8b949e;font-weight:700;'
        f'letter-spacing:1.5px;text-transform:uppercase;margin:0 0 10px 0;">'
        f'{text}</div>'
    )


# ── Session state init ────────────────────────────────────────────────────────

def _init_state() -> None:
    defaults: dict = {
        "sensor_latest":  {},
        "ai_latest":      {},
        "sensor_history": {},
        "schema_errors":  [],
        "msg_counts":     {"sensor": 0, "ai": 0, "error": 0},
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ── MQTT ──────────────────────────────────────────────────────────────────────

def _mqtt_connect(broker: str, port: int) -> None:
    s = _g_state()
    # 기존 연결 정리
    if s["client"] is not None:
        try:
            s["client"].loop_stop()
            s["client"].disconnect()
        except Exception:
            pass
    s["connected"].clear()

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        client = mqtt.Client()

    def on_connect(c, *_args):
        for t in SENSOR_TOPICS + [AI_TOPIC]:
            c.subscribe(t)
        s["connected"].set()

    def on_disconnect(*_args):
        s["connected"].clear()

    def on_message(_c, _userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8", errors="ignore"))
            s["queue"].put_nowait({"topic": msg.topic, "data": data})
        except Exception:
            pass

    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect(broker, port)
    client.loop_start()
    s["client"] = client


def _mqtt_disconnect() -> None:
    s = _g_state()
    if s["client"] is not None:
        try:
            s["client"].loop_stop()
            s["client"].disconnect()
        except Exception:
            pass
        s["client"] = None
    s["connected"].clear()


def _drain_queue(active_types: list[str]) -> None:
    q = _g_state()["queue"]
    processed = 0
    while not q.empty() and processed < 50:
        item  = q.get_nowait()
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
                ts   = datetime.now()
                hist = st.session_state.sensor_history.setdefault(sensor_type, [])
                hist.append((ts, float(value)))
                if len(hist) > 60:
                    hist.pop(0)


# ── Main UI ───────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="DTFP Demo",
        page_icon="🛡️",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _init_state()
    st.markdown(_CSS, unsafe_allow_html=True)

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            '<div style="padding:8px 0 16px 0;">'
            '<div style="font-size:22px;font-weight:800;color:#e6edf3;letter-spacing:-0.5px;">🛡️ DTFP</div>'
            '<div style="font-size:11px;color:#8b949e;margin-top:2px;">AI 기반 배전반 예측 유지보수</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        st.divider()

        st.markdown("**📡 MQTT 연결**")
        broker = st.text_input("Broker", value="localhost",
                                label_visibility="collapsed", placeholder="Broker address")
        port = st.number_input("Port", value=1883, step=1, label_visibility="collapsed")

        col1, col2 = st.columns(2)
        with col1:
            connect_btn = st.button("🔌 연결", use_container_width=True, type="primary")
        with col2:
            disconnect_btn = st.button("⏹ 해제", use_container_width=True)

        if connect_btn:
            try:
                _mqtt_connect(broker, port)
                st.success(f"연결 요청: {broker}:{port}")
            except Exception as e:
                st.error(f"연결 실패: {e}")

        if disconnect_btn:
            _mqtt_disconnect()

        st.divider()
        st.markdown("**🧩 프로젝트 프로필**")
        profile_name = st.selectbox("profile", list(PROJECT_SENSORS.keys()),
                                     label_visibility="collapsed")
        profile      = PROJECT_SENSORS[profile_name]
        active_types = profile["types"]

        st.divider()
        st.markdown("**📊 파이프라인 통계**")
        mc = st.session_state.msg_counts
        c1, c2, c3 = st.columns(3)
        c1.metric("센서", mc["sensor"])
        c2.metric("AI", mc["ai"])
        c3.metric("오류", mc["error"])

        if st.button("🔄 초기화", use_container_width=True):
            st.session_state.sensor_latest  = {}
            st.session_state.ai_latest      = {}
            st.session_state.sensor_history = {}
            st.session_state.msg_counts     = {"sensor": 0, "ai": 0, "error": 0}

    # ── Main area ─────────────────────────────────────────────────────────────
    _drain_queue(active_types)

    # Connection status bar
    if _g_state()["connected"].is_set():
        st.markdown(
            '<div style="background:#1a3a1a;border:1px solid #3fb95055;border-radius:8px;'
            'padding:9px 16px;color:#3fb950;font-size:13px;font-weight:600;margin-bottom:10px;">'
            f'🟢 MQTT 연결됨 &nbsp;|&nbsp; 토픽 {len(SENSOR_TOPICS + [AI_TOPIC])}개 구독 중'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="background:#2d1b1b;border:1px solid #f8514955;border-radius:8px;'
            'padding:9px 16px;color:#f85149;font-size:13px;font-weight:600;margin-bottom:10px;">'
            '🔴 오프라인 — 사이드바에서 브로커를 연결하세요'
            '</div>',
            unsafe_allow_html=True,
        )

    # ── AI Result Banner ──────────────────────────────────────────────────────
    ai = st.session_state.ai_latest
    pred_class = ""
    if ai:
        ir_data    = ai.get("inference_result", {})
        pred_class = ir_data.get("predicted_class", "unknown")
        warning_level = ir_data.get("warning_level", "Normal")
        _wl_to_sev = {"Normal": "NORMAL", "Caution": "CAUTION", "Warning": "WARNING", "Danger": "CRITICAL"}
        severity   = _wl_to_sev.get(warning_level, "NORMAL")
        state_str  = f"{pred_class}_{severity}"
        timestamp  = ai.get("timestamp", "—")

        st.markdown(_ai_banner(state_str, timestamp, ai), unsafe_allow_html=True)

    # Two-column layout: sensors left, probabilities right
    left_col, right_col = st.columns([3, 2])

    with left_col:
        # ── Sensor Metrics ────────────────────────────────────────────────────
        st.markdown(_section_label("실시간 센서 데이터"), unsafe_allow_html=True)
        sensor_cols = st.columns(len(active_types))
        for i, sensor_type in enumerate(active_types):
            label = profile["labels"][sensor_type]
            icon  = profile["icons"][sensor_type]
            unit  = profile["units"][sensor_type]
            with sensor_cols[i]:
                data = st.session_state.sensor_latest.get(sensor_type)
                if data:
                    val      = data.get("value", 0)
                    ts_short = data.get("ts", "")[-8:]
                    st.markdown(
                        _sensor_card(icon, label, val, unit, sensor_type, ts_short),
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        _sensor_card(icon, label, None, unit, sensor_type),
                        unsafe_allow_html=True,
                    )

        # ── Sensor History Charts ─────────────────────────────────────────────
        has_history = any(
            len(st.session_state.sensor_history.get(t, [])) > 3
            for t in active_types
        )
        if has_history:
            st.markdown(
                '<div style="margin-top:16px;"></div>', unsafe_allow_html=True
            )
            st.markdown(_section_label("추이 (최근 60s)"), unsafe_allow_html=True)
            chart_cols = st.columns(len(active_types))
            for i, sensor_type in enumerate(active_types):
                hist = st.session_state.sensor_history.get(sensor_type, [])
                with chart_cols[i]:
                    if len(hist) > 3:
                        import pandas as pd
                        df = pd.DataFrame(
                            {"value": [v for _, v in hist[-60:]]},
                        )
                        st.line_chart(df, height=72, use_container_width=True)
                    else:
                        st.markdown(
                            '<div style="height:72px;background:#161b22;border-radius:6px;'
                            'display:flex;align-items:center;justify-content:center;">'
                            '<span style="font-size:10px;color:#484f58;">데이터 수집중</span>'
                            '</div>',
                            unsafe_allow_html=True,
                        )

    with right_col:
        # ── Probability Bars ──────────────────────────────────────────────────
        if ai:
            ir_full = ai.get("inference_result", {})
            probs   = ir_full.get("probabilities", {})
            if probs:
                st.markdown(_section_label("위협 분류 확률"), unsafe_allow_html=True)
                st.markdown(
                    '<div style="background:#161b22;border:1px solid #21262d;'
                    'border-radius:10px;padding:16px 18px;">'
                    + _prob_bars_html(probs, pred_class)
                    + '</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                '<div style="background:#161b22;border:1px solid #21262d;'
                'border-radius:10px;padding:24px 18px;text-align:center;">'
                '<div style="font-size:32px;margin-bottom:8px;">🎯</div>'
                '<div style="font-size:12px;color:#484f58;">AI 추론 결과 대기중</div>'
                '</div>',
                unsafe_allow_html=True,
            )

    # ── Auto-refresh ──────────────────────────────────────────────────────────
    # mqtt_client 객체가 존재하면 항상 rerun (connected 플래그는 백그라운드 스레드 이슈)
    s = _g_state()
    if s["client"] is not None or not s["queue"].empty():
        time.sleep(0.5)
        st.rerun()


if __name__ == "__main__":
    main()
