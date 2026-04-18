#!/usr/bin/env bash
# ============================================================
# dev.sh — DTFP 개발환경 원클릭 실행
#
# 실행 순서:
#   1. Mosquitto 로컬 브로커 (localhost:1883)
#   2. Streamlit 대시보드       (localhost:8501)
#   3. Streamlit 데이터 제너레이터 (localhost:8502)
#   4. DTFP 메인 앱
#
# 종료: Ctrl+C → 모든 프로세스 자동 정리
# ============================================================

set -e

DEVTOOLS="$(cd "$(dirname "$0")" && pwd)"   # dtfp-devtools/
DTFP_DIR="$(cd "$DEVTOOLS/.." && pwd)"      # DTFP/
MQTTGEN="$DTFP_DIR/MqttDataGen"
APP_DIR="$DTFP_DIR/Release_v2.0.2/dtfp"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${GREEN}[✔]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
err()     { echo -e "${RED}[✘]${NC} $1"; }
section() { echo -e "\n${CYAN}━━ $1 ━━${NC}"; }

PIDS=()

cleanup() {
    echo ""
    warn "종료 중... 모든 프로세스 정리"
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null && echo "  killed: $pid"
    done
    exit 0
}
trap cleanup SIGINT SIGTERM

# ── 1. Mosquitto 브로커 ───────────────────────────────────────
section "MQTT 브로커"
if ! command -v mosquitto &>/dev/null; then
    err "mosquitto 없음. 설치: brew install mosquitto"
    exit 1
fi

mosquitto -c "$DEVTOOLS/dev_mosquitto.conf" &
PIDS+=($!)
info "Mosquitto 시작 (localhost:1883) pid=${PIDS[-1]}"
sleep 1

# ── 2. 대시보드 ───────────────────────────────────────────────
section "대시보드 (8501)"
cd "$DEVTOOLS"
uv run streamlit run dashboard/dashboard.py \
    --server.port=8501 \
    --server.headless=true \
    --browser.gatherUsageStats=false \
    --global.developmentMode=false \
    &> /tmp/dtfp_dashboard.log &
PIDS+=($!)
info "대시보드 시작 pid=${PIDS[-1]} → http://localhost:8501"

# ── 3. 데이터 제너레이터 ──────────────────────────────────────
section "데이터 제너레이터 (8502)"
cd "$MQTTGEN"
uv run streamlit run Generater.py \
    --server.port=8502 \
    --server.headless=false \
    --browser.gatherUsageStats=false \
    &> /tmp/dtfp_generator.log &
PIDS+=($!)
info "제너레이터 시작 pid=${PIDS[-1]} → http://localhost:8502"

sleep 3

# 브라우저 자동 오픈
open "http://localhost:8501" 2>/dev/null || true
open "http://localhost:8502" 2>/dev/null || true

# ── 4. DTFP 메인 앱 ───────────────────────────────────────────
section "DTFP 메인 앱"
cd "$APP_DIR"
info "앱 시작 (로그는 터미널에 출력)"
echo ""
echo -e "${YELLOW}브로커: localhost:1883${NC}"
echo -e "${YELLOW}대시보드: http://localhost:8501${NC}"
echo -e "${YELLOW}제너레이터: http://localhost:8502${NC}"
echo ""

# 로그 레벨 DEBUG로 설정해서 MQTT 메시지 실시간 출력
DTFP_LOG_LEVEL=DEBUG uv run dtfp-app 2>&1

# 앱 종료 시 cleanup 호출
cleanup
