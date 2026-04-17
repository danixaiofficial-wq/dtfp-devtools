# AGENTS.md — dtfp-devtools

AI 에이전트를 위한 코드베이스 가이드.

## 역할

DTFP 파이프라인 통합 검증 + 클라이언트 데모 도구.  
MqttDataGen과 DTFP v2 양쪽 모두를 테스트하며, 어느 쪽 코드도 직접 수정하지 않는다.

## 파일 구조

```
dtfp-devtools/
├── monitor/
│   └── monitor.py       # CLI: MQTT 토픽 실시간 감청 + 스키마 자동 검증
├── dashboard/
│   └── dashboard.py     # Streamlit: 풀파이프라인 데모 대시보드
├── tests/
│   ├── test_schema.py   # pytest: 페이로드 포맷 자동 검증
│   └── scenarios/       # 재현 가능한 시나리오 JSON
│       ├── normal.json
│       ├── fire_overload.json
│       └── breakdown.json
├── docs/
│   └── WORKFLOW.md      # 모듈 관리 전략 + 학습-검증 워크플로우
└── pyproject.toml       # uv 의존성
```

## 실행 방법

```bash
# 의존성 설치
uv sync

# 1. MQTT 실시간 감청 (가장 먼저 실행)
uv run python monitor/monitor.py --broker broker.emqx.io
uv run python monitor/monitor.py --profile project1 --verbose

# 2. 클라이언트 데모 대시보드
uv run streamlit run dashboard/dashboard.py

# 3. 스키마 자동 검증 (배포 전 필수)
uv run pytest tests/test_schema.py -v

# 4. 전체 테스트
uv run pytest tests/ -v
```

## 스키마 기준

인터페이스 문서 v1.9 (2026-03-23) 기준.  
변경 시 → MqttDataGen/docs/interface/Sensor_Schema.md 먼저 수정 후 이 레포의 테스트 업데이트.

## 시나리오 파일 형식

```json
{
  "scenario": "name",
  "profile": "project1 | project2",
  "description": "설명",
  "params": { "load_amp": ..., "threat": ..., "intensity": ... },
  "sensor_packets": { "type": { ...payload... } },
  "expected_ai": { "state_prefix": "...", "min_threat_prob": 0.5 }
}
```

## 의존 레포

| 레포 | 역할 | 관계 |
|---|---|---|
| MqttDataGen | MQTT 발행 | 스키마 Source of Truth |
| DTFP (Release_v2.0.2/dtfp) | AI 추론 | MqttDataGen 스키마 따름 |
| dtfp-devtools (이 레포) | 검증/데모 | 위 두 레포를 테스트만 함 |
