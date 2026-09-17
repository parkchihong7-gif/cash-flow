"""자동화 대행 납품 키트 — 전체 진입점.

    python cli.py doctor                     세 모듈이 돌 준비가 됐는지 봅니다
    python cli.py demo --dry-run             세 모듈을 한 번씩 돌려 봅니다
    python cli.py package --client "가게 이름"  납품 패키지를 만듭니다

모듈은 각자 따로 돌릴 수 있습니다. 이 파일은 **한 번에 점검하고 납품물을
만드는** 자리입니다.

    kakao-faq-bot/   uvicorn app:get_app --factory
    sheet-report/    python run.py --csv sample_sales.csv
    insta-scheduler/ python manage.py list
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR.parents[1]))

MODULES = {
    "kakao": BASE_DIR / "kakao-faq-bot",
    "report": BASE_DIR / "sheet-report",
    "insta": BASE_DIR / "insta-scheduler",
}
DELIVERABLES = BASE_DIR / "deliverables"
DEFAULT_OUT = BASE_DIR / "outputs"

#: 납품 패키지에 들어가는 문서.
PACKAGE_FILES = (
    "INSTALL_GUIDE.md",
    "RETAINER_CONTRACT_TEMPLATE.md",
    "HANDOVER_CHECKLIST.md",
    "KMONG_LISTING.md",
    "AI_NOTICE.md",
)

#: 패키지 3단. 크몽 등록과 같은 구성이다.
PLANS = {
    "basic": ("BASIC", 550_000, ("kakao",), "챗봇만"),
    "standard": ("STANDARD", 880_000, ("kakao", "report"), "챗봇 + 보고서"),
    "premium": ("PREMIUM", 1_200_000, ("kakao", "report", "insta"), "3종 + 교육 2시간"),
}


def _mark(ok: bool) -> str:
    return "✓" if ok else "·"


# --------------------------------------------------------------------- doctor
def cmd_doctor(args: argparse.Namespace) -> int:
    """설치 상태를 본다. 납품 나가기 전에 한 번 돌려 보는 용도."""
    print("환경")
    api_key = bool(os.getenv("ANTHROPIC_API_KEY"))
    print(f"  {_mark(api_key)} ANTHROPIC_API_KEY — "
          + ("있습니다" if api_key else "없습니다 (모의 실행만 됩니다)"))

    for label, keys in (
        ("구글시트 (모듈 A·B)", ("GOOGLE_CREDENTIALS_JSON",)),
        ("카카오 FAQ 시트 (모듈 A)", ("SHEET_ID",)),
        ("인스타 (모듈 C)", ("IG_ACCESS_TOKEN", "IG_USER_ID")),
        ("슬랙·메일 (모듈 B, 선택)", ("SLACK_WEBHOOK_URL", "SMTP_HOST")),
    ):
        found = [key for key in keys if os.getenv(key)]
        print(f"  {_mark(bool(found))} {label} — "
              + (", ".join(found) if found else "없습니다"))

    print()
    print("라이브러리")
    problems = 0
    for module, why in (("fastapi", "모듈 A 서버"), ("pandas", "모듈 B 집계"),
                        ("docx", "모듈 B 워드"), ("apscheduler", "모듈 C 예약")):
        try:
            __import__(module)
            print(f"  ✓ {module:<12} {why}")
        except ImportError:
            problems += 1
            print(f"  ✗ {module:<12} {why} — pip install -r requirements.txt")

    print()
    print("파일")
    for name, path in MODULES.items():
        ok = path.is_dir()
        problems += 0 if ok else 1
        print(f"  {_mark(ok)} {path.name}")
    for name in PACKAGE_FILES:
        ok = (DELIVERABLES / name).is_file()
        problems += 0 if ok else 1
        print(f"  {_mark(ok)} deliverables/{name}")

    print()
    if problems:
        print(f"{problems}가지를 손봐야 합니다.")
        return 2
    print("세 모듈 모두 돌 준비가 됐습니다.")
    if not api_key:
        print("  실제 실행에는 ANTHROPIC_API_KEY 가 필요합니다. 지금은 모의 실행만 됩니다.")
    return 0


# ----------------------------------------------------------------------- demo
def _demo_kakao(out_dir: Path, dry_run: bool) -> dict:
    """스킬 서버에 오픈빌더 규격 요청을 넣어 본다."""
    sys.path.insert(0, str(MODULES["kakao"]))
    from fastapi.testclient import TestClient

    from app import create_app                                  # type: ignore
    from logs import LogStore                                   # type: ignore
    from sample_content import fake_ask                         # type: ignore

    store = LogStore(out_dir / "kakao_logs.db")
    client = TestClient(create_app(
        ask_fn=fake_ask if dry_run else None, store=store, model="demo"))

    questions = ["영업시간이 어떻게 되나요?", "주차 가능한가요?", "강아지 데려가도 되나요?"]
    transcript = []
    for question in questions:
        payload = {
            "userRequest": {"utterance": question, "user": {"id": "demo-user"}},
            "bot": {"id": "demo"}, "action": {"name": "faq"},
        }
        response = client.post("/skill", json=payload)
        body = response.json()
        transcript.append({
            "질문": question,
            "응답": body["template"]["outputs"][0]["simpleText"]["text"],
            "규격": body.get("version"),
        })

    health = client.get("/health").json()
    totals = store.totals()
    (out_dir / "kakao_demo.json").write_text(
        json.dumps({"대화": transcript, "health": health}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    return {
        "모듈": "A 카카오 FAQ 챗봇",
        "결과": f"{len(transcript)}건 응답 · 평균 {int(totals['avg_ms'] or 0)}ms"
                f" · 최대 {int(totals['max_ms'] or 0)}ms",
        "ok": int(totals["max_ms"] or 0) < 4000 and health["status"] == "ok",
        "파일": "kakao_demo.json",
    }


def _demo_report(out_dir: Path, dry_run: bool) -> dict:
    """샘플 매출 CSV 로 주간 보고서를 만든다."""
    sys.path.insert(0, str(MODULES["report"]))
    from aggregate import load_csv, summarize                   # type: ignore
    from run import _fake_narration                             # type: ignore
    from writers import write_all                               # type: ignore

    frame = load_csv(MODULES["report"] / "sample_sales.csv")
    aggregate = summarize(frame, period="week")

    if dry_run:
        narration = _fake_narration(aggregate)
    else:
        from narrate import narrate                             # type: ignore
        from shared.config import DEFAULT_MODEL
        from shared.llm import ask

        narration = narrate(aggregate, ask, DEFAULT_MODEL)

    md_path, docx_path = write_all(aggregate, narration, out_dir,
                                   title="주간 매출 보고서 (예시)", source="sample_sales.csv")
    return {
        "모듈": "B 주간 보고서",
        "결과": f"합계 {aggregate.total:,}원 · 직전 대비 {aggregate.delta:+,}원"
                f" · 숫자 확인 {'통과' if narration.verified else '실패'}",
        "ok": narration.verified,
        "파일": f"{md_path.name}, {docx_path.name}",
    }


def _demo_insta(out_dir: Path, dry_run: bool) -> dict:
    """큐에 넣고 → 승인 없이 발행되지 않는 것까지 확인한다."""
    sys.path.insert(0, str(MODULES["insta"]))
    from queue_store import QueueStore                          # type: ignore
    from scheduler import Runner                                # type: ignore

    store = QueueStore(out_dir / "insta_queue.db")
    store.add("2020-01-01 09:00", "https://example.com/demo.jpg",
              caption="예시 게시물입니다.", hashtags="#예시")

    runner = Runner(store=store, client=None, dry_run=True)
    before = runner.tick()                      # 승인 전 — 아무것도 안 나가야 한다
    blocked = not before.published

    store.approve(1, "데모 담당자")
    after = runner.tick()                       # 승인 후 — 모의 실행이라 올리진 않는다

    lines = [
        "# 인스타 예약 발행 — 승인 흐름 확인",
        "",
        "| 단계 | 결과 |",
        "|---|---|",
        f"| 승인 전 발행 시도 | {'막힘 ✓' if blocked else '나감 ✗'} |",
        f"| 승인 후 | {'모의 실행이라 올리지 않음' if after.skipped else '올림'} |",
        "",
        "승인 없이는 발행되지 않습니다. 이것이 이 모듈의 핵심 안전장치입니다.",
    ]
    (out_dir / "insta_demo.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "모듈": "C 인스타 예약 발행",
        "결과": ("승인 전 발행 막힘 확인" if blocked else "⚠ 승인 전에 발행되었습니다"),
        "ok": blocked,
        "파일": "insta_demo.md",
    }


def cmd_demo(args: argparse.Namespace) -> int:
    """세 모듈을 한 번씩 돌려 본다. 설치 직후와 시연에 쓴다."""
    out_dir = Path(args.out) / datetime.now().strftime("%Y%m%d-%H%M")
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        print("모의 실행 — Claude 를 부르지 않습니다 (비용 없음)")
    print()

    results = []
    for step, (label, runner) in enumerate([
        ("모듈 A — 카카오 FAQ 챗봇", _demo_kakao),
        ("모듈 B — 주간 보고서", _demo_report),
        ("모듈 C — 인스타 예약 발행", _demo_insta),
    ], start=1):
        print(f"[{step}/3] {label}")
        try:
            result = runner(out_dir, args.dry_run)
        except Exception as exc:
            print(f"  ✗ {type(exc).__name__}: {exc}")
            results.append({"모듈": label, "결과": f"실패 — {exc}", "ok": False, "파일": ""})
            continue
        print(f"  {'✓' if result['ok'] else '⚠'} {result['결과']}")
        if result["파일"]:
            print(f"     → {result['파일']}")
        results.append(result)

    summary = out_dir / "demo_summary.md"
    lines = ["# 세 모듈 점검 결과", "",
             f"- 실행: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
             f"- 방식: {'모의 실행 (Claude 안 부름)' if args.dry_run else '실제 실행'}", "",
             "| 모듈 | 결과 | 파일 |", "|---|---|---|"]
    for result in results:
        mark = "✓" if result["ok"] else "⚠"
        lines.append(f"| {mark} {result['모듈']} | {result['결과']} | {result['파일']} |")
    lines += ["", "납품 전에는 `deliverables/HANDOVER_CHECKLIST.md` 20항목을 "
              "고객과 함께 확인하세요."]
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print()
    print(f"  → {out_dir}")
    failed = [result for result in results if not result["ok"]]
    if failed:
        print(f"  ⚠ {len(failed)}개 모듈에서 확인할 것이 있습니다")
        return 2
    print("  세 모듈 모두 정상입니다.")
    return 0


# -------------------------------------------------------------------- package
def cmd_package(args: argparse.Namespace) -> int:
    """고객 이름을 채운 납품 패키지를 만든다."""
    plan = PLANS.get(args.plan)
    if plan is None:
        print(f"플랜은 {' / '.join(PLANS)} 중 하나입니다.", file=sys.stderr)
        return 1
    name, price, modules, description = plan

    slug = re.sub(r"[^0-9A-Za-z가-힣]+", "-", args.client).strip("-") or "고객사"
    out_dir = Path(args.out) / f"{slug}-{name.lower()}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) 문서 복사 — 고객 이름과 날짜를 채운다
    today = datetime.now().strftime("%Y년 %m월 %d일")
    copied = []
    for filename in PACKAGE_FILES:
        source = DELIVERABLES / filename
        if not source.is_file():
            print(f"  ✗ {filename} 이 없습니다", file=sys.stderr)
            continue
        text = source.read_text(encoding="utf-8")
        # 자리가 정해진 것부터 채운다. 먼저 뭉뚱그려 바꾸면 엉뚱한 칸이 채워진다.
        text = text.replace("고객 상호: [                    ]", f"고객 상호: {args.client}")
        text = text.replace("납품일: [    년   월   일]", f"납품일: {today}")
        text = text.replace("**고객** (이하 \"갑\")\n상호: [                    ]",
                            f"**고객** (이하 \"갑\")\n상호: {args.client}")
        (out_dir / filename).write_text(text, encoding="utf-8")
        copied.append(filename)

    # 2) 모듈 폴더 복사 (.env·기록·산출물은 빼고)
    for key in modules:
        source = MODULES[key]
        target = out_dir / source.name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target, ignore=shutil.ignore_patterns(
            ".env", "*.db", "__pycache__", "outputs", ".token*", "credentials.json"))

    # 3) 안내문
    lines = [
        f"# {args.client} 납품 패키지",
        "",
        f"- 패키지: **{name}** ({description}) · {price:,}원",
        f"- 만든 날: {today}",
        f"- 들어 있는 모듈: {', '.join(MODULES[key].name for key in modules)}",
        "",
        "## 순서",
        "",
        "1. `INSTALL_GUIDE.md` 0장(공통 준비)부터 보세요",
        "2. 모듈 하나를 끝내고 며칠 써 보신 뒤 다음 것을 하세요",
        "3. 다 끝나면 `HANDOVER_CHECKLIST.md` 20항목을 함께 확인합니다",
        "",
        "## 들어 있지 않은 것",
        "",
        "- `.env` 파일 — 키는 **고객사 계정으로** 발급해 직접 넣으십니다",
        "- 서비스 계정 키(`credentials.json`)",
        "- 지난 기록(`*.db`)과 이전 산출물",
        "",
        "이 도구는 반복 업무에 드는 시간을 줄이기 위한 것이며, "
        "매출이나 문의 증가를 약속하지 않습니다.",
    ]
    (out_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"{name} 패키지를 만들었습니다 — {args.client}")
    print(f"  문서 {len(copied)}종 · 모듈 {len(modules)}개")
    print(f"  → {out_dir}")

    if args.zip:
        archive = shutil.make_archive(str(out_dir), "zip", str(out_dir))
        print(f"  압축 → {archive}")

    print()
    print("보내기 전에 확인하세요")
    print("  1. .env 나 credentials.json 이 안 들어갔는지 (넣으면 안 됩니다)")
    print("  2. 계약서의 [   ] 자리를 채웠는지")
    print("  3. 점검표 20항목을 고객과 함께 볼 시간을 잡았는지")
    return 0


# ------------------------------------------------------------------- 진입점
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py", description="자동화 대행 납품 키트 — 점검·시연·납품")
    subparsers = parser.add_subparsers(dest="command")

    doctor = subparsers.add_parser("doctor", help="돌 준비가 됐는지 봅니다")
    doctor.set_defaults(func=cmd_doctor)

    demo = subparsers.add_parser("demo", help="세 모듈을 한 번씩 돌려 봅니다")
    demo.add_argument("--dry-run", action="store_true", help="Claude 를 부르지 않습니다")
    demo.add_argument("--out", default=str(DEFAULT_OUT))
    demo.set_defaults(func=cmd_demo)

    package = subparsers.add_parser("package", help="납품 패키지를 만듭니다")
    package.add_argument("--client", required=True, help="고객사 이름")
    package.add_argument("--plan", default="premium", choices=sorted(PLANS))
    package.add_argument("--out", default=str(DEFAULT_OUT))
    package.add_argument("--zip", action="store_true")
    package.set_defaults(func=cmd_package)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        print("\n예: python cli.py demo --dry-run", file=sys.stderr)
        return 1
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"파일을 찾지 못했습니다: {exc}", file=sys.stderr)
    except ValueError as exc:
        print(f"오류: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
