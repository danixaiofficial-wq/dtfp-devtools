# DTFP 검증 가이드

인터페이스 스펙 v1.9 / 물리 엔진 수정 2026-04-18 기준

---

## 실행 순서 (매번 동일)

```bash
# 터미널 1 — DataGen
cd MqttDataGen
uv run streamlit run Generater.py           # http://localhost:8501

# 터미널 2 — DTFP AI 모듈
cd DTFP/Release_v2.0.2/dtfp
uv run dtfp-app
# → Profile 선택 → Realtime → broker.emqx.io:1883 → Start

# 터미널 3 — Demo Dashboard
cd DTFP/dtfp-devtools
uv run streamlit run dashboard/dashboard.py  # http://localhost:8502
# → 사이드바 broker.emqx.io → 🔌 연결
```

---

## Phase 1 — 연결 & 스키마 기본 검증

| 확인 항목 | 기대 결과 | 실패 시 |
|---|---|---|
| Dashboard 상태 바 | 🟢 초록 "MQTT 연결됨" | mqtt_client.py 토픽 확인 |
| 센서 카드 값 수신 | 4개 카드 모두 수신 | DataGen 실행 여부 확인 |
| AI 배너 등장 | 버퍼 50개 채운 뒤 표시 | DTFP app 상태 확인 |
| 페이로드 소수점 | 값이 X.X 형식 | Generater.py round() 확인 |

---

## Phase 2 — 시나리오별 검증

### 시나리오 1 — Normal (Project 1)
`Threat = Normal, Intensity = 0.0, Load = 20A`

| 센서 | 기대 범위 | 카드 색상 | 핵심 체크 |
|---|---|---|---|
| 온도 | 25~27°C | 파란색 | — |
| 습도 | 43~47% | 파란색 | — |
| 아크 | 0.0 | 파란색 | — |
| **진동** | **~50 Hz** | 파란색 | ⚠️ 물리 엔진 수정 확인 (구 60Hz) |

**Dashboard 기대:** 🟢 AI 배너 `NORMAL`, 확률 바 normal ◄ 초록색

---

### 시나리오 2 — condensation (Project 1)
`Threat = condensation, Intensity = 0.8, Load = 30A`

| 센서 | 기대 결과 | 핵심 체크 |
|---|---|---|
| 온도 | **유지 또는 상승** | ⚠️ 냉각 제거 검증 — 절대 내려가면 안 됨 |
| 습도 | 75~95% | 노란/빨간 카드 |
| 진동 | 54~57 Hz | 릴레이 채터 반영 |
| CO | 소량 상승 (부식 마이크로 아크) | — |

**Dashboard 기대:** 🟡 또는 🟠 배너

---

### 시나리오 3 — insulation_aging (Project 1)
`Threat = insulation_aging, Intensity = 0.9, Load = 80A`

| 확인 항목 | 기대 결과 | 핵심 체크 |
|---|---|---|
| 아크 발생 빈도 | **간헐적 (~10%)** | ⚠️ 구 25%에서 10%로 수정 확인, 30초 이상 관찰 |
| 아크 발생 시 온도 | 급등 방향 (+45°C) | — |
| 아크 미발생 구간 | 온도 완만 상승 | — |
| AI 판정 | insulation_aging 확률 ↑ | — |

> 30초 이상 관찰 필요. 아크가 매 step 발생하면 물리 엔진 확인.

---

### 시나리오 4 — fire_overload (Project 2)
Dashboard 프로필: `Project 2 — 화재/가스`
`Threat = fire_overload, Intensity = 0.9, Load = 100A`

| 센서 | 기대 범위 | 카드 색상 | 핵심 체크 |
|---|---|---|---|
| 온도 | 75°C 이상 | 🔴 빨간 | — |
| CO | 85°C 초과 시 서서히 상승 | 노란→빨간 | ⚠️ 임계 85°C (구 75°C) 확인 |
| tobacco | CO>150 + temp>95 진입 후 등장 | 노란 | ⚠️ 임계 순서 확인 |
| 진동 | ~50 Hz | 파란 | fire_overload는 진동 무영향 |

**Dashboard 기대:** 🔴 `FIRE OVERLOAD — CRITICAL` 빨간 배너

---

### 시나리오 5 — breakdown (Project 2)
`Threat = breakdown, Intensity = 1.0, Load = 80A`

| 센서 | 기대 결과 | 핵심 체크 |
|---|---|---|
| CO | 급등 후 **500 PPM 이내** 수렴 | ⚠️ CO 상한 캡 검증 |
| tobacco | CO>150 + temp>95 후 상승 | ⚠️ 임계 순서 |
| 진동 | 70~75 Hz | 빨간 카드 |
| AI | breakdown ◄ 보라색, 확률 > 0.7 | — |

**Dashboard 기대:** 🔴 `BREAKDOWN — CRITICAL` 빨간 배너, breakdown 바 보라색

---

## Phase 3 — UI 동작 체크리스트

```
□ 센서 카드: 온도 75°C 이상 → 카드 테두리 + 값 빨간색
□ 센서 카드: 온도 50~74°C → 노란색
□ AI 배너: Normal → 초록 그라디언트
□ AI 배너: Warning/Danger → 빨간 그라디언트
□ 확률 바: 예측 클래스만 고유 색상, 나머지 회색
□ 추이 차트: 30s 이상 실행 후 라인차트 등장
□ 사이드바 통계: 센서/AI 카운터 초당 증가
□ DataGen 상태 배너: 위험도별 초록/노란/빨간 변경
```

---

## Phase 4 — 자동 스키마 검증

```bash
cd DTFP/dtfp-devtools
uv run pytest tests/ -v
# 전체 PASS 확인 후 배포 진행
```

---

## 수정 완료 항목 (2026-04-18)

| 항목 | 이전 | 이후 |
|---|---|---|
| 진동 기준 | 60 Hz | 50 Hz |
| CO 발생 임계 | 75°C | 85°C |
| CO 아크 방출 | +50 PPM | +100 PPM |
| CO 감쇠 | 0.05 | 0.02 |
| CO 상한 | 없음 | 500 PPM |
| 아크 확률 | 25% | 10% |
| tobacco 임계 | CO>100 & temp>85 | CO>150 & temp>95 |
| condensation 냉각 | 존재 | 제거 |
| normal.json 진동 | 60.1 Hz | 50.1 Hz |

---

## 예상 소요 시간

| Phase | 시간 |
|---|---|
| Phase 0 실행 준비 | ~5분 |
| Phase 1 연결 확인 | ~5분 |
| Phase 2 시나리오 5개 | ~20분 |
| Phase 3 UI 체크 | ~5분 |
| Phase 4 pytest | ~2분 |
| **합계** | **~35분** |
