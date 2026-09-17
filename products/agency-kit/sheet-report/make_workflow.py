"""n8n 워크플로 JSON 만들기 — **6번 상품의 노드 틀을 그대로 쓴다.**

    python make_workflow.py                 # workflow.json 을 다시 만든다
    python make_workflow.py --hour 9 --weekday 1

왜 손으로 안 쓰고 만드는가
    노드 규격(`typeVersion` 같은 것)은 n8n 판이 올라가면 바뀐다. 6번 상품
    `products/n8n-gen/templates/nodes/` 를 고치면 이 워크플로도 같이 맞는다.
    두 군데에 같은 값을 적어 두면 한쪽이 조용히 낡는다.

무엇을 만드나
    매주 월요일 아침 9시 → 보고서 서버 호출 → 슬랙에 요약 올리기

    스케줄 트리거 → HTTP 요청 → 슬랙

크리덴셜은 **이름만** 넣는다. 실제 토큰은 n8n 화면에서 넣는다(CLAUDE.md §7).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
NODES_DIR = BASE_DIR.parents[1] / "n8n-gen" / "templates" / "nodes"

__all__ = ["build", "load_template", "NODES_DIR"]


def load_template(name: str) -> dict:
    """6번 상품의 노드 틀 한 장을 읽는다."""
    path = NODES_DIR / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"노드 틀이 없습니다: {path}\n"
            "  6번 상품(products/n8n-gen)이 같은 저장소에 있어야 합니다.")
    return json.loads(path.read_text(encoding="utf-8"))


def _fill(value, replacements: dict[str, str]):
    """틀 안의 {{자리}} 를 실제 값으로 바꾼다."""
    if isinstance(value, str):
        for key, replacement in replacements.items():
            value = value.replace("{{" + key + "}}", str(replacement))
        return value
    if isinstance(value, dict):
        return {key: _fill(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_fill(item, replacements) for item in value]
    return value


def _node(template: dict, name: str, position: list[int], replacements: dict) -> dict:
    node = {
        "parameters": _fill(template["parameters"], replacements),
        "id": template["id"] + "-" + name.replace(" ", "-"),
        "name": name,
        "type": template["n8n_type"],
        "typeVersion": template["type_version"],
        "position": position,
    }
    if template.get("credential"):
        # 이름만 둔다. 실제 값은 n8n 화면에서 넣는다.
        node["credentials"] = {
            template["credential"]: {"id": "", "name": f"[{template['credential']} 자격증명]"}
        }
    return node


def build(hour: int = 9, minute: int = 0, weekday: int = 1,
          url: str = "http://host.docker.internal:8090/run",
          channel: str = "보고서", period: str = "week") -> dict:
    """워크플로 한 벌을 만든다.

    Args:
        hour, minute: 도는 시각.
        weekday: 요일 (0=일 … 1=월).
        url: 보고서 서버 주소. n8n 이 도커 안이면 host.docker.internal 을 쓴다.
        channel: 슬랙 채널 이름(# 없이).
        period: week / month / quarter.
    """
    schedule = load_template("schedule-trigger")
    http = load_template("http-request")
    slack = load_template("slack-post")

    body = json.dumps({"period": period, "dry_run": False}, ensure_ascii=False)

    nodes = [
        _node(schedule, "매주 월요일 아침", [240, 300],
              {"minute": minute, "hour": hour}),
        _node(http, "보고서 만들기", [520, 300],
              {"method": "POST", "url": url, "body": body}),
        _node(slack, "슬랙에 올리기", [800, 300],
              {"channel": channel, "text": "={{ $json.summary }}"}),
    ]

    # 스케줄 트리거는 매일 도는 크론이라, 요일을 여기서 좁힌다.
    nodes[0]["parameters"]["rule"]["interval"][0]["expression"] = (
        f"{minute} {hour} * * {weekday}")

    connections = {
        nodes[0]["name"]: {"main": [[{"node": nodes[1]["name"], "type": "main", "index": 0}]]},
        nodes[1]["name"]: {"main": [[{"node": nodes[2]["name"], "type": "main", "index": 0}]]},
    }

    return {
        "name": "주간 매출 보고서",
        "nodes": nodes,
        "connections": connections,
        "active": False,
        "settings": {"executionOrder": "v1"},
        "tags": [],
        "meta": {
            "생성": "products/agency-kit/sheet-report/make_workflow.py",
            "노드 틀": "products/n8n-gen/templates/nodes/",
            "쓰는 법": [
                "1. n8n 에서 워크플로 → 가져오기 → 이 파일을 고르세요",
                "2. '보고서 만들기' 노드의 주소를 실제 서버 주소로 바꾸세요",
                "3. 슬랙 자격증명을 n8n 화면에서 연결하세요 (여기에는 토큰이 없습니다)",
                "4. 오른쪽 위 Active 를 켜면 매주 돕니다",
            ],
            "주의": "n8n 이 도커 안에 있으면 localhost 가 아니라 host.docker.internal 입니다",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="make_workflow.py")
    parser.add_argument("--hour", type=int, default=9)
    parser.add_argument("--minute", type=int, default=0)
    parser.add_argument("--weekday", type=int, default=1, help="0=일 1=월 … 6=토")
    parser.add_argument("--url", default="http://host.docker.internal:8090/run")
    parser.add_argument("--channel", default="보고서")
    parser.add_argument("--period", default="week")
    parser.add_argument("--out", default=str(BASE_DIR / "workflow.json"))
    args = parser.parse_args(argv)

    workflow = build(hour=args.hour, minute=args.minute, weekday=args.weekday,
                     url=args.url, channel=args.channel, period=args.period)
    path = Path(args.out)
    path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    print(f"노드 {len(workflow['nodes'])}개 → {path}")
    print("n8n 에서 가져오기(Import) 하시면 됩니다. 토큰은 들어 있지 않습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
