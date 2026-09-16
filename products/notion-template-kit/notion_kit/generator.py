"""Claude 에게 설계와 문구를 받는다.

호출은 **세 번**이다.

    1. 구조 설계 (spec)      — 가장 길고 중요하다
    2. 판매 문구 (sales)     — 금지 표현 검사를 통과할 때까지 다시 시킨다
    3. 구매자용 문서 (extras) — 자주 하는 실수·미리보기 지시서·파생 템플릿

`build_guide.md` 는 Claude 를 부르지 않는다. **설계에서 기계적으로 만든다.**
설명서가 설계와 어긋나면 그 설명서를 따라 만든 사람이 막히는데,
사람이 쓴 설명서는 설계가 바뀌면 조용히 낡기 때문이다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from notion_kit.schema import TemplateSpec        # noqa: E402
from shared import banned_phrases                  # noqa: E402

__all__ = ["TemplateGenerator", "MAX_RETRY", "PROMPTS_DIR"]

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

#: 형식이 틀렸을 때 다시 시키는 횟수.
MAX_RETRY = 2


def _prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"프롬프트가 없습니다: {path}")
    return path.read_text(encoding="utf-8")


class TemplateGenerator:
    """설계와 문구를 만든다. `ask_fn` 을 갈아 끼우면 모의 실행이 된다."""

    def __init__(self, model: str, ask_fn=None) -> None:
        self.model = model
        self.warnings: list[str] = []
        self.calls = 0
        if ask_fn is not None:
            self._ask = ask_fn
        else:
            from shared.llm import ask

            self._ask = ask

    def _call(self, system: str, user: str):
        self.calls += 1
        return self._ask(system, user, model=self.model, json_mode=True)

    # ------------------------------------------------------------ 구조 설계
    def build_spec(self, topic: str, audience: str) -> TemplateSpec:
        """구조를 받는다. 형식이 틀리면 **무엇이 틀렸는지 붙여** 다시 시킨다."""
        system = _prompt("spec")
        user = f"[주제] {topic}\n[타깃] {audience}\n\n위 주제로 노션 템플릿 구조를 설계하라."

        last_error = ""
        for attempt in range(1, MAX_RETRY + 2):
            raw = self._call(system, user)
            if not isinstance(raw, dict):
                last_error = "JSON 객체 하나가 아닙니다"
            else:
                raw.setdefault("topic", topic)
                raw.setdefault("audience", audience)
                try:
                    spec = TemplateSpec(**raw)
                except ValidationError as exc:
                    last_error = _readable(exc)
                else:
                    if attempt > 1:
                        self.warnings.append(f"구조를 {attempt}번째 시도에 받았습니다")
                    return spec

            if attempt > MAX_RETRY:
                break
            user = (f"[주제] {topic}\n[타깃] {audience}\n\n"
                    f"앞선 답이 규격에 맞지 않았다. 아래를 고쳐 다시 내라.\n{last_error}")

        raise ValueError(
            f"구조가 {MAX_RETRY + 1}번 모두 규격에 맞지 않았습니다.\n{last_error}\n"
            "  주제를 더 좁혀 보시거나 prompts/spec.md 에 예시를 늘려 보세요.")

    # ------------------------------------------------------------ 판매 문구
    def build_sales(self, spec: TemplateSpec) -> dict:
        """판매 문구를 받는다. 금지 표현이 있으면 그 표현을 짚어 다시 시킨다."""
        system = _prompt("sales")
        facts = _spec_digest(spec)
        user = f"[구조]\n{facts}\n\n위 템플릿의 판매 문구를 써라."

        for attempt in range(1, MAX_RETRY + 2):
            data = self._call(system, user)
            if not isinstance(data, dict):
                user = f"[구조]\n{facts}\n\nJSON 객체 하나만 내라."
                continue

            dirty = banned_phrases.check(json.dumps(data, ensure_ascii=False))
            missing = [key for key in ("titles", "intro", "included", "howto",
                                       "audience", "pricing") if not data.get(key)]
            if not dirty and not missing:
                if attempt > 1:
                    self.warnings.append(f"판매 문구를 {attempt}번째 시도에 받았습니다")
                return data

            if attempt > MAX_RETRY:
                break
            problems = []
            if dirty:
                problems.append("쓰면 안 되는 표현이 있다: " + ", ".join(dirty))
            if missing:
                problems.append("빠진 칸이 있다: " + ", ".join(missing))
            user = (f"[구조]\n{facts}\n\n앞선 답에 문제가 있었다.\n"
                    + "\n".join(f"- {p}" for p in problems) + "\n고쳐서 다시 내라.")

        self.warnings.append(
            "판매 문구에서 금지 표현을 끝내 걸러내지 못했습니다. "
            "sales_page.md 의 점검 표를 보고 직접 고치세요")
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------- 구매자용 문서
    def build_extras(self, spec: TemplateSpec) -> dict:
        system = _prompt("extras")
        user = f"[구조]\n{_spec_digest(spec)}\n\n구매자용 문서에 들어갈 내용을 써라."
        data = self._call(system, user)
        if not isinstance(data, dict):
            self.warnings.append("구매자용 문서를 받지 못해 빈 칸으로 두었습니다")
            return {}
        for key in ("mistakes", "preview", "variants"):
            if not data.get(key):
                self.warnings.append(f"구매자용 문서의 '{key}' 가 비었습니다")
        return data


def _readable(error: ValidationError) -> str:
    """pydantic 오류를 모델이 고칠 수 있는 말로 바꾼다."""
    lines = []
    for item in error.errors()[:8]:
        where = " → ".join(str(part) for part in item["loc"])
        lines.append(f"- {where}: {item['msg']}")
    return "\n".join(lines)


def _spec_digest(spec: TemplateSpec) -> str:
    """구조를 문구 작성에 쓸 만큼만 간추린다. 전부 넘기면 토큰만 먹는다."""
    lines = [f"이름: {spec.name}", f"주제: {spec.topic}", f"타깃: {spec.audience}",
             f"요약: {spec.summary}"]
    if spec.problems:
        lines.append("풀어 주는 문제: " + " / ".join(spec.problems))
    lines.append(f"데이터베이스 {len(spec.databases)}개:")
    for db in spec.databases:
        views = ", ".join(f"{v.name}({v.type})" for v in db.views)
        lines.append(f"  - {db.name}: {db.description}")
        lines.append(f"    속성 {len(db.properties)}개 · 뷰: {views}")
    if spec.buttons:
        lines.append("버튼: " + ", ".join(b.name for b in spec.buttons))
    relations = spec.relation_properties()
    lines.append(f"연결(관계·롤업) 속성 {len(relations)}개")
    return "\n".join(lines)
