"""노션 템플릿 기획·설명서 생성기 CLI.

    python cli.py plan "프리랜서 프로젝트 관리" --audience "1인 디자이너"
    python cli.py plan "..." --dry-run          # Claude 없이 예시 설계로
    python cli.py deploy outputs/<slug>/spec.yaml
    python cli.py check outputs/<slug>/spec.yaml   # 설계만 다시 검사

`deploy` 는 토큰이 없으면 **오류가 아니라 안내**하고 끝납니다(종료 코드 0).
손으로 만드는 길(build_guide.md)이 늘 있기 때문입니다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from notion_kit.deploy import (                                    # noqa: E402
    NotionError, NotionNotConfigured, deploy as run_deploy, notion_config,
    write_deploy_log,
)
from notion_kit.generator import TemplateGenerator                 # noqa: E402
from notion_kit.notion_types import MANUAL_ONLY                    # noqa: E402
from notion_kit.schema import TemplateSpec                         # noqa: E402
from notion_kit.writers import (                                   # noqa: E402
    OUTPUT_FILES, estimate_minutes, write_outputs,
)
from shared.config import DEFAULT_MODEL                            # noqa: E402
from shared.llm import LLMError                                    # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = BASE_DIR / "outputs"


def load_spec(path: Path) -> TemplateSpec:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"설계 파일이 없습니다: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    try:
        return TemplateSpec(**data)
    except ValidationError as exc:
        lines = [f"  - {' → '.join(str(p) for p in item['loc'])}: {item['msg']}"
                 for item in exc.errors()[:10]]
        raise ValueError(f"{path.name} 이 규격에 맞지 않습니다:\n" + "\n".join(lines)) from exc


def _summary(spec: TemplateSpec) -> None:
    times = estimate_minutes(spec)
    manual = [(db.name, prop.name) for db in spec.databases
              for prop in db.properties if prop.type in MANUAL_ONLY]
    views = sum(len(db.views) for db in spec.databases)

    print(f"  {spec.icon} {spec.name}")
    print(f"     페이지 {sum(1 for p in spec.pages for _ in p.walk())}개"
          f" · 데이터베이스 {len(spec.databases)}개"
          f" · 뷰 {views}개"
          f" · 버튼 {len(spec.buttons)}개")
    print(f"     연결(관계·롤업) {len(spec.relation_properties())}개"
          f" · 예시 {sum(len(db.sample_rows) for db in spec.databases)}행")
    print(f"     손으로 만들면 약 {times['합계'] / 60:.1f}시간")
    if manual:
        pairs = ", ".join(f"{db}.{name}" for db, name in manual[:4])
        print(f"     ⚠ API 로 못 만드는 속성 {len(manual)}개: {pairs}")


def read_request(path: Path) -> tuple[str, str]:
    """주제·타깃을 적어 둔 작은 YAML 을 읽는다.

    대시보드 '테스트' 탭은 명령줄 대신 파일 하나를 고쳐 실행하는 구조라
    주제를 파일로도 받을 수 있게 열어 둔다.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"요청 파일이 없습니다: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} 은 'topic:' 과 'audience:' 두 줄이어야 합니다")
    topic = str(data.get("topic") or "").strip()
    if not topic:
        raise ValueError(f"{path.name} 에 topic 이 비어 있습니다")
    audience = str(data.get("audience") or "1인 사업자").strip()
    return topic, audience


# --------------------------------------------------------------------- plan
def cmd_plan(args: argparse.Namespace) -> int:
    if args.request_file:
        args.topic, args.audience = read_request(Path(args.request_file))
    if not args.topic:
        raise ValueError('주제를 주세요. 예: python cli.py plan "프리랜서 프로젝트 관리"')

    if args.dry_run:
        from notion_kit.sample_content import fake_ask

        generator = TemplateGenerator("dry-run", fake_ask)
        print("모의 실행 — Claude 를 부르지 않습니다 (비용 없음)")
    else:
        generator = TemplateGenerator(args.model)
        print(f"모델 {args.model} 로 설계합니다. 호출 3회, 1~2분 걸립니다.")
    print()

    print("[1/3] 구조 설계")
    spec = generator.build_spec(args.topic, args.audience)
    _summary(spec)

    print("\n[2/3] 판매 문구")
    sales = generator.build_sales(spec)
    print(f"  제목 {len(sales.get('titles', []))}안 · "
          f"가격 {len(sales.get('pricing', []))}안")

    print("\n[3/3] 구매자용 문서")
    extras = generator.build_extras(spec)
    print(f"  자주 하는 실수 {len(extras.get('mistakes', []))}개 · "
          f"파생 템플릿 {len(extras.get('variants', []))}개")

    out_dir, dirty = write_outputs(spec, sales, extras, Path(args.out),
                                   ai_label=not args.no_ai_label)

    print()
    for name in OUTPUT_FILES:
        path = out_dir / name
        mark = "✓" if path.is_file() else "✗"
        size = f"{path.stat().st_size:,}B" if path.is_file() else "없음"
        print(f"  {mark} {name:18} {size:>10}")
    print(f"  → {out_dir}")

    for warning in generator.warnings:
        print(f"  ! {warning}")
    if dirty:
        print(f"  ⚠ 판매 문구에 쓰면 안 되는 표현 {len(dirty)}개: {', '.join(dirty)}")
        print("    sales_page.md 의 '등록 전 점검' 을 보고 고치세요")

    print()
    print("다음 순서")
    print(f"  1. {out_dir.name}/spec.yaml 을 읽고 구조가 말이 되는지 보세요")
    print(f"  2. build_guide.md 를 보며 노션에서 만드세요")
    print(f"     (또는 python cli.py deploy \"{out_dir / 'spec.yaml'}\")")
    print(f"  3. preview_brief.md 대로 화면을 찍으세요")
    if args.dry_run:
        print("\n※ 모의 실행 결과입니다. 설계와 문구는 예시입니다.")

    return 2 if (dirty or generator.warnings) else 0


# ------------------------------------------------------------------- check
def cmd_check(args: argparse.Namespace) -> int:
    spec = load_spec(Path(args.spec))
    print("설계가 규격에 맞습니다.")
    print()
    _summary(spec)
    return 0


# ------------------------------------------------------------------ deploy
def cmd_deploy(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec)
    spec = load_spec(spec_path)

    try:
        token, parent = notion_config()
    except NotionNotConfigured as exc:
        # 오류가 아니다. 이 기능은 없어도 되는 것이다.
        print(exc)
        return 0

    print(f"노션에 만듭니다: {spec.name}")
    print(f"  부모 페이지 {parent[:8]}…")
    print("  단계: 페이지 → 데이터베이스 → 관계 → 롤업 → 예시 데이터")
    print()

    report = run_deploy(spec, token, parent)

    for step in report.steps:
        mark = {"ok": "✓", "skipped": "·", "failed": "✗"}.get(step.status, "?")
        print(f"  {mark} [{step.kind}] {step.name}"
              + (f" — {step.detail.splitlines()[0][:70]}" if step.detail else ""))

    log_path = write_deploy_log(report, spec_path.parent / "deploy_log.md")
    print()
    print(f"  만든 것 {report.made}개 · 기록 → {log_path}")

    if report.manual_todo:
        print()
        print("  손으로 해야 하는 것")
        for item in report.manual_todo:
            print(f"    · {item.splitlines()[0][:76]}")

    if not report.ok:
        print()
        print(f"  ✗ '{report.failed_at}' 에서 멈췄습니다.")
        print("    노션에 절반쯤 만들어진 것이 남아 있습니다.")
        print("    다시 하시기 전에 만들어진 페이지를 지우세요. 안 그러면 두 벌이 생깁니다.")
        return 2

    return 0


# ------------------------------------------------------------------ 진입점
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="노션 템플릿 구조 설계와 판매·사용 문서를 만듭니다",
    )
    subparsers = parser.add_subparsers(dest="command")

    plan = subparsers.add_parser("plan", help="설계와 문서 6종을 만듭니다")
    plan.add_argument("topic", nargs="?", default="",
                      help='주제. 예: "프리랜서 프로젝트 관리"')
    plan.add_argument("--audience", default="1인 사업자",
                      help='타깃. 좁을수록 좋습니다. 예: "1인 디자이너"')
    plan.add_argument("--request-file", default="",
                      help="주제·타깃을 적어 둔 YAML. topic 자리 대신 씁니다")
    plan.add_argument("--dry-run", action="store_true",
                      help="Claude 를 부르지 않고 예시 설계로 만듭니다")
    plan.add_argument("--model", default=DEFAULT_MODEL, help=f"기본: {DEFAULT_MODEL}")
    plan.add_argument("--no-ai-label", action="store_true", help="AI 생성물 표시를 끕니다")
    plan.add_argument("--out", default=str(DEFAULT_OUT), help="산출물 상위 폴더")
    plan.set_defaults(func=cmd_plan)

    check = subparsers.add_parser("check", help="설계 파일만 다시 검사합니다")
    check.add_argument("spec", help="spec.yaml 경로")
    check.set_defaults(func=cmd_check)

    deploy = subparsers.add_parser("deploy", help="노션에 실제로 만듭니다 (선택)")
    deploy.add_argument("spec", help="spec.yaml 경로")
    deploy.set_defaults(func=cmd_deploy)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        print('\n예: python cli.py plan "프리랜서 프로젝트 관리" --audience "1인 디자이너"',
              file=sys.stderr)
        return 1

    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"파일을 찾지 못했습니다: {exc}", file=sys.stderr)
    except NotionError as exc:
        print(f"노션이 요청을 거절했습니다:\n{exc}", file=sys.stderr)
    except LLMError as exc:
        print(f"생성 실패: {exc}", file=sys.stderr)
    except ValueError as exc:
        print(f"오류: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
