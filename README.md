# 🏠 AI Home Layout Debugger

> **AI 기반 1인 주택 가구 배치 검증 & 해결 지원 에이전트**
> 기존 인테리어 앱이 배치를 "만들어준다"면, 우리는 당신의 배치를 **디버깅**한다.

가구 배치의 Grammarly. 사용자가 직접 배치한 1인 주택(거실·침실·서재) 레이아웃을 AI가 검사하고 **문제의 원인 · 생활 영향 · 해결 방법 · 유사 사례**까지 제시합니다.

```
Human Layout → AI Critic → Human Revision
```

## 왜 이게 없는가 (시장 조사)

오늘의집 3D, 아키스케치, Planner 5D, Coohom 등 기존 도구는 전부 **생성(Generation) 패러다임** — "AI가 예쁜 배치를 만들어줄게"입니다. 반면:

- ❌ 사용자 배치를 **수치 근거로 검사**해 PASS/FAIL 오류 목록을 주는 도구 없음
- ❌ "옷장이 현관문 개폐 반경을 550mm 침범" 같은 **정량 진단** 없음
- ❌ "소파를 왼쪽 400mm만 옮기면 해소 (부작용 없음, 재검증 완료)" 같은 **검증된 최소 수정** 없음
- ❌ 검출→수정→재검증을 자율 반복하는 **Agent 루프** 없음

좁은 원룸일수록 "예쁘게"보다 **"충돌 없이 살 수 있는가"**가 문제인데, 이 검증 시장이 비어 있습니다.

## 핵심 기능

| | |
|---|---|
| **Detect** | 결정론적 기하 엔진이 가구 겹침 / 문 개폐 구역 침범 / 창문 앞 확보 구역 / 동선 폭 / 가구 사용 공간(책상 750mm 등) / 벽 관통 검사 |
| **Visualize** | Three.js 3D — 위반 하이라이트, 펄스 마커, 반투명 keep-clear 구역, 동선 튜브 |
| **Recommend** | 해결안 후보를 기하적으로 생성 → **전체 재검증 통과분만** A/B안 제시 + 고스트 미리보기 |
| **Explain + Learn** | LLM이 인체공학 규칙 + 배치 사례 KB 기반으로 원인/영향/추천 근거를 생활 언어로 설명 |
| **Agent** | 전체 자동 수정 — 위반 4건을 ~3초에 자율 해결 (진동 방지 가드 포함) |
| **Copilot** | 자연어 배치 명령 ("책상을 창가로 옮겨줘") |
| **도우미 챗봇** | 인테리어 초보용 Q&A (현재 배치 상태 인지) |
| **편집기** | 가구 드래그(바닥 평면 고정), 동선 경유점 편집, 팔레트 추가/삭제, 속성 편집, Undo/Redo, 저장 |

## 아키텍처 — 역할 분리 원칙

**모든 수치와 판정은 결정론적 엔진에서, LLM은 설명만.**

```
studio.json (배치 데이터)
    ↓
Geometry + Rule Engine ── 정확한 검출 (LLM 개입 0%)
    ↓
Resolver ── 후보 생성 → 전체 재검증 → 통과분만 제시
    ↓
LLM ── 검증된 사실 + 규칙/사례 KB → 자연어 설명 (수치 생성 금지)
    ↓
사용자 최종 판단 → 적용/실행취소
```

## 실행

```bash
pip install -r requirements.txt
python -m uvicorn backend.main:app --port 8001
# → http://localhost:8001
```

**⚡ AI 속도:** `.env.example`을 `.env`로 복사하고 무료 [Gemini API 키](https://aistudio.google.com/apikey)를 넣으면 AI 응답이 1~4초. 키가 없으면 Claude Code CLI로 폴백(느림), 그것도 없으면 템플릿 폴백.

## 테스트

### 표시 언어

화면의 언어 선택에서 한국어(기본값)와 English를 전환할 수 있습니다. 선택은 브라우저에 보관됩니다.
API는 `?lang=ko` 또는 `?lang=en`으로 위반 설명·해결안·AI 응답의 언어를 선택합니다.
언어는 표시만 바꾸며, ID·좌표·측정값·판정·점수는 동일합니다. 가구의 저장 이름은 한국어를 유지하고
3D 라벨에서는 괄호 설명을 생략합니다. 사용자 입력 이름이나 이전 대화 기록은 자동 번역하지 않습니다.
AI 응답은 HTML로 실행하지 않고 텍스트로 표시합니다.

### 회귀 테스트 실행

프로젝트 루트에서 실행합니다. WSL에서는 기존 가상환경을 먼저 활성화합니다.

```bash
source ~/.venvs/wanted-ai-hackathon/bin/activate  # WSL에서 실행할 때
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

WSL 공유 드라이브에서 pytest 캐시 권한 경고가 발생하면 `python -m pytest -q -p no:cacheprovider`로 실행합니다.
실제 HTTP 검증만 실행하려면 `python -m pytest -q -s -p no:cacheprovider tests/test_live_api.py`를 사용합니다.
이 테스트는 충돌하지 않는 로컬 포트에 Uvicorn을 시작하여 API를 확인하고 종료합니다.

개발 의존성은 `pytest`와 FastAPI `TestClient`에 필요한 `httpx`입니다.
테스트는 LLM을 호출하지 않으며 API 작업 상태와 데이터 경로를 격리하여 원본 데모를 변경하지 않습니다.

현재 [기본 데모](backend/data/house2.json)의 기준선은 **6건 (HIGH 3건, MEDIUM 3건), 34점**입니다.

| 코드 | 대상 a | 대상 b |
|---|---|---|
| HARD_CLASH | sofa | table |
| HARD_CLASH | tv_stand | wall_b |
| ZONE_INTRUSION | bed | bedroom_window |
| ZONE_INTRUSION | wardrobe | bedroom_door_swing |
| MAINTENANCE_SPACE | desk | bookshelf |
| OUT_OF_ROOM | tv_stand | living |

[회귀 테스트](tests/test_baseline.py)는 코드·대상 쌍·측정값, 각 위반의 1순위 해결안 적용 후 대상 위반 해소와 새 위반 없음,
`/api/autofix` 후 **0건·100점**, 반복 실행과 Undo/Redo를 검증합니다.
규칙이나 의도된 위반이 바뀌면 기준선과 테스트를 함께 갱신합니다.

## 검사 규칙 (기본값)

| 규칙 | 기준 | 근거 |
|---|---|---|
| 주 동선 폭 | 600mm (권장 900) | 1인 통행 + 물건 운반 |
| 문 개폐 구역 | 침범 금지 | 출입/피난/가구 반입 |
| 창문 앞 확보 | 침범 금지 (~500mm) | 채광/환기/결로/피난 |
| 책상 사용 공간 | 750mm | 의자 빼고 앉는 동작 |
| 옷장 개폐 공간 | 600mm | 여닫이 문짝 폭 |
| 가구 겹침/벽 관통 | 금지 | 물리적 배치 가능성 |

## 프로젝트 구조

```
backend/
├── main.py          # FastAPI + Undo/Redo + Auto-Fix Agent
├── models.py        # Scene/가구/구역/동선 데이터 모델
├── geometry.py      # 기하 계산 (선분-박스, 박스-박스 거리)
├── detector.py      # Rule Engine (ZONE_INTRUSION 등 주거 특화)
├── resolver.py      # 해결안 생성 + 재검증 (바닥 평면 제약)
├── llm.py           # LLM 프로바이더 (Gemini/Groq/OpenAI/Claude CLI)
├── commands.py      # 자연어 → 배치 작업(ops)
├── chat.py          # 배치 도우미 챗봇
└── data/
    ├── house.json      # 1인 주택 씬 — 거실·침실·서재, 내벽/문/창 (의도적 위반 5건)
    ├── studio.json     # 원룸 씬 (의도적 위반 4건)
    └── knowledge.json  # 인체공학 규칙 + 배치 사례 KB
frontend/
└── index.html       # Three.js 뷰어 + 전체 UI
```

## 계보

같은 아키텍처의 조선 도메인 버전에서 출발: [K-Shipbuilding-AI-Hackathon](https://github.com/GeunheePARKKK/K-Shipbuilding-AI-Hackathon) (AI Ship Design Debugger — 기관실 배관/장비 간섭 검증). 도메인 독립적 코어(기하/규칙/해결안/Agent)를 재사용하고 규칙·데이터·프롬프트만 교체해 이식.
