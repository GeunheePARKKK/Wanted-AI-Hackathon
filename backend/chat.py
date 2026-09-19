"""Help-desk chatbot: answers questions about equipment, layout rules and
how to use this tool. Read-only — it never modifies the design."""
from __future__ import annotations

import json

from backend.commands import _brief
from backend.detector import inspect_scene
from backend.llm import _load_knowledge, llm_text
from backend.models import Scene
from backend.i18n import language_instruction, tr

PROMPT = """당신은 'AI Home Layout Debugger'에 내장된 1인 주택 인테리어 도우미 챗봇입니다.
인테리어가 처음인 사람도 이해할 수 있게 쉬운 말로, 간결하게(2~5문장, 필요하면 짧은 목록) 선택된 언어로 답하세요.
배치를 직접 수정할 수는 없습니다. 수정 요청을 받으면 상단 'AI Copilot' 입력창이나 편집 도구 사용법을 안내하세요.

[이 도구 사용법]
- 왼쪽 패널: 가구 추가(종류 선택 후 +가구 추가), 선택 항목 삭제, Properties에서 ID/이름/크기 편집
- 가운데 3D 화면: 클릭=선택(이동 기즈모 표시), 드래그=회전, 휠=줌
- 오른쪽 패널: AI Copilot(자연어로 배치 명령), 배치 검사 실행, 전체 자동 수정(Agent), 오류 카드 클릭=해결안 보기/AI 분석
- 헤더: ↶↷ 실행취소/재실행(Ctrl+Z/Y), 💾 저장, ↩ 저장본 복원

[가구·요소 역할]
- bed(침대), wardrobe(옷장), desk(책상), sofa(소파), fridge(냉장고), bookshelf(책장), tv_stand(TV장), washing_machine(세탁기), table(테이블)
- rooms(방): 거실·침실·서재 같은 방 영역. 가구는 반드시 하나의 방 안에 완전히 들어가야 함
- zone(구역): 문 개폐 구역, 창문 앞 확보 구역 등 비워둬야 하는 공간 / wall(벽): 가구가 관통하면 안 됨

[배치 상식]
- 문 개폐 반경 안에는 가구 금지 / 창문 앞 500mm 비우기 (채광·환기·피난)
- 책상 앞 750mm (의자 공간) / 옷장 앞 600mm (문 열기) / 침대 측면 300mm 이상
- 가구가 방 경계나 벽에 걸치면 안 됨

[배치 규정 지식]
{rules}

[과거 배치 사례]
{cases}

[현재 배치 상태 (단위 m, Z-up)]
{scene}

[현재 검출된 위반]
{violations}

[대화 기록]
{history}

사용자 질문: "{text}"

답변 텍스트만 출력하세요 (JSON·코드블록·마크다운 서식 금지, 일반 텍스트로)."""


def answer(scene: Scene, text: str, history: list[dict]) -> str:
    kb = _load_knowledge()
    ins = inspect_scene(scene)
    violations = [
        f"{v['id']} {v['code']}: {v['detail']}" for v in ins["violations"]
    ] or ["없음 (모든 검사 통과)"]
    hist = "\n".join(
        f"{'사용자' if m.get('role') == 'user' else '도우미'}: {m.get('text', '')[:300]}"
        for m in history[-8:]) or "(첫 대화)"
    prompt = PROMPT.format(
        rules=json.dumps(kb["rules"], ensure_ascii=False),
        cases=json.dumps(kb["cases"], ensure_ascii=False),
        scene=_brief(scene),
        violations="\n".join(violations),
        history=hist,
        text=text[:500],
    )
    reply = llm_text(prompt + language_instruction())
    return reply or tr("지금은 답변 생성에 실패했습니다. AI 제공자 설정을 확인해주세요.",
                       "Unable to generate a reply. Check your AI provider configuration.")
