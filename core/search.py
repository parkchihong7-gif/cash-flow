"""전체 검색.

프로그램이 여덟 개가 되니 찾을 것이 많아졌다. 매뉴얼 18개, 편집 가능한 파일
수십 개, FAQ 90개가 넘는다. 어디에 뭐가 있는지 기억해서 찾아 들어가야 했다.

**따로 색인을 만들어 두지 않는다.** 매니페스트와 문서를 그때그때 읽어 훑는다.
항목이 수백 개 수준이라 이 편이 빠르고, 무엇보다 **파일을 고치면 바로 반영된다.**
색인을 쌓아 두면 언제 다시 만들지를 관리해야 하고, 그 관리를 빠뜨리면
검색 결과가 조용히 낡는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

__all__ = ["Hit", "search", "GROUPS", "MAX_PER_GROUP"]

#: 결과를 묶어 보여 줄 갈래와 그 순서.
GROUPS = ("프로그램", "매뉴얼", "설정·파일", "고객")

#: 갈래마다 최대 몇 개까지 보여 줄지.
MAX_PER_GROUP = 8

_SPACES = re.compile(r"\s+")


@dataclass
class Hit:
    group: str
    title: str
    subtitle: str
    href: str
    snippet: str = ""
    score: int = 0


def _flatten(text: str) -> str:
    return _SPACES.sub(" ", str(text or "")).strip()


def _snippet(haystack: str, needle: str, width: int = 90) -> str:
    """찾은 낱말 앞뒤를 잘라 보여 준다."""
    flat = _flatten(haystack)
    at = flat.lower().find(needle.lower())
    if at < 0:
        return flat[:width] + ("…" if len(flat) > width else "")
    start = max(0, at - width // 3)
    end = min(len(flat), at + width)
    return ("…" if start else "") + flat[start:end] + ("…" if end < len(flat) else "")


def _score(needle: str, title: str, body: str) -> int:
    """제목에 있으면 크게, 본문에 있으면 작게."""
    needle = needle.lower()
    title_flat, body_flat = title.lower(), body.lower()
    if needle == title_flat:
        return 100
    if title_flat.startswith(needle):
        return 70
    if needle in title_flat:
        return 50
    if needle in body_flat:
        return 10 + min(10, body_flat.count(needle))
    return 0


def _program_hits(registry, needle: str) -> list[Hit]:
    hits: list[Hit] = []
    for program in registry.programs:
        label = f"{program.number}. {program.name}"

        body_parts = [program.tagline, program.summary]
        body_parts += [f"{s.title} {s.body}" for s in program.steps]
        body_parts += [f"{f.q} {f.a}" for f in program.faq]
        body_parts += [f"{o.label} {o.description}" for o in program.outputs]
        body = "\n".join(body_parts)

        score = _score(needle, program.name, body)
        if score:
            hits.append(Hit("프로그램", label, program.tagline,
                            f"/programs/{program.id}",
                            _snippet(body, needle), score))

        for step in program.steps:
            if needle.lower() in f"{step.title} {step.body}".lower():
                hits.append(Hit("프로그램", f"{program.name} — {step.title}",
                                "이용 순서", f"/programs/{program.id}",
                                _snippet(step.body, needle), 30))
        for item in program.faq:
            if needle.lower() in f"{item.q} {item.a}".lower():
                hits.append(Hit("프로그램", f"{program.name} — {item.q}",
                                "자주 묻는 질문", f"/programs/{program.id}",
                                _snippet(item.a, needle), 35))

        for spec in program.settings:
            if needle.lower() in f"{spec.key} {spec.label} {spec.help}".lower():
                hits.append(Hit("설정·파일", f"{program.name} — {spec.label}",
                                f"설정 {spec.key}", f"/programs/{program.id}/edit",
                                _snippet(spec.help, needle), 25))
        for spec in program.editable_files:
            if needle.lower() in f"{spec.path} {spec.label} {spec.help}".lower():
                hits.append(Hit("설정·파일", f"{program.name} — {spec.label}",
                                spec.path,
                                f"/programs/{program.id}/file?path={spec.path}",
                                _snippet(spec.help, needle), 25))
    return hits


def _manual_hits(registry, docs_dir: Path, needle: str) -> list[Hit]:
    hits: list[Hit] = []
    shared = [("관리자 매뉴얼", docs_dir / "admin-manual.md", "/manual/admin"),
              ("클라이언트 매뉴얼", docs_dir / "client-manual.md", "/manual/client")]

    for program in registry.programs:
        for audience, label in (("admin", "관리자용"), ("client", "고객용")):
            path = getattr(program.manuals, audience, "")
            if path:
                shared.append((f"{program.name} {label} 매뉴얼",
                               program.resolve(path),
                               f"/programs/{program.id}/manual/{audience}"))

    for title, path, href in shared:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, ValueError):
            continue
        if needle.lower() not in text.lower():
            continue
        # 어느 장에서 나왔는지 알려 준다
        chapter = ""
        for line in text.splitlines():
            if line.startswith("## "):
                chapter = line[3:].strip()
            if needle.lower() in line.lower():
                break
        hits.append(Hit("매뉴얼", title, chapter or "본문", href,
                        _snippet(text, needle), 20 + min(10, text.lower().count(needle.lower()))))
    return hits


def _member_hits(db, needle: str) -> list[Hit]:
    hits = []
    for row in db.list_members(needle):
        hits.append(Hit(
            "고객", row["name"],
            " · ".join(filter(None, [row["email"], row["source"]])),
            f"/members/{row['id']}",
            f"이용권 {row['license_count']}건 · 누적 {int(row['paid'] or 0):,}원", 40))
    return hits


def search(query: str, registry, db, docs_dir: Path) -> dict[str, list[Hit]]:
    """갈래별로 묶은 검색 결과."""
    needle = (query or "").strip()
    if len(needle) < 2:
        return {}

    found = _program_hits(registry, needle)
    found += _manual_hits(registry, docs_dir, needle)
    found += _member_hits(db, needle)

    grouped: dict[str, list[Hit]] = {}
    for group in GROUPS:
        rows = sorted((hit for hit in found if hit.group == group),
                      key=lambda hit: -hit.score)
        if rows:
            grouped[group] = rows[:MAX_PER_GROUP]
    return grouped
