"""원고에서 '상품 이야기가 나온 자리' 를 뽑는다.

Claude 를 **한 번** 부른다. 원고 한 편이면 충분하고, 나눠 부르면 문단 번호가
어긋나기 때문이다.

중요한 것은 이 단계가 **상품을 고르지 않는다**는 점이다. 뽑는 것은

    "3번 문단에서 캠핑 의자 이야기를 하고 있고, 사려는 기색이 4점쯤 된다"

까지다. 무엇을 붙일지는 사람이 정한다. 프로그램이 상품까지 정해 주면
본문과 무관한 물건이 섞여 들어가고, 그게 이 바닥에서 신뢰를 잃는 가장 빠른 길이다.

문단을 미리 잘라 번호를 붙여 넘긴다. 번호가 있어야 "어디에" 를 말할 수 있다.
"""

from __future__ import annotations

import sys
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from affiliate.schema import Extraction                              # noqa: E402

__all__ = ["split_paragraphs", "numbered", "Extractor", "MAX_RETRY", "PROMPTS_DIR"]

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

#: 형식이 틀렸을 때 다시 시키는 횟수.
MAX_RETRY = 2

#: 너무 긴 원고는 자른다. 릴스 캡션부터 롱폼 대본까지가 대상이라 이 정도면 넉넉하다.
MAX_CHARS = 20000


def split_paragraphs(text: str) -> list[str]:
    """빈 줄을 기준으로 문단을 나눈다.

    대본은 줄바꿈 한 번으로 이어 쓰는 경우가 많아, 빈 줄이 하나도 없으면
    줄 단위로 떨어뜨린다. 문단이 하나뿐이면 "어디에 넣을지" 를 말할 수 없다.
    """
    body = (text or "").strip()
    if not body:
        return []
    chunks = [block.strip() for block in body.split("\n\n") if block.strip()]
    if len(chunks) <= 1:
        chunks = [line.strip() for line in body.splitlines() if line.strip()]
    return chunks


def numbered(paragraphs: list[str]) -> str:
    """문단마다 번호를 붙인 글. 이대로 Claude 에게 넘긴다."""
    return "\n\n".join(f"[{index}] {text}" for index, text in enumerate(paragraphs))


def _prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"프롬프트가 없습니다: {path}")
    return path.read_text(encoding="utf-8")


def _readable(exc: ValidationError) -> str:
    lines = []
    for item in exc.errors()[:8]:
        where = " → ".join(str(part) for part in item["loc"])
        lines.append(f"  - {where}: {item['msg']}")
    return "\n".join(lines)


class Extractor:
    """언급 지점을 뽑아 온다. `ask_fn` 을 갈아 끼우면 모의 실행이 된다."""

    def __init__(self, model: str, ask_fn=None) -> None:
        self.model = model
        self.warnings: list[str] = []
        self.calls = 0
        if ask_fn is not None:
            self._ask = ask_fn
        else:
            from shared.llm import ask

            self._ask = ask

    def run(self, text: str, medium: str = "", title: str = "") -> tuple[Extraction, list[str]]:
        """원고 한 편을 읽고 언급 지점을 돌려준다.

        Returns:
            (추출 결과, 문단 목록)
        """
        paragraphs = split_paragraphs(text)
        if not paragraphs:
            raise ValueError("원고가 비어 있습니다")
        if len(text) > MAX_CHARS:
            self.warnings.append(
                f"원고가 길어 앞 {MAX_CHARS:,}자만 봅니다. 나눠서 돌리시는 편이 낫습니다")

        system = _prompt("extract")
        body = numbered(paragraphs)[:MAX_CHARS]
        user = (f"[채널] {medium or '미지정'}\n[제목] {title or '(없음)'}\n"
                f"[문단 수] {len(paragraphs)}\n\n--- 원고 ---\n{body}")

        last_error = ""
        for attempt in range(1, MAX_RETRY + 2):
            self.calls += 1
            raw = self._ask(system, user, model=self.model, json_mode=True)

            if not isinstance(raw, dict):
                last_error = "JSON 객체 하나가 아닙니다"
            else:
                raw.setdefault("medium", medium or "블로그")
                raw.setdefault("title", title)
                try:
                    extraction = Extraction(**raw)
                except ValidationError as exc:
                    last_error = _readable(exc)
                else:
                    before = len(extraction.mentions)
                    extraction.within(len(paragraphs))
                    dropped = before - len(extraction.mentions)
                    if dropped:
                        self.warnings.append(
                            f"본문에 없는 문단을 가리킨 언급 {dropped}개를 버렸습니다")
                    if attempt > 1:
                        self.warnings.append(f"{attempt}번째 시도에 형식이 맞았습니다")
                    return extraction, paragraphs

            if attempt > MAX_RETRY:
                break
            user = (f"앞선 답이 규격에 맞지 않았다. 아래를 고쳐 같은 원고를 다시 읽어라.\n"
                    f"{last_error}\n\n{user}")

        raise ValueError(
            f"추출이 {MAX_RETRY + 1}번 모두 규격에 맞지 않았습니다.\n{last_error}\n"
            "  원고가 너무 짧거나 상품 이야기가 없을 수 있습니다.")
