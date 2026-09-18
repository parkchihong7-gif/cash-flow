"""공인중개사 시험 구조 — 공개 자료만 쓴다.

시험 과목과 배점은 「공인중개사법 시행령」과 한국산업인력공단 시행계획 공고에
나오는 **공개 정보**다. 저작권법 제7조는 국가·지자체가 작성한 고시·공고를 보호
대상에서 빼고 있어 이런 구조 정보는 인용할 수 있다.

**문제 본문은 다르다.** 시험문제는 어문저작물로 보호받는다는 것이 법원의 판단이다
(대법원 2007다354, 대학 입시문제). 그래서 이 프로그램은 문제 텍스트를 **담지도,
배포하지도 않는다.** 구조와 통계만 다룬다. 자세한 것은 README 를 보라.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["SUBJECTS", "Subject", "subject_of", "all_units", "PASS_RULE", "ROUND_1", "ROUND_2"]

#: 합격 기준. 공개된 시행 규칙 그대로다.
PASS_RULE = (
    "매 과목 40점 이상, 전 과목 평균 60점 이상이면 합격합니다. "
    "상대평가가 아니라 절대평가라서, 남과 견줄 것 없이 60점만 넘기면 됩니다."
)

ROUND_1 = "1차"
ROUND_2 = "2차"


@dataclass
class Subject:
    """과목 하나. 단원 목록은 학습 범위를 나누는 기준으로만 쓴다."""

    key: str
    name: str
    round: str
    questions: int
    minutes: int
    units: list[str] = field(default_factory=list)

    @property
    def per_question_seconds(self) -> int:
        """한 문제에 쓸 수 있는 시간(초). 시간 배분 연습에 쓴다."""
        return round(self.minutes * 60 / self.questions)


#: 과목 구성. 1차 2과목·2차 3과목, 과목당 40문항.
SUBJECTS: tuple[Subject, ...] = (
    Subject("civil", "민법 및 민사특별법", ROUND_1, 40, 50, [
        "법률행위", "의사표시", "대리", "무효와 취소", "조건과 기한",
        "물권법 총론", "점유권", "소유권", "용익물권", "담보물권",
        "계약법 총론", "매매", "임대차", "주택임대차보호법",
        "상가건물임대차보호법", "집합건물법", "가등기담보법", "부동산실명법",
    ]),
    Subject("intro", "부동산학개론", ROUND_1, 40, 50, [
        "부동산학 총론", "부동산의 특성", "부동산 경제론", "부동산 시장론",
        "부동산 정책론", "부동산 투자론", "부동산 금융론", "부동산 개발론",
        "부동산 관리론", "부동산 감정평가론",
    ]),
    Subject("law", "공인중개사법령 및 중개실무", ROUND_2, 40, 50, [
        "총칙과 용어", "중개사무소 개설등록", "중개업무", "중개계약",
        "개업공인중개사의 의무", "손해배상책임과 보증", "보수", "교육과 지도감독",
        "행정처분", "벌칙", "중개실무 총론", "부동산거래신고", "경매와 공매",
    ]),
    Subject("public", "부동산공법", ROUND_2, 40, 50, [
        "국토계획법 총칙", "광역도시계획과 도시기본계획", "도시관리계획",
        "용도지역·지구·구역", "도시계획시설", "지구단위계획", "개발행위허가",
        "도시개발법", "도시정비법", "건축법", "주택법", "농지법",
    ]),
    Subject("tax", "부동산공시법령 및 부동산 관련 세법", ROUND_2, 40, 50, [
        "지적제도 총칙", "토지의 등록", "지적공부", "토지이동과 지적정리",
        "등기 총론", "표시에 관한 등기", "권리에 관한 등기", "각종 등기절차",
        "조세총론", "취득세", "등록면허세", "재산세", "종합부동산세", "양도소득세",
    ]),
)

_BY_KEY = {subject.key: subject for subject in SUBJECTS}
_BY_NAME = {subject.name: subject for subject in SUBJECTS}


def subject_of(value: str) -> Subject:
    """과목 키나 이름으로 찾는다. 줄여 쓴 이름도 받아 준다."""
    text = (value or "").strip()
    if text in _BY_KEY:
        return _BY_KEY[text]
    if text in _BY_NAME:
        return _BY_NAME[text]
    for subject in SUBJECTS:
        if text and (text in subject.name or subject.name.startswith(text)):
            return subject
    raise ValueError(
        f"모르는 과목입니다: {value}\n"
        f"  쓸 수 있는 과목: {', '.join(s.key for s in SUBJECTS)}")


def all_units() -> dict[str, list[str]]:
    """과목별 단원 목록."""
    return {subject.key: list(subject.units) for subject in SUBJECTS}
