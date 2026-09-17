"""모의 실행용 캡션. Claude 를 부르지 않는다.

시연과 테스트에서 승인 흐름을 끝까지 볼 수 있어야 해서 둔다.
**부탁조 문구와 금지 표현이 없는 문장**만 돌려준다. 그래야 검사도 통과한다.
"""

from __future__ import annotations

__all__ = ["fake_ask"]


def fake_ask(system: str, user: str, **kwargs):
    note = ""
    if "[사진·메모]" in user:
        note = user.split("[사진·메모]", 1)[1].strip()
    sponsored = "있음" in user.split("[광고·협찬 여부]", 1)[-1][:20]

    head = "광고) " if sponsored else ""
    first = note.splitlines()[0][:40] if note else "오늘의 기록"

    return {
        "caption": (f"{head}{first}\n\n"
                    "오늘 준비한 것들을 사진으로 남겨 둡니다.\n"
                    "궁금한 점은 댓글로 남겨 주시면 확인하는 대로 답 드릴게요.\n"
                    "영업시간과 오시는 길은 프로필 링크에 있습니다."),
        "hashtags": ["#동네가게", "#사장님일상", "#오늘의준비", "#소상공인"],
        "first_line_note": "'더 보기' 앞 한 줄에 무엇에 대한 글인지 담았습니다",
    }
