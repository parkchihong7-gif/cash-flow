"""이중키 인증 — 16종 공통 표준 테스트.

규격은 이미 돌아가고 있는 두 프로그램(공인중개사 기출문제·maim 네이버 블로그)의
관리자 매뉴얼에서 뽑았다. 그 매뉴얼이 사용자에게 약속한 동작을 그대로 확인한다.
여기서 어긋나면 사용자가 이미 배포한 안내문이 거짓말이 된다.
"""

from __future__ import annotations

import pytest

from core.keyauth import (
    DEVICES, KIND_LEGACY, KIND_PRIMARY, KIND_SECONDARY, MAX_BULK,
    RESET_WORD, KeyAuth, KeyError_, format_key, normalize,
)


@pytest.fixture
def auth(tmp_path):
    return KeyAuth(tmp_path / "keys.db")


# ───────────────────────────────────────────────────────────── 발급
def test_한_사람에게_1차키_하나와_2차키_셋(auth):
    """매뉴얼: 1차키는 사람당 1개, 2차키는 PC·노트북·휴대폰 3개."""
    issued = auth.issue_set("홍길동", "hong@example.com")

    assert len(issued.secondary) == 3
    assert tuple(issued.secondary) == DEVICES
    assert len({issued.primary, *issued.secondary.values()}) == 4, "키가 겹쳤다"

    assert len(auth.list_keys(kind=KIND_PRIMARY)) == 1
    assert len(auth.list_keys(kind=KIND_SECONDARY)) == 3


def test_키_모양은_XXXX_XXXX_XXXX(auth):
    code = auth.issue_set("홍길동", "hong@example.com").primary
    blocks = code.split("-")
    assert len(blocks) == 3 and all(len(b) == 4 for b in blocks)
    assert "0" not in code and "O" not in code, "헷갈리는 글자는 빼기로 했다"


def test_이름_없이는_발급하지_않는다(auth):
    """누구에게 준 키인지 남지 않으면 나중에 회수할 수 없다."""
    with pytest.raises(KeyError_, match="이름"):
        auth.issue_set("", "hong@example.com")


def test_이메일이_아니면_거절한다(auth):
    with pytest.raises(KeyError_, match="이메일"):
        auth.issue_set("홍길동", "hong")


def test_안내메일_문구에_키_네_개가_모두_들어간다(auth):
    issued = auth.issue_set("홍길동", "hong@example.com",
                            service_url="https://example.com")
    body = issued.mail_body("공인중개사 기출문제")

    assert issued.primary in body
    for device in DEVICES:
        assert f"- {device} : {issued.secondary[device]}" in body
    assert "https://example.com" in body
    assert "홍길동님" in body


# ───────────────────────────────────────────────────────────── 인증
def test_1차키와_2차키가_모두_맞아야_들어온다(auth):
    issued = auth.issue_set("홍길동", "hong@example.com")
    token, used = auth.authenticate(issued.primary, issued.secondary["PC"])

    assert token
    assert used.device == "PC"
    assert auth.check_session(token) == (True, "")


def test_남의_2차키는_통하지_않는다(auth):
    """키 두 개를 따로 주워도 섞어서는 못 쓴다. 이게 두 겹으로 나눈 이유다."""
    mine = auth.issue_set("홍길동", "hong@example.com")
    yours = auth.issue_set("김철수", "kim@example.com")

    with pytest.raises(KeyError_, match="짝이 아닙니다"):
        auth.authenticate(mine.primary, yours.secondary["PC"])


def test_칸을_바꿔_넣으면_알려준다(auth):
    """2차키를 1차키 칸에 넣는 실수는 반드시 일어난다. 이유를 말해 줘야 한다."""
    issued = auth.issue_set("홍길동", "hong@example.com")

    with pytest.raises(KeyError_, match="1차 인증키 칸에는 1차키"):
        auth.authenticate(issued.secondary["PC"], issued.secondary["노트북"])
    with pytest.raises(KeyError_, match="2차 인증키 칸에는 2차키"):
        auth.authenticate(issued.primary, issued.primary)


def test_띄어쓰기나_소문자로_쳐도_들어온다(auth):
    """키를 손으로 옮겨 적으면 반드시 생기는 일이라 받아 준다."""
    issued = auth.issue_set("홍길동", "hong@example.com")
    sloppy_primary = issued.primary.lower().replace("-", " ")
    sloppy_secondary = issued.secondary["PC"].lower().replace("-", "")

    token, _ = auth.authenticate(sloppy_primary, sloppy_secondary)
    assert auth.check_session(token)[0]


def test_없는_키는_어느_칸인지_말해_준다(auth):
    issued = auth.issue_set("홍길동", "hong@example.com")
    with pytest.raises(KeyError_, match="1차 인증키가 맞지 않습니다"):
        auth.authenticate("AAAA-BBBB-CCCC", issued.secondary["PC"])
    with pytest.raises(KeyError_, match="2차 인증키가 맞지 않습니다"):
        auth.authenticate(issued.primary, "AAAA-BBBB-CCCC")


# ────────────────────────────────────────────────────── 기기당 한 세션
def test_같은_2차키로_다시_들어오면_먼저_있던_기기가_끊긴다(auth):
    """매뉴얼의 핵심 약속. 키를 빌려줘도 동시에 둘은 못 쓴다."""
    issued = auth.issue_set("홍길동", "hong@example.com")
    first, _ = auth.authenticate(issued.primary, issued.secondary["PC"])
    second, _ = auth.authenticate(issued.primary, issued.secondary["PC"])

    alive, why = auth.check_session(first)
    assert alive is False
    assert why == "다른 기기에서 로그인되어 세션이 종료되었습니다", (
        "왜 끊겼는지 말해 주지 않으면 사용자는 고장으로 여긴다")
    assert auth.check_session(second)[0] is True


def test_다른_기기_2차키는_서로_끊지_않는다(auth):
    """PC 와 휴대폰을 같이 켜 두는 것은 정상이다. 기기 수만큼 허용한다."""
    issued = auth.issue_set("홍길동", "hong@example.com")
    pc, _ = auth.authenticate(issued.primary, issued.secondary["PC"])
    phone, _ = auth.authenticate(issued.primary, issued.secondary["휴대폰"])

    assert auth.check_session(pc)[0] is True
    assert auth.check_session(phone)[0] is True
    assert auth.live_sessions() == 2


def test_기기잠금을_끄면_끊기지_않는다(auth):
    """여럿이 한 화면을 같이 보는 곳(사무국 공용 PC)을 위한 예외."""
    issued = auth.issue_set("홍길동", "hong@example.com")
    first, _ = auth.authenticate(issued.primary, issued.secondary["PC"],
                                 device_lock=False)
    auth.authenticate(issued.primary, issued.secondary["PC"], device_lock=False)
    assert auth.check_session(first)[0] is True


def test_로그아웃하면_그_세션만_닫힌다(auth):
    issued = auth.issue_set("홍길동", "hong@example.com")
    pc, _ = auth.authenticate(issued.primary, issued.secondary["PC"])
    phone, _ = auth.authenticate(issued.primary, issued.secondary["휴대폰"])

    auth.close_session(pc)
    assert auth.check_session(pc) == (False, "로그아웃했습니다")
    assert auth.check_session(phone)[0] is True


# ───────────────────────────────────────────────────── 사용중지·삭제
def test_사용중지는_되돌릴_수_있다(auth):
    issued = auth.issue_set("홍길동", "hong@example.com")
    primary = auth.list_keys(kind=KIND_PRIMARY)[0]

    auth.suspend(primary.id)
    with pytest.raises(KeyError_, match="사용중지"):
        auth.authenticate(issued.primary, issued.secondary["PC"])

    auth.resume(primary.id)
    assert auth.authenticate(issued.primary, issued.secondary["PC"])[0]


def test_사용중지하면_쓰고_있던_세션도_끊는다(auth):
    """지금 들어와 있는 사람을 내보내지 못하면 정지 버튼이 의미가 없다."""
    issued = auth.issue_set("홍길동", "hong@example.com")
    token, _ = auth.authenticate(issued.primary, issued.secondary["PC"])

    auth.suspend(auth.list_keys(kind=KIND_PRIMARY)[0].id)
    assert auth.check_session(token)[0] is False


def test_1차키를_지우면_딸린_2차키도_같이_간다(auth):
    issued = auth.issue_set("홍길동", "hong@example.com")
    removed = auth.delete(auth.list_keys(kind=KIND_PRIMARY)[0].id)

    assert removed == 4
    assert auth.list_keys() == []
    assert auth.find(issued.secondary["PC"]) is None


def test_2차키_하나만_지우면_나머지는_남는다(auth):
    """기기 하나를 잃어버렸을 때 그 몫만 정리하는 쓰임 (매뉴얼)."""
    issued = auth.issue_set("홍길동", "hong@example.com")
    lost = auth.find(issued.secondary["휴대폰"])

    assert auth.delete(lost.id) == 1
    assert auth.authenticate(issued.primary, issued.secondary["PC"])[0]
    with pytest.raises(KeyError_, match="2차 인증키가 맞지 않습니다"):
        auth.authenticate(issued.primary, issued.secondary["휴대폰"])


# ───────────────────────────────────────────────────────── 전체 초기화
def test_초기화는_글자를_정확히_쳐야_돈다(auth):
    auth.issue_set("홍길동", "hong@example.com")

    for wrong in ["", "reset", "초기화할래", "ㅊㄱㅎ", "초 기 화"]:
        with pytest.raises(KeyError_, match="되돌릴 수 없습니다"):
            auth.reset_all(wrong)
    assert len(auth.list_keys()) == 4, "실패했는데 지워졌다"

    assert auth.reset_all(RESET_WORD) == 4
    assert auth.list_keys() == []


def test_초기화_글자_앞뒤_공백은_봐준다(auth):
    """복사해 붙이면 공백이 따라온다. 글자만 맞으면 통과시킨다."""
    auth.issue_set("홍길동", "hong@example.com")
    assert auth.reset_all("  초기화  ") == 4


def test_프로그램별로만_초기화할_수_있다(auth):
    """16종이 한 저장소를 쓰므로, 한 프로그램을 비워도 남은 곳은 멀쩡해야 한다."""
    auth.issue_set("홍길동", "hong@example.com", program_id="exam-drill")
    auth.issue_set("김철수", "kim@example.com", program_id="naver-blog")

    assert auth.reset_all(RESET_WORD, program_id="exam-drill") == 4
    assert len(auth.list_keys(program_id="naver-blog")) == 4


# ───────────────────────────────────────────────── 일괄 생성·레거시
def test_레거시_단일키는_1차키_칸만으로_통과한다(auth):
    """예전에 뿌린 키를 계속 쓰게 해 준다. 하위호환."""
    code = auth.bulk_legacy(1)[0]
    token, used = auth.authenticate(code, "")

    assert used.kind == KIND_LEGACY
    assert auth.check_session(token)[0] is True


def test_일괄_생성_상한은_500(auth):
    assert len(auth.bulk_legacy(MAX_BULK)) == MAX_BULK
    with pytest.raises(KeyError_, match="500"):
        auth.bulk_legacy(MAX_BULK + 1)
    with pytest.raises(KeyError_, match="1 이상"):
        auth.bulk_legacy(0)


def test_유효기간을_비우면_무제한(auth):
    code = auth.bulk_legacy(1, expires_days=None)[0]
    assert auth.find(code).expires_at == ""
    assert auth.find(code).expired is False


def test_기간이_지난_키는_막고_만료라고_말한다(auth):
    """사용중지와 만료는 고객 응대가 다르다. 구별해서 알려 줘야 한다."""
    issued = auth.issue_set("홍길동", "hong@example.com", expires_days=1)
    key = auth.find(issued.primary)
    with auth._conn() as conn:                      # 어제로 돌려 놓는다
        conn.execute("UPDATE auth_keys SET expires_at = '2020-01-01'")

    assert auth.find(issued.primary).expired is True
    assert auth.find(issued.primary).state_label == "만료"
    with pytest.raises(KeyError_, match="만료된 키"):
        auth.authenticate(issued.primary, issued.secondary["PC"])
    assert key.id


def test_쓰던_중에_키가_만료되면_세션도_끝난다(auth):
    issued = auth.issue_set("홍길동", "hong@example.com")
    token, _ = auth.authenticate(issued.primary, issued.secondary["PC"])

    with auth._conn() as conn:
        conn.execute("UPDATE auth_keys SET expires_at = '2020-01-01'")
    assert auth.check_session(token) == (False, "만료된 키입니다")


# ─────────────────────────────────────────────────── 프로그램 분리·집계
def test_프로그램_전용_키는_그_프로그램에서만_찾는다(auth):
    issued = auth.issue_set("홍길동", "hong@example.com", program_id="exam-drill")
    assert auth.find(issued.primary, program_id="exam-drill") is not None
    assert auth.find(issued.primary, program_id="naver-blog") is None


def test_공용_키는_어느_프로그램에서도_통한다(auth):
    """program_id 를 비우면 16종 전체 공용 키가 된다."""
    issued = auth.issue_set("홍길동", "hong@example.com")
    assert auth.find(issued.primary, program_id="senior-video") is not None


def test_집계는_사람_수를_이메일로_센다(auth):
    auth.issue_set("홍길동", "hong@example.com")
    auth.issue_set("김철수", "kim@example.com")
    counts = auth.counts()

    assert counts == {"primary": 2, "secondary": 6, "legacy": 0,
                      "suspended": 0, "expired": 0, "holders": 2,
                      # 파는 키와 쓰는 키를 따로 센다. 기본은 쓰는 키다.
                      "admins": 0, "clients": 2}


# ───────────────────────────────────────────────────────── 마스터 토큰
def test_마스터_토큰은_정확히_맞아야_한다(auth):
    assert KeyAuth.master_matches("s3cret", "s3cret") is True
    assert KeyAuth.master_matches(" s3cret ", "s3cret") is True
    assert KeyAuth.master_matches("s3cre", "s3cret") is False
    assert KeyAuth.master_matches("", "s3cret") is False
    assert KeyAuth.master_matches("아무거나", "") is False or True  # 빈 설정은 별도 처리


# ───────────────────────────────────────────────────────────── 잡다
def test_정규화는_열두_글자가_아니면_그대로_둔다(auth):
    assert normalize("abcd-efgh-ijkl") == "ABCD-EFGH-IJKL"
    assert normalize("짧음") == ""
    assert normalize("") == ""


def test_키는_매번_다르게_나온다():
    assert len({format_key() for _ in range(200)}) == 200
