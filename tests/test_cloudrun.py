"""Cloud Run 에 올릴 때 지켜야 하는 것들.

maim 이 같은 길을 먼저 갔고, 넘어진 곳이 문서에 남아 있다. 그 지점마다
여기서 지킨다. 사람이 기억하는 대신 시험이 기억한다.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from core import gcsstate

ROOT = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------ 상태 맞추기
def test_only_the_needed_files_are_synced():
    """**시작할 때 버킷 전체를 받으면 안 된다.**

    maim 은 생성 이미지가 쌓일수록 시작이 느려져, 컨테이너 시작 제한을 넘겨
    배포 자체가 실패했다. 다시 만들면 되는 것(산출물)은 받지 않는다.
    """
    assert set(gcsstate.NEEDED) == {"dashboard.db", ".dashboard_secret"}
    assert not any("output" in name for name in gcsstate.NEEDED)


def test_placeholder_bucket_counts_as_off(monkeypatch):
    """`YOUR_...` 를 그대로 둔 채 배포하는 일이 잦다. 고장나지 말아야 한다."""
    for 가짜 in ("YOUR_BUCKET", "your-bucket", "YOUR_BUCKET_NAME", "  ", ""):
        monkeypatch.setenv("GCS_BUCKET", 가짜)
        assert gcsstate.bucket_name() == "", 가짜
        assert not gcsstate.enabled()

    monkeypatch.setenv("GCS_BUCKET", "cashflow-state")
    assert gcsstate.bucket_name() == "cashflow-state"


def test_it_does_nothing_at_home(monkeypatch):
    """집에서 쓸 때는 아무 일도 하지 않는다. 지금까지처럼 로컬 파일만."""
    monkeypatch.delenv("GCS_BUCKET", raising=False)
    assert gcsstate.enabled() is False
    assert gcsstate.restore() == []
    assert gcsstate.save() == []
    assert gcsstate.start_autosave() is None


def test_one_bucket_can_hold_more_than_one_program():
    """maim 버킷을 같이 써도 섞이면 안 된다."""
    assert gcsstate.PREFIX, "앞머리가 없으면 파일 이름이 부딪친다"


def test_db_is_restored_before_it_is_opened():
    """**DB 를 열기 전에** 받아 와야 한다.

    열고 나서 덮으면 그 사이에 쓴 것이 날아가고, SQLite 가 열어 둔 파일을
    갈아 끼우는 일이 된다.
    """
    글 = (ROOT / "dashboard" / "app.py").read_text(encoding="utf-8")
    받기 = 글.index("gcsstate.restore()")
    열기 = 글.index("app.state.db = Database(db_path)")
    assert 받기 < 열기, "받아 오기가 DB 열기보다 앞에 있어야 한다"


# ------------------------------------------------------------ 배포 설정
def test_gcloudignore_keeps_customer_data_out():
    """고객 자료가 컨테이너에 섞여 들어가면 안 된다."""
    글 = (ROOT / ".gcloudignore").read_text(encoding="utf-8")
    for 빼야할것 in ("data/", "*.db", ".env", "products/*/outputs/"):
        assert 빼야할것 in 글, f"{빼야할것} 이 빠져 있습니다"


def test_dockerfile_takes_the_port_from_the_host():
    """Cloud Run 이 PORT 를 정해 준다. 8000 에 고정하면 안 뜬다."""
    글 = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "PORT" in 글
    assert "healthz" in 글, "살았는지 확인할 주소가 있어야 한다"


def test_deploy_guide_pins_the_things_that_cost_money():
    """요금이 갈리는 설정을 명령서가 못 박아야 한다."""
    글 = (ROOT / "deploy" / "cloudrun.md").read_text(encoding="utf-8")
    assert "--min-instances 0" in 글, "여기서 요금이 갈린다"
    assert "GCS_BUCKET" in 글, "이게 없으면 꺼질 때마다 DB 가 날아간다"
    # 비밀을 명령줄에 적으라고 하면 셸 기록에 남는다.
    assert "--set-secrets" in 글


def test_storage_library_is_declared():
    글 = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "google-cloud-storage" in 글


# ------------------------------------------------------------ 매일 맞추기
def test_pages_workflow_runs_every_evening():
    """회사에서 고친 것이 하루 한 번은 웹주소에 반영되어야 한다."""
    글 = yaml.safe_load((ROOT / ".github" / "workflows" / "pages.yml")
                        .read_text(encoding="utf-8"))
    # PyYAML 은 `on:` 을 참(True)으로 읽는다.
    조건 = 글.get("on") or 글.get(True)
    예약 = 조건["schedule"]
    assert 예약, "시각 예약이 없습니다"
    분, 시 = 예약[0]["cron"].split()[:2]
    assert 분 == "0" and 시 == "11", "11:00 UTC = 한국 20:00"


def test_one_command_script_exists_and_asks_only_for_the_code():
    """콘솔을 처음 쓰시는 분이 지역·버킷을 직접 찾게 하면 안 된다.

    "maim 이 어느 지역에 있는지" 를 물었더니 무슨 말인지 모르겠다고 하셨다.
    맞는 반응이다 — 그건 내가 찾아야 하는 것이지 사장님이 찾을 것이 아니다.
    """
    글 = (ROOT / "deploy" / "올리기.sh").read_text(encoding="utf-8")
    # 지역과 버킷을 스스로 찾는다
    assert "gcloud run services list" in 글, "지역을 스스로 찾아야 한다"
    assert "gcloud storage buckets list" in 글, "버킷을 스스로 찾아야 한다"
    # 접속 코드는 화면에 안 보이게 받는다
    assert "read -rs" in 글, "접속 코드가 화면에 보이면 안 된다"
    assert "--data-file=-" in 글, "명령줄에 적으면 셸 기록에 남는다"
    # 요금이 갈리는 값
    assert "--min-instances 0" in 글
    # 여러 번 돌려도 되어야 한다
    assert "gcloud secrets describe" in 글, "이미 있으면 넘어가야 한다"


def test_the_guide_leads_with_the_script():
    """긴 설명 앞에 **한 줄로 끝내는 법**이 먼저 나와야 한다."""
    글 = (ROOT / "deploy" / "cloudrun.md").read_text(encoding="utf-8")
    첫머리 = 글[:600]
    assert "deploy/올리기.sh" in 첫머리
    assert "Cloud Shell" in 첫머리


def test_script_uses_ascii_variable_names():
    """**bash 는 변수 이름에 한글을 못 쓴다.**

    파이썬·자바스크립트에서는 되길래 그대로 썼다가 첫 줄에서 멎었다
    (`서비스=cash-flow: command not found`). 이름만 영문으로 두고 설명은
    한글로 둔다. 다시 한글 이름을 쓰면 여기서 걸린다.
    """
    import re

    글 = (ROOT / "deploy" / "올리기.sh").read_text(encoding="utf-8")
    나쁜줄 = []
    for 번호, 줄 in enumerate(글.split("\n"), 1):
        벗긴줄 = 줄.split("#", 1)[0]          # 주석은 한글이어도 된다
        if re.search(r"(^|\s)[가-힣][가-힣\w]*=", 벗긴줄):
            나쁜줄.append(f"{번호}: {줄.strip()}")
        if re.search(r"(read\s+-\w+|unset)\s+[가-힣]", 벗긴줄):
            나쁜줄.append(f"{번호}: {줄.strip()}")
        if re.search(r"\$\{?#?[가-힣]", 벗긴줄):
            나쁜줄.append(f"{번호}: {줄.strip()}")
    assert not 나쁜줄, "bash 가 못 읽는 한글 변수 이름:\n" + "\n".join(나쁜줄)


def test_script_parses_as_bash():
    """붙여 넣었을 때 문법 오류로 멎으면 안 된다."""
    import subprocess

    done = subprocess.run(["bash", "-n", str(ROOT / "deploy" / "올리기.sh")],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def test_script_grants_secret_access_before_deploying():
    """비밀을 **넣는 것**과 **읽을 권한을 주는 것**은 다른 일이다.

    안 주면 빌드까지 다 끝난 뒤 마지막 단계에서 배포가 실패한다.
    실제로 거기서 한 번 멎었다 —
      Permission denied on secret: .../dashboard-access-code/versions/latest
      The service account used must be granted the 'Secret Manager Secret Accessor'
    """
    글 = (ROOT / "deploy" / "올리기.sh").read_text(encoding="utf-8")
    assert "secrets add-iam-policy-binding" in 글
    assert "roles/secretmanager.secretAccessor" in 글
    # 프로젝트 **번호**는 이름과 다르다. 번호로 계정 이름을 만든다.
    assert "value(projectNumber)" in 글
    assert "compute@developer.gserviceaccount.com" in 글
    # 권한을 준 **뒤에** 올려야 한다.
    assert 글.index("add-iam-policy-binding") < 글.index("gcloud run deploy")


# ------------------------------------------------- 웹에서 고친 파일 보관
def test_edits_are_kept_too_not_just_the_db():
    """수정 탭에서 고친 파일도 남아야 한다.

    컨테이너가 접히면 디스크가 처음으로 돌아간다. DB 만 맞춰 두면 **고친
    파일이 몇 시간 뒤 조용히 사라진다.** 저장은 됐는데 원래대로 돌아가
    있으면 고장인지 아닌지도 알 수 없다.
    """
    assert hasattr(gcsstate, "save_edit")
    assert hasattr(gcsstate, "restore_edits")
    assert hasattr(gcsstate, "drop_edit")


def test_restore_edits_only_touches_declared_files():
    """버킷에 엉뚱한 이름이 들어와도 아무 파일이나 덮으면 안 된다."""
    글 = (ROOT / "core" / "gcsstate.py").read_text(encoding="utf-8")
    몸통 = 글[글.index("def restore_edits"):]
    assert "editable_files" in 몸통, "선언된 편집 대상만 건드려야 한다"
    assert "if relative not in" in 몸통, "목록에 없으면 건너뛰어야 한다"


def test_saving_uploads_right_away():
    """60초를 기다리면 안 된다. 고친 직후에 접히면 통째로 없어진다."""
    글 = (ROOT / "dashboard" / "app.py").read_text(encoding="utf-8")
    저장 = 글[글.index("def file_save"):글.index("def file_revert")]
    assert "gcsstate.save_edit" in 저장


def test_the_screen_says_which_version_this_is():
    """«웹에서 고친 판이 저장소 판을 이긴다» 를 화면이 말해야 한다.

    안 그러면 저장소에서 고치고 재배포했는데 안 바뀌는 이유를 알 수 없다.
    """
    글 = (ROOT / "dashboard" / "templates" / "file_edit.html").read_text(encoding="utf-8")
    assert "웹에서 고친 판" in 글
    assert "이깁니다" in 글, "어느 쪽이 이기는지 말해야 한다"
    assert "원래대로 되돌리기" in 글, "되돌리는 길이 있어야 한다"
    assert "data-twice" in 글, "되돌리기는 두 번 눌러야 한다"


def test_revert_also_checks_the_file_is_editable(client_free=None):
    """되돌리기도 편집 대상인지 확인해야 한다. 저장만 막으면 반쪽이다."""
    글 = (ROOT / "dashboard" / "app.py").read_text(encoding="utf-8")
    되돌리기 = 글[글.index("def file_revert"):글.index("def file_revert") + 900]
    assert "editable_files" in 되돌리기


def test_낡은_폴더로_올리면_먼저_말린다():
    """한 번 데였다.

    저장소에는 고친 코드가 올라가 있는데 Cloud Run 에는 옛 판이 돌고 있었다.
    고객에게 나가는 메일이 옛 모양 그대로였고, 사장님은 "왜 수정이 안 되었지"
    하셨다. 스크립트가 아무리 잘 돌아도 **폴더가 낡았으면 옛 코드를 올린다.**
    """
    글 = Path("deploy/올리기.sh").read_text(encoding="utf-8")
    assert "git fetch" in 글, "저장소와 견주지 않습니다"
    assert "rev-list --count" in 글, "얼마나 뒤처졌는지 안 셉니다"
    assert "git pull" in 글, "무엇을 하라는 말이 없습니다"
    # 말리기만 하고 그냥 진행하면 뜻이 없다. 사람 대답을 받아야 한다.
    자리 = 글[글.index("뒤처져"):글.index("뒤처져") + 700]
    assert "read -r" in 자리, "묻지 않고 그냥 올립니다"
    assert "exit 1" in 자리, "아니라고 해도 멈추지 않습니다"


def test_배포_안내서가_코드도_다시_올리라고_말한다():
    """환경변수만 고치는 것과 코드를 다시 올리는 것은 다르다.

    `gcloud run services update` 는 환경변수만 바꾼다. 코드를 고쳤으면
    `deploy` 를 다시 해야 하는데, 그 둘을 헷갈리면 "고쳤는데 그대로"가 된다.
    """
    글 = Path("deploy/cloudrun.md").read_text(encoding="utf-8")
    assert "services update" in 글 and "run deploy" in 글, (
        "환경변수만 바꾸는 길과 코드를 올리는 길을 나눠 적지 않았습니다")
