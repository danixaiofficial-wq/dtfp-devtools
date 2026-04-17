# dtfp-devtools

DTFP 파이프라인 통합 검증 및 클라이언트 데모 도구.

## 빠른 시작

```bash
uv sync

# 파이프라인 감청 (터미널 1)
uv run python monitor/monitor.py --broker broker.emqx.io

# 데모 대시보드 (터미널 2)
uv run streamlit run dashboard/dashboard.py

# 배포 전 스키마 검증
uv run pytest tests/ -v
```

## 구성 요소

| 도구 | 용도 |
|---|---|
| `monitor/monitor.py` | MQTT 실시간 감청 + 스키마 자동 검증 |
| `dashboard/dashboard.py` | 클라이언트 시연용 풀파이프라인 대시보드 |
| `tests/test_schema.py` | 인터페이스 스펙 v1.9 기준 자동 검증 |
| `tests/scenarios/*.json` | 재현 가능한 시나리오 케이스 |

## 관련 레포

- **MqttDataGen** — ESP32 시뮬레이터 / MQTT 스키마 소스
- **DTFP** — AI 추론 모듈

자세한 워크플로우: [docs/WORKFLOW.md](docs/WORKFLOW.md)
