"""퍼널 빌더 CLI.

    python cli.py build funnel_input.yaml
    python cli.py build funnel_input.yaml --platform kmong
    python cli.py build funnel_input.yaml --platform instagram
    python cli.py serve outputs/<slug>            # 브라우저로 미리 보기

입력 YAML 하나로 `outputs/<slug>/` 에 산출물을 만든다.

**어디에 올릴 것인가**에 따라 첫 화면이 달라진다(`--platform`).

    own(기본)   landing.html                    내 도메인에 올린다
    kmong       detail_page.md                  크몽은 HTML 을 못 올린다
    instagram   reels_captions.md + dm_flow.yaml

이메일 5통·리드매그넷 목차·카피 변형·빌드 리포트는 어느 쪽이든 똑같이 나온다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from funnel_builder.generator import FunnelGenerator, write_outputs  # noqa: E402
from funnel_builder.platforms import PLATFORMS, platform_files  # noqa: E402
from funnel_builder.schema import load_input  # noqa: E402

from shared.config import DEFAULT_MODEL  # noqa: E402
from shared.llm import LLMError  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = BASE_DIR / "outputs"

#: `--serve` 가 쓰는 포트.
DEFAULT_PORT = 8000

#: 미리보기에서 첫 화면으로 열 파일. 플랫폼마다 다르다.
PREVIEW_FILES = ("landing.html", "detail_page.md", "reels_captions.md")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="강의·전자책 판매 퍼널 생성기 (랜딩 + 이메일 5통 + 리드매그넷 목차)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="YAML 입력으로 퍼널 산출물을 만든다")
    build.add_argument("input", help="입력 YAML 경로 (예: funnel_input.yaml)")
    build.add_argument(
        "--model", default=DEFAULT_MODEL, help=f"Claude 모델 ID (기본: {DEFAULT_MODEL})"
    )
    build.add_argument(
        "--no-ai-label",
        action="store_true",
        help="AI 생성물 표시를 끈다. 인공지능기본법 표시 의무를 직접 처리할 때만 쓴다.",
    )
    build.add_argument(
        "--out", default=str(DEFAULT_OUT), help=f"산출물 상위 폴더 (기본: {DEFAULT_OUT})"
    )
    build.add_argument(
        "--dry-run",
        action="store_true",
        help="Claude 를 부르지 않고 예시 콘텐츠로 산출물 형태만 만든다 (API 비용 없음)",
    )
    build.add_argument(
        "--platform", default="own", choices=list(PLATFORMS),
        help="어디에 올릴 것인가. own=랜딩 html / kmong=상세페이지 md / "
             "instagram=릴스 캡션 + DM 흐름 (기본: own)",
    )
    build.add_argument(
        "--serve", action="store_true",
        help="만든 뒤 바로 브라우저로 볼 수 있게 8000 포트로 띄운다 (own 전용)",
    )
    build.add_argument("--port", type=int, default=DEFAULT_PORT,
                       help=f"--serve 포트 (기본: {DEFAULT_PORT})")

    serve = sub.add_parser("serve", help="이미 만든 산출물을 브라우저로 본다")
    serve.add_argument("path", nargs="?", default="",
                       help="볼 폴더. 비우면 가장 최근에 만든 것")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument("--no-open", action="store_true", help="브라우저를 열지 않는다")
    serve.set_defaults(func=cmd_serve)
    return parser


def latest_output(root: Path) -> Path | None:
    """가장 최근에 만든 산출물 폴더. `serve` 를 인자 없이 쓸 때 찾는다."""
    if not root.is_dir():
        return None
    folders = [path for path in root.iterdir() if path.is_dir()]
    if not folders:
        return None
    return max(folders, key=lambda path: path.stat().st_mtime)


def make_server(folder: Path, port: int = DEFAULT_PORT):
    """폴더 하나만 보여 주는 서버를 만든다. `(서버, 주소, 첫 파일)` 을 돌려준다.

    **그 폴더 밖은 보이지 않는다.** `SimpleHTTPRequestHandler` 에 `directory` 를
    주면 위로 못 올라간다. 산출물에는 고객 이름이 들어갈 수 있어서, 실수로
    상위 폴더가 통째로 열리는 일은 막아야 한다.

    포트가 이미 쓰이고 있으면 다음 포트로 옮겨 간다. 띄우는 것과 도는 것을
    나눠 둔 이유는, 테스트가 **실제로 뜬 포트**를 알아야 하기 때문이다.
    """
    import functools
    import http.server
    import socketserver

    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(folder))

    for offset in range(10):                      # 8000 이 막혀 있으면 8001, 8002…
        try:
            httpd = socketserver.TCPServer(("127.0.0.1", port + offset), handler)
        except OSError:
            continue
        opened = port + offset
        first = next((name for name in PREVIEW_FILES if (folder / name).is_file()), "")
        return httpd, f"http://127.0.0.1:{opened}/" + first, first

    raise OSError(f"{port}~{port + 9} 포트가 모두 쓰이고 있습니다")


def serve_folder(folder: Path, port: int = DEFAULT_PORT, open_browser: bool = True,
                 forever: bool = True) -> str:
    """폴더를 띄우고 주소를 알려 준다. `forever` 면 Ctrl+C 까지 돈다."""
    import webbrowser

    httpd, url, first = make_server(folder, port)

    print(f"  미리보기 → {url}")
    print(f"  폴더: {folder}")
    print("  멈추려면 Ctrl+C")
    if not first:
        print("  ! 첫 화면으로 열 파일이 없습니다. 폴더 목록이 보입니다")
    elif first != "landing.html":
        print(f"  · 이 플랫폼에는 landing.html 이 없어 {first} 를 엽니다"
              " (마크다운은 글자 그대로 보입니다)")

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass                                   # 브라우저가 없는 환경도 있다

    if forever:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  멈췄습니다.")
        finally:
            httpd.server_close()
    else:
        httpd.server_close()
    return url


def cmd_serve(args: argparse.Namespace) -> int:
    folder = Path(args.path) if args.path else latest_output(DEFAULT_OUT)
    if folder is None:
        print("아직 만든 산출물이 없습니다. 먼저 build 를 돌리세요.", file=sys.stderr)
        return 1
    if not folder.is_dir():
        print(f"폴더가 없습니다: {folder}", file=sys.stderr)
        return 1

    serve_folder(folder, port=args.port, open_browser=not args.no_open)
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    data = load_input(args.input)
    print(f"[1/3] 입력 확인: {data.product_name} ({data.price_text})")
    if not data.proof:
        print("      proof 가 비어 있어 랜딩의 증거 섹션은 생성하지 않습니다.")

    if args.dry_run:
        from funnel_builder.sample_content import fake_ask

        print("[2/3] 모의 실행 — Claude 를 부르지 않고 예시 콘텐츠로 만듭니다 (비용 없음)")
        generator = FunnelGenerator(
            data, model="dry-run", ask_fn=fake_ask, ai_label=not args.no_ai_label,
            platform=args.platform,
        )
    else:
        tail = " → 릴스 캡션" if args.platform == "instagram" else ""
        print(f"[2/3] 섹션 생성 중 (모델 {args.model}) — "
              f"헤드라인 → 본문 → FAQ → 목차 → 이메일{tail}")
        generator = FunnelGenerator(data, model=args.model,
                                    ai_label=not args.no_ai_label,
                                    platform=args.platform)
    result = generator.build()

    out_dir = write_outputs(result, Path(args.out))
    made = list(platform_files[args.platform]) + [
        "emails/", "lead_magnet_outline.md", "copy_variants.json", "build_report.md"]
    print(f"[3/3] 산출물 {len(made)}종을 만들었습니다 (플랫폼: {args.platform}): {out_dir}")
    for name in made:
        print(f"      - {name}")

    if args.platform == "kmong":
        print("\n크몽은 HTML 을 못 올립니다. detail_page.md 의 글을 상세페이지 "
              "편집기에 옮겨 적으세요.")
    elif args.platform == "instagram":
        print("\ndm_flow.yaml 은 ManyChat·포크레터 같은 **공식 도구**에 넣으세요.")
        print("먼저 댓글을 남긴 사람에게만, 24시간 안에만 보낼 수 있습니다.")

    if result.warnings:
        names = ", ".join(section.name for section in result.warnings)
        print(f"\n⚠ 금지 문구가 남은 섹션이 있습니다: {names}")
        print("  build_report.md 를 열어 해당 부분을 직접 고친 뒤 발행하세요.")
        return 2

    print("\n금지 문구 검사를 모두 통과했습니다. 발행 전 사람이 한 번 읽어보세요.")
    if args.dry_run:
        print("※ 모의 실행 결과입니다. 본문은 예시 콘텐츠이므로 그대로 쓰지 마세요.")

    if args.serve:
        print()
        serve_folder(out_dir, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if getattr(args, "func", None) is not None:
            return args.func(args)
        return cmd_build(args)
    except FileNotFoundError as exc:
        print(f"오류: {exc}", file=sys.stderr)
    except LLMError as exc:
        print(f"생성 실패: {exc}", file=sys.stderr)
    except RuntimeError as exc:  # API 키 누락 등 설정 문제
        print(f"설정 오류: {exc}", file=sys.stderr)
    except ValueError as exc:  # pydantic ValidationError 포함
        print(f"입력이 올바르지 않습니다:\n{exc}", file=sys.stderr)
    except OSError as exc:
        print(f"열지 못했습니다: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
