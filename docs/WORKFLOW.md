# DTFP 시스템 관리 전략 & 워크플로우

## 레포지토리 구조

```
MqttDataGen/          ← ESP32 시뮬레이터 (데이터 소스)
DTFP/
  Release_v2.0.2/
    dtfp/             ← AI 추론 모듈
dtfp-devtools/        ← 통합 검증 + 데모 (이 레포)
```

### 역할 분리 원칙
- **MqttDataGen**: MQTT 스키마의 Source of Truth. 프론트엔드와 직접 협의한 인터페이스 기준.
- **DTFP**: MqttDataGen 스키마를 따름. AI 모델, 추론 엔진, GUI.
- **dtfp-devtools**: 위 두 레포를 테스트하는 독립 도구. 어느 쪽도 수정하지 않음.

---

## 일상 개발 워크플로우

### 센서 스키마 변경 시

```
1. MqttDataGen/docs/interface/Sensor_Schema.md 수정
2. MqttDataGen/Generater.py 수정 (SensorPlugin 등록)
3. DTFP/src/dtfp_v2/core/config.py 수정 (PROJECT1/2 features)
4. DTFP/src/dtfp_v2/inference/mqtt_client.py 수정 (_FEATURE_TOPIC_MAP)
5. DTFP/src/dtfp_v2/data/generator.py 수정 (FEATURE_TO_STATE_KEY)
6. dtfp-devtools/tests/scenarios/*.json 업데이트
7. uv run pytest tests/test_schema.py -v  ← 자동 검증
```

### 새 시나리오 추가 시

```
1. tests/scenarios/{name}.json 작성
2. uv run pytest tests/test_schema.py -v 로 포맷 검증
3. monitor.py 로 실제 MQTT 흐름 육안 확인
```

---

## 모델 학습 → 배포 워크플로우

```
Phase 1: 데이터 생성
  uv run dtfp-cli generate --profile project1 --preset full
  uv run dtfp-cli generate --profile project2 --preset full

Phase 2: 학습
  uv run dtfp-cli train --profile project1 --epochs 100
  uv run dtfp-cli train --profile project2 --epochs 100

Phase 3: 검증 (학습 직후 필수)
  ① 오프라인 지표
      uv run dtfp-cli evaluate --profile project1
      uv run dtfp-cli evaluate --profile project2
      → Confusion matrix + per-class accuracy 확인
      → 목표: Normal 95%+, 위협 클래스 80%+

  ② 파이프라인 시뮬레이션 검증
      터미널 A: uv run python monitor/monitor.py
      터미널 B: uv run dtfp-app  (또는 uv run dtfp-cli simulate)
      MqttDataGen에서 각 위협 시나리오 발행 후 AI 결과 확인

  ③ 스키마 자동 테스트
      uv run pytest tests/ -v
      → 전체 PASS 확인 후에만 배포 진행

Phase 4: 배포
  uv run dtfp-cli export --profile project1
  uv run dtfp-cli export --profile project2
  → PyInstaller 빌드: uv run pyinstaller dtfp.spec
```

### 배포 전 체크리스트 (시연 실패 방지)

```
□ uv run pytest tests/test_schema.py -v → 전체 PASS
□ monitor.py 실행 후 Schema Error 0개 확인
□ dashboard.py 에서 Project 1 시나리오 시연 확인
□ dashboard.py 에서 Project 2 시나리오 시연 확인
□ breakdown 시나리오: AI 판정 Danger 확인
□ normal 시나리오: AI 판정 Normal 확인
□ 인터페이스 문서 버전 vs Sensor_Schema.md 버전 일치 확인
```

---

## 두 프로젝트 완전 분리 기준

### Project 1 — 전기 구조 모니터링

| 항목 | 내용 |
|:---|:---|
| 대상 장비 | 고압반, 저압반, MCC, 분전반 |
| 센서 | temperature, humidity, arc, vibration |
| 주요 위협 | insulation_aging, condensation, breakdown |
| 전원 | 110V/380V/220V, CT 2차측 5A |
| 특징 | 전기적 절연 상태, 수분 침투, 구조적 고장 |

### Project 2 — 화재/가스 감지 (포유파워)

| 항목 | 내용 |
|:---|:---|
| 대상 장비 | 포유파워 연계 가스/화재 감지 모듈 |
| 센서 | temperature, vibration, co, tobacco |
| 주요 위협 | fire_overload, breakdown (연소 동반) |
| 특징 | CO/연기 농도 기반 화재 조기 감지 |
| arc 없음 | 전기 아크 감지 대신 가스 농도 중심 |
| humidity 없음 | 결로 대신 연소 부산물 감지 |

### 공통
- temperature, vibration: 두 프로젝트 모두 사용
- 동일 MQTT 브로커, 동일 토픽 구조
- 동일 AI 모델 아키텍처, 별도 학습된 가중치

---

## 물리 엔진 이슈 트래커

| 우선순위 | 항목 | 파일 | 상태 |
|:---|:---|:---|:---|
| 🔴 긴급 | condensation 시나리오 온도 냉각 로직 제거 | physics.py, Generater.py | ✅ 완료 (2026-04-18) |
| 🔴 긴급 | CO 발생 온도 임계 75°C → 85°C (학습 시퀀스 절충) | physics.py, Generater.py | ✅ 완료 (2026-04-18) |
| 🔴 긴급 | 진동 기본 주파수 60Hz → 50Hz (한국 표준) | physics.py, Generater.py | ✅ 완료 (2026-04-18) |
| 🟠 높음 | I²R 발열 계수 물리 기반 재계산 | physics.py, Generater.py | 미수정 |
| 🟠 높음 | 온도 시간상수 inertia 0.05 유지 (50-step 학습 절충) | physics.py, Generater.py | 보류 (의도적) |
| 🟠 높음 | 아크 발생 확률 25% → 10% per step | physics.py, Generater.py | ✅ 완료 (2026-04-18) |
| 🟠 높음 | CO 아크 방출 +50 → +100 PPM | physics.py, Generater.py | ✅ 완료 (2026-04-18) |
| 🟠 높음 | CO 감쇠 속도 0.05 → 0.02 (밀폐 공간) | physics.py, Generater.py | ✅ 완료 (2026-04-18) |
| 🟠 높음 | CO 상한 500 PPM 캡 추가 | physics.py, Generater.py | ✅ 완료 (2026-04-18) |
| 🟡 중간 | 연기/tobacco 임계 CO 100→150, 온도 85→95°C | physics.py, Generater.py | ✅ 완료 (2026-04-18) |

---

## 브랜치 전략 (권장)

```
main          ← 배포 가능한 안정 버전
develop       ← 통합 개발
feature/*     ← 기능 개발 (예: feature/physics-fix)
hotfix/*      ← 긴급 수정
```

### 커밋 컨벤션

```
feat:     새 기능
fix:      버그 수정
physics:  물리 엔진 수정
schema:   MQTT 스키마/인터페이스 변경
docs:     문서 수정
test:     테스트 추가/수정
```

---

## 실장비(ESP32) 연결 전환 체크리스트

```
□ ESP32 MQTT 토픽: sensors/{deviceXX}/data 형식 확인
□ 페이로드 필드: sb_id, device_id, type, value, unit, ts 모두 포함
□ value 소수점 1자리 이하 확인
□ ts: ISO 8601 UTC (예: "2026-04-17T10:00:00Z") 확인
□ monitor.py 로 실장비 데이터 수신 및 Schema Error 0개 확인
□ MqttDataGen은 오프라인 유지 (중복 발행 방지)
□ dtfp-app 또는 dtfp-cli 로 DTFP v2 기동
□ dashboard.py 에서 실데이터 시각화 확인
```
