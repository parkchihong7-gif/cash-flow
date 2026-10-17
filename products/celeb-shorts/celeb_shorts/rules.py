"""이 상품이 **양보하지 않는 규칙** — 입력 검사와 기획서 검사.

연예인 쇼핑 쇼츠에서 채널이 망가지는 길은 정해져 있다.

1. 연예인 얼굴·방송 화면을 쓴다 → 저작권 신고, 퍼블리시티권 분쟁, 재사용 콘텐츠 판정.
2. 확인 안 된 아이템을 "○○ 착용템" 이라고 한다 → 허위 표시.
3. 출처 없는 가격·"원가" 를 띄운다 → 허위 표시, 신뢰 하락.
4. 대가성 문구를 빠뜨린다 → 쿠팡 자격 정지, 유튜브 제재.

1번은 장면 화면 종류(`schema.VISUALS`)에서 아예 고를 수 없게 막았다. 나머지는 여기서 본다.
고칠 수 있는 것은 고치고(`notes`), 사람이 봐야 하는 것은 경고(`warn`),
그대로 올리면 안 되는 것은 막음(`block`)으로 남긴다. 막음이 하나라도 있으면 승인할 수 없다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from shared.banned_phrases import check as banned_check

from .schema import PlanDraft, Scene, ShortsInput

__all__ = ["Issue", "InputReview", "review_input", "review_plan", "SUBTITLE_MAX", "split_subtitle"]

#: 자막 한 장 한 줄 최대 글자 수. 15초 쇼츠는 한 장이 1~2초라 길면 못 읽는다.
SUBTITLE_MAX = 15

#: 같은 물건이라고 단정하는 말 — 확인 안 된 아이템에는 쓰면 안 된다.
_SAME_WORDS = ("똑같은", "똑같이", "동일 제품", "동일제품", "같은 제품", "바로 그", "정품")

#: 가격처럼 보이는 숫자.
_PRICE_RE = re.compile(r"\d[\d,\.]*\s*(?:만\s*)?(?:천\s*)?원")


@dataclass
class Issue:
    level: str          # "block" | "warn"
    where: str
    message: str

    def line(self) -> str:
        mark = "⛔" if self.level == "block" else "⚠"
        return f"{mark} [{self.where}] {self.message}"


@dataclass
class InputReview:
    """입력을 읽고 정한 것 — 이름을 써도 되는지, 아이템마다 어떻게 부를지."""

    data: ShortsInput
    name_allowed: bool
    issues: list[Issue] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(issue.level == "block" for issue in self.issues)

    def item_mode(self, index: int) -> str:
        item = self.data.items[index]
        return "확인" if (item.confirmed and self.data.has_source) else "비슷한 스타일"

    def shown_price(self, index: int) -> int | None:
        item = self.data.items[index]
        return item.price if (item.price is not None and item.price_source.strip()) else None

    @property
    def any_price(self) -> bool:
        return any(self.shown_price(i) is not None for i in range(len(self.data.items)))


def review_input(data: ShortsInput) -> InputReview:
    review = InputReview(data=data, name_allowed=bool(data.celebrity.strip() and data.has_source))

    if len(data.items) > data.max_items:
        review.issues.append(Issue(
            "block", "입력",
            f"{data.duration_sec}초에 아이템 {len(data.items)}개는 너무 많습니다. "
            f"{data.max_items}개까지 넣으세요. 한 장면이 1초도 안 돼 아무것도 안 보입니다."))

    if data.celebrity.strip() and not data.has_source:
        review.notes.append(
            f"출처 주소가 없어 '{data.celebrity}' 이름을 쓰지 않습니다. "
            "'비슷한 스타일' 쇼츠로 만듭니다. 이름을 쓰려면 기사·공식 SNS 주소를 넣으세요.")

    for index, item in enumerate(data.items):
        where = f"아이템 {index + 1}"
        if item.confirmed and not data.has_source:
            review.notes.append(f"{where} '{item.name}': 확인(o)이지만 출처가 없어 '비슷한 스타일'로 소개합니다.")
        if item.price is not None and not item.price_source.strip():
            review.notes.append(f"{where} '{item.name}': 가격 출처가 없어 가격을 화면에 쓰지 않습니다.")

    return review


def split_subtitle(text: str) -> str:
    """15자를 넘는 자막을 의미 단위(띄어쓰기) 두 줄로 나눈다. 못 나누면 그대로."""
    text = text.strip()
    if len(text) <= SUBTITLE_MAX or "\n" in text:
        return text
    middle = len(text) / 2
    spaces = [i for i, ch in enumerate(text) if ch == " "]
    if not spaces:
        return text
    cut = min(spaces, key=lambda i: abs(i - middle))
    return text[:cut].rstrip() + "\n" + text[cut + 1:].lstrip()


def _fix_timing(scenes: list[Scene], duration: int) -> tuple[list[Scene], bool]:
    """장면을 0초부터 빈틈없이 이어 붙이고, 끝을 목표 길이에 맞춘다."""
    scenes = sorted(scenes, key=lambda s: s.start)
    lengths = [max(s.end - s.start, 0.5) for s in scenes]
    total = sum(lengths)
    changed = abs(total - duration) > 0.05 or scenes[0].start != 0
    scale = duration / total
    cursor = 0.0
    fixed = []
    for scene, length in zip(scenes, lengths):
        end = round(cursor + length * scale, 2)
        if scene is scenes[-1]:
            end = float(duration)
        if abs(scene.start - cursor) > 0.05 or abs(scene.end - end) > 0.05:
            changed = True
        fixed.append(scene.model_copy(update={"start": round(cursor, 2), "end": end}))
        cursor = end
    return fixed, changed


def _texts(plan: PlanDraft) -> list[tuple[str, str]]:
    found = [("제목", plan.title), ("후크", plan.hook), ("설명", plan.description)]
    for number, scene in enumerate(plan.scenes, 1):
        found.append((f"장면 {number} 자막", scene.subtitle))
        found.append((f"장면 {number} 내레이션", scene.narration))
    found += [("해시태그", " ".join(plan.hashtags))]
    return found


def review_plan(plan: PlanDraft, review: InputReview) -> tuple[PlanDraft, list[Issue], list[str]]:
    """기획 초안을 고칠 수 있는 만큼 고치고, 남은 문제를 돌려준다.

    Returns:
        (고친 기획, 문제 목록, 고친 내역)
    """
    data = review.data
    notes: list[str] = []
    issues: list[Issue] = []

    # 1) 이름 — 출처가 없으면 어디에도 나오면 안 된다.
    name = data.celebrity.strip()
    if name and not review.name_allowed:
        def scrub(text: str) -> str:
            return text.replace(name, "").replace("  ", " ").strip()

        leaked = any(name in text for _, text in _texts(plan))
        if leaked:
            plan = plan.model_copy(update={
                "title": scrub(plan.title), "hook": scrub(plan.hook) or "요즘 이 스타일",
                "description": scrub(plan.description),
                "hashtags": [tag for tag in plan.hashtags if name.replace(" ", "") not in tag],
                "scenes": [s.model_copy(update={"subtitle": scrub(s.subtitle) or "이 스타일",
                                                "narration": scrub(s.narration)})
                           for s in plan.scenes],
            })
            notes.append(f"출처가 없어 '{name}' 이름을 기획서에서 지웠습니다.")

    # 2) 장면 화면과 아이템 번호
    scenes = []
    for number, scene in enumerate(plan.scenes, 1):
        index = scene.item_index
        if index is not None and not (0 <= index < len(data.items)):
            notes.append(f"장면 {number}: 없는 아이템 번호({index})라 글자 화면으로 바꿨습니다.")
            scene = scene.model_copy(update={"item_index": None, "visual": "text_card"})
        elif index is None and scene.visual != "text_card":
            scene = scene.model_copy(update={"visual": "text_card"})
        scenes.append(scene)

    # 3) 시간
    scenes, retimed = _fix_timing(scenes, data.duration_sec)
    if retimed:
        notes.append(f"장면 시간을 0~{data.duration_sec}초에 빈틈없이 맞췄습니다.")

    # 4) 자막 길이
    wrapped = []
    for number, scene in enumerate(scenes, 1):
        subtitle = split_subtitle(scene.subtitle)
        if subtitle != scene.subtitle:
            notes.append(f"장면 {number}: 자막이 {SUBTITLE_MAX}자를 넘어 두 줄로 나눴습니다.")
        if any(len(line) > SUBTITLE_MAX for line in subtitle.splitlines()):
            issues.append(Issue("warn", f"장면 {number} 자막",
                                f"한 줄이 {SUBTITLE_MAX}자를 넘습니다. 줄이세요: {subtitle!r}"))
        wrapped.append(scene.model_copy(update={"subtitle": subtitle}))
    hook = split_subtitle(plan.hook)
    plan = plan.model_copy(update={"scenes": wrapped, "hook": hook})

    # 5) 확인 안 된 아이템을 같은 물건이라고 하는가
    for number, scene in enumerate(plan.scenes, 1):
        if scene.item_index is None or review.item_mode(scene.item_index) == "확인":
            continue
        text = f"{scene.subtitle} {scene.narration}"
        for word in _SAME_WORDS:
            if word in text:
                issues.append(Issue(
                    "block", f"장면 {number}",
                    f"확인 안 된 아이템에 '{word}' 를 썼습니다. '비슷한 스타일' 로 고치세요."))
                break

    # 6) 가격·원가 — 출처 있는 가격이 하나도 없는데 숫자가 나오면 막는다.
    for where, text in _texts(plan):
        if not text:
            continue
        if "원가" in text:
            issues.append(Issue("block", where,
                                "'원가' 는 출처로 확인하기 어렵습니다. 빼거나 '판매가' 로 바꾸세요."))
        if _PRICE_RE.search(text) and not review.any_price:
            issues.append(Issue("block", where,
                                f"출처 없는 가격이 들어갔습니다: {_PRICE_RE.search(text).group(0)!r}"))

    # 7) 판매 금지 문구 (공용 목록)
    for where, text in _texts(plan):
        found = banned_check(text or "")
        if found:
            issues.append(Issue("block", where, "금지 문구: " + ", ".join(found)))

    return plan, issues, notes
