"""**번호로 프로그램 하나만 다루기** — 통합 대시보드 안 1~16번의 자산 목록·범위·시험·경계 검사.

사장님이 «3번 수정» 처럼 번호를 말하면, 그 번호의 파일만 고치고 그 번호의 시험만 돌리고,
다른 번호를 건드리지 않았는지 커밋 전에 확인한다. 번호·이름·폴더는 각 `products/*/program.yaml`
(`number`·`id`·`name`)에서 읽으므로 따로 고칠 표가 없다.

    python -m tools.programs list            # 1~16 한눈에
    python -m tools.programs scope 3         # 3번이 고쳐도 되는 곳 / 묻고 고칠 곳 / 다시 만들 것
    python -m tools.programs test 3          # 3번 시험만 (자기 시험 + 공용 시험 중 3번 몫 + 점검 dry-run)
    python -m tools.programs guard 3         # 지금 바뀐 파일 중 3번 범위 밖이 있으면 알리고 1 로 끝남
    python -m tools.programs doc             # PROGRAMS.md 다시 만들기
"""
from __future__ import annotations

import glob
import subprocess
import sys
from pathlib import Path

import yaml

뿌리 = Path(__file__).resolve().parent.parent

# 번호별 «자기 시험» 파일과, 공용 시험(test_webui_products.py)에서 그 번호 몫을 고르는 낱말.
자기시험 = {
    "exam-drill": (["test_exam_drill.py"], "exam"),
    "senior-video": (["test_senior_video.py"], "senior"),
    "naver-blog": (["test_naver_blog.py", "test_naver_blog_live.py"], "naver"),
    "speaker-desk": (["test_speaker_desk.py"], "speaker"),
    "funnel-builder": (["test_funnel.py"], "funnel"),
    "hook-script": (["test_hook_script.py"], "hook"),
    "ebook-gen": (["test_ebook.py"], "ebook"),
    "lecture-deck": (["test_lecture_deck.py"], "lecture"),
    "kmong-copy": (["test_kmong_copy.py"], "kmong"),
    "n8n-gen": (["test_n8n_gen.py"], "n8n"),
    "groupbuy-ledger": (["test_groupbuy.py"], "groupbuy"),
    "income-sim": (["test_income_sim.py"], "income"),
    "notion-template-kit": (["test_notion_kit.py"], "notion"),
    "affiliate-matcher": (["test_affiliate_matcher.py"], "affiliate"),
    "agency-kit": (["test_agency_kit.py"], "agency"),
    "niche-research": (["test_niche_research.py"], "niche"),
}

# 본체가 이 저장소 밖에 있는 번호. 그 저장소에서 따로 고치고 시험한다.
바깥 = {
    "exam-drill": {
        "저장소": "parkchihong7-gif/gongin-jungsagsa-exam (GitHub Pages)",
        "시험": "그 저장소를 세션에 붙인 뒤(add_repo) 확인 — 이 저장소에는 판매 문서·점검(check.py)만 있다",
    },
    "naver-blog": {
        "저장소": "parkchihong7-gif/maim (Cloud Run) · 브랜치 claude/great-brown-j376u0",
        "시험": "cd <maim> && npm run build && for f in tests/*.ts; do npx tsx $f; done",
        "배포": "cd ~/maim && git pull && gcloud run deploy maim --source . --region=us-central1 "
                "--allow-unauthenticated --concurrency=80  (사장님이 Cloud Shell 에서)",
    },
}

# 등록부에서 **다시 만드는** 파일 — 손으로 고치지 않는다.
재생성 = {
    "web/programs.js": "python -m tools.gen_programs_js",
    "server/keyserver.bundle.gs": "python -m tools.build_keyserver",
}

# 여러 번호가 함께 쓰는 곳 — 번호 작업 중 여기를 고쳐야 하면 **먼저 사장님께 묻는다.**
공용 = ["core/", "dashboard/", "shared/", "server/", "web/", "deploy/", "tools/",
        "tests/conftest.py", "CLAUDE.md", "HANDOFF.md", "PROGRAMS.md", "README.md", "requirements.txt"]

# 번호와 상관없이 늘 바뀌어도 되는 것 (생성물·캐시)
무시 = ["__pycache__", ".pyc", "dashboard.db"]


def 등록부() -> list[dict]:
    목록 = []
    for f in glob.glob(str(뿌리 / "products/*/program.yaml")):
        d = yaml.safe_load(open(f, encoding="utf-8"))
        목록.append({"number": d["number"], "id": d["id"], "name": d["name"], "status": d.get("status", ""),
                   "live": bool(d.get("live")), "run": d.get("run") or {}})
    return sorted(목록, key=lambda x: x["number"])


def 찾기(번호: str) -> dict:
    for p in 등록부():
        if str(p["number"]) == str(번호).rstrip("번") or p["id"] == 번호:
            return p
    sys.exit(f"{번호}번 프로그램이 없습니다. `python -m tools.programs list` 로 확인하세요.")


def 공용속자리(pid: str) -> list[str]:
    """공용 파일 중 이 번호 이름이 직접 나오는 곳 (재생성 파일 제외). 고칠 땐 그 부분만."""
    낱말 = f"{pid}|{pid.replace('-', '_')}"
    out = subprocess.run(["git", "-c", "core.quotepath=off", "grep", "-lE", 낱말, "--", "core", "dashboard", "shared", "server", "web"],
                         cwd=뿌리, capture_output=True, text=True).stdout.split()
    return [f for f in out if f not in 재생성 and "/tests/" not in f and "나눠붙이기" not in f]


def 범위(p: dict) -> list[str]:
    파일, _ = 자기시험.get(p["id"], ([], ""))
    return [f"products/{p['id']}/"] + [f"tests/{t}" for t in 파일]


def scope(번호: str) -> None:
    p = 찾기(번호)
    print(f"■ {p['number']}번 {p['name']}  ({p['id']}, {p['status']})\n")
    print("고쳐도 되는 곳 (이 번호만):")
    for r in 범위(p):
        print(f"  - {r}")
    if p["id"] in 바깥:
        b = 바깥[p["id"]]
        print(f"\n본체는 밖에 있음: {b['저장소']}\n  시험: {b['시험']}")
        if "배포" in b:
            print(f"  배포: {b['배포']}")
    속 = 공용속자리(p["id"])
    print("\n공용 파일 중 이 번호가 직접 걸린 곳 (고칠 땐 이 번호 부분만, 보고에 적기):")
    print("".join(f"  - {f}\n" for f in 속) or "  (없음)\n")
    print("그 밖의 공용 파일 → 고쳐야 하면 먼저 묻는다:", ", ".join(공용))
    print("\n이 번호의 이름·설명·요금 등 program.yaml 을 바꿨으면 다시 만들 것:")
    for f, cmd in 재생성.items():
        print(f"  - {f}: {cmd}")


def test(번호: str) -> int:
    p = 찾기(번호)
    파일, 낱말 = 자기시험.get(p["id"], ([], p["id"]))
    결과 = 0
    있는것 = [f"tests/{t}" for t in 파일 if (뿌리 / "tests" / t).exists()]
    print(f"■ {p['number']}번 시험: {' '.join(있는것)} + test_webui_products.py -k {낱말}")
    결과 |= subprocess.run([sys.executable, "-m", "pytest", "-q", *있는것], cwd=뿌리).returncode
    공 = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests/test_webui_products.py", "-k", 낱말], cwd=뿌리).returncode
    결과 |= 0 if 공 in (0, 5) else 공          # 5 = 고를 것이 없음
    dry = p["run"].get("dry_run_command")
    입력 = p["run"].get("input_file") or ""
    if dry and any("{input}" in x for x in dry):
        dry = [x.replace("{input}", 입력) for x in dry] if 입력 else None
        if not 입력:
            print("■ 점검 dry-run: 입력 파일이 정해져 있지 않아 건너뜀")
    if dry:
        print(f"■ 점검 dry-run: {' '.join(dry)}")
        코드 = subprocess.run([sys.executable if dry[0] == "python" else dry[0], *dry[1:]],
                            cwd=뿌리 / "products" / p["id"]).returncode
        # 대시보드(core/runner.py)와 같게 읽는다 — 0 성공, 2 «주의»(결과는 나왔고 볼 것이 있음), 그 밖은 실패.
        if 코드 == 2:
            print("■ 점검 결과: 주의(종료 코드 2) — 결과물은 나왔고, 위 ⚠ 항목을 보라는 뜻입니다. 실패가 아닙니다.")
        else:
            결과 |= 코드
    if p["id"] in 바깥:
        print(f"■ 본체 시험은 밖에서: {바깥[p['id']]['시험']}")
    print("✅ 통과" if 결과 == 0 else "❌ 실패가 있습니다")
    return 결과


def guard(번호: str) -> int:
    p = 찾기(번호)
    바뀜 = subprocess.run(["git", "-c", "core.quotepath=off", "status", "--porcelain"], cwd=뿌리, capture_output=True, text=True).stdout
    파일들 = [줄[3:].strip().strip('"') for 줄 in 바뀜.splitlines() if 줄.strip()]
    파일들 = [f for f in 파일들 if not any(m in f for m in 무시)]
    안 = 범위(p)
    밖 = [f for f in 파일들 if not any(f.startswith(r) for r in 안) and f not in 재생성]
    print(f"■ {p['number']}번 경계 검사 — 바뀐 파일 {len(파일들)}개")
    for f in 파일들:
        표 = "  " if f not in 밖 else "⚠ "
        print(f"  {표}{f}")
    if 밖:
        print(f"\n⚠ {p['number']}번 범위 밖 {len(밖)}개 — 사장님께 확인받았거나 꼭 필요한 공용 수정인지 보고에 적으세요.")
        return 1
    print("✅ 범위 안만 바뀌었습니다")
    return 0


def 목록() -> None:
    for p in 등록부():
        밖 = " · 본체 밖" if p["id"] in 바깥 else ""
        print(f"{p['number']:>2}번  {p['name']}  ({p['id']}){밖}")


def doc() -> None:
    줄 = ["# 프로그램 번호표 (자동 생성 — 손으로 고치지 마세요)", "",
         "`python -m tools.programs doc` 이 각 `products/*/program.yaml` 에서 만듭니다.",
         "번호 작업 규칙은 CLAUDE.md 11장.", "",
         "| 번호 | 이름 | 폴더 | 자기 시험 | 본체 |", "|---|---|---|---|---|"]
    for p in 등록부():
        파일, _ = 자기시험.get(p["id"], ([], ""))
        본체 = 바깥[p["id"]]["저장소"].split(" ")[0] if p["id"] in 바깥 else "이 저장소"
        줄.append(f"| {p['number']} | {p['name']} | `products/{p['id']}/` | {', '.join(f'`{t}`' for t in 파일)} | {본체} |")
    줄 += ["", "## 공용 자산 (여러 번호가 함께 씀 — 번호 작업 중 고치려면 먼저 확인)", "",
          "| 무엇 | 어디 | 실행·시험 |", "|---|---|---|",
          "| 통합 관리자 대시보드 | `dashboard/` (FastAPI·템플릿) | `python -m dashboard` → http://127.0.0.1:8000 |",
          "| 공용 엔진 | `core/` (등록부·실행기·접속키·콘솔·메일 등) | `pytest tests/` |",
          "| 공용 도우미 | `shared/` (AI 표시·금지 문구·LLM) | `pytest tests/test_shared.py` |",
          "| 접속키 서버 (Apps Script) | `server/keyserver.gs`, `web/admin.html` | `node --test server/tests/keyserver.test.js` · `pytest tests/test_keyserver_web.py` |",
          "| 생성물 | `web/programs.js`, `server/keyserver.bundle.gs` | `python -m tools.gen_programs_js` · `python -m tools.build_keyserver` |",
          "| 대시보드 스냅샷 | `dashboard/snapshot.py` | `python -m dashboard.snapshot --demo --single` |",
          "| 교육자료 PPT | `tools/build_training_decks.js` 외 | README 참고 |",
          "| 배포 | `deploy/`, `Dockerfile`, `render.yaml` | `deploy/cloudrun.md` |",
          "| 검토 문서·화면 확인 | `tools/review_page.py`, `tools/ui_shot.py` | CLAUDE.md 10장 |",
          "| 전체 시험 | `tests/` | `python -m pytest -q` (오래 걸림 — 공용을 고쳤을 때만) |", ""]
    for pid, b in 바깥.items():
        p = 찾기(pid)
        줄.append(f"- **{p['number']}번 본체** — {b['저장소']}. 시험: `{b['시험']}`" + (f". 배포: `{b['배포']}`" if "배포" in b else ""))
    (뿌리 / "PROGRAMS.md").write_text("\n".join(줄) + "\n", encoding="utf-8")
    print("PROGRAMS.md 를 만들었습니다.")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "list":
        목록()
    elif a[0] == "scope" and len(a) > 1:
        scope(a[1])
    elif a[0] == "test" and len(a) > 1:
        sys.exit(test(a[1]))
    elif a[0] == "guard" and len(a) > 1:
        sys.exit(guard(a[1]))
    elif a[0] == "doc":
        doc()
    else:
        print(__doc__)
