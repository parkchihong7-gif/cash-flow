"""노션 속성 타입과 API 제약.

**여기 적힌 제약이 이 상품의 값어치입니다.** 노션 템플릿을 팔아 본 적이 없으면
"API 로 다 만들면 되지" 라고 생각하게 되는데, 실제로는 손으로 해야 하는 것이
꽤 있습니다. 그걸 모르고 설계하면 납품 직전에 막힙니다.

두 목록을 나눠 둡니다.

    CREATABLE     공개 API 로 만들 수 있는 타입
    MANUAL_ONLY   노션 화면에서는 되지만 공개 API 로는 못 만드는 타입

`deploy` 는 MANUAL_ONLY 를 만나면 멈추지 않고 **가장 가까운 타입으로 바꿔 만든 뒤
무엇을 바꿨는지 기록**합니다. 그래야 나머지라도 자동으로 만들어집니다.

⚠️ 이 목록은 공개 문서를 근거로 적은 것이고, 이 저장소를 만든 컨테이너에서는
   api.notion.com 에 닿지 못해 **실제 호출로 확인하지 못했습니다.**
   노션 API 는 조용히 바뀌는 편이라, 처음 쓰실 때 한 번은 직접 확인하세요.
   틀린 것이 있으면 이 파일만 고치면 됩니다.
"""

from __future__ import annotations

__all__ = ["CREATABLE", "MANUAL_ONLY", "ALL_TYPES", "NEEDS_OPTIONS",
           "SUBSTITUTE", "ROLLUP_FUNCTIONS", "VIEW_TYPES", "why_manual"]

#: 공개 API 의 databases.create / databases.update 로 만들 수 있는 속성 타입.
CREATABLE = frozenset({
    "title", "rich_text", "number", "select", "multi_select", "date",
    "people", "files", "checkbox", "url", "email", "phone_number",
    "formula", "relation", "rollup",
    "created_time", "created_by", "last_edited_time", "last_edited_by",
})

#: 노션 화면에서는 만들 수 있지만 공개 API 로는 만들지 못하는 타입.
MANUAL_ONLY = {
    "status": "상태(status) 속성은 공개 API 로 만들지 못합니다. "
              "노션에서 속성 타입을 '상태' 로 바꾸면 그룹(시작 전·진행 중·완료)이 생깁니다.",
    "unique_id": "고유 ID 속성은 공개 API 로 만들지 못합니다. 노션에서 추가하세요.",
    "verification": "확인(verification) 속성은 공개 API 로 만들지 못합니다.",
}

#: 기획서(spec)에 적을 수 있는 전체 타입.
ALL_TYPES = frozenset(CREATABLE | set(MANUAL_ONLY))

#: 선택지 목록이 있어야 하는 타입.
NEEDS_OPTIONS = frozenset({"select", "multi_select", "status"})

#: API 로 못 만드는 타입을 대신할 타입. 뜻이 가장 가까운 것으로 고른다.
SUBSTITUTE = {
    "status": "select",
    "unique_id": "number",
    "verification": "checkbox",
}

#: 롤업에서 쓸 수 있는 계산 방식.
ROLLUP_FUNCTIONS = frozenset({
    "count", "count_values", "sum", "average", "median", "min", "max", "range",
    "percent_empty", "percent_not_empty", "show_original", "unique",
})

#: 기획서에 적을 수 있는 뷰 종류.
#:
#: **공개 API 로는 뷰를 만들지 못합니다.** 그래서 뷰는 설계서에만 적히고,
#: `build_guide.md` 가 손으로 만드는 법을 알려 줍니다. deploy 도 이 사실을 알립니다.
VIEW_TYPES = frozenset({"table", "board", "calendar", "list", "gallery", "timeline"})


def why_manual(property_type: str) -> str:
    """API 로 못 만드는 이유. 모르는 타입이면 빈 문자열."""
    return MANUAL_ONLY.get(property_type, "")
