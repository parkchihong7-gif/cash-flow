"""모의 실행용 예시 계획.

실제 Claude 를 부르지 않고 계획 → 조립 → 검증 → 산출물 전 과정을 돌리기 위한 고정 응답이다.
두 군데서 쓴다.

1. `python cli.py "요구" --dry-run` — API 비용 없이 산출물 형태를 미리 본다.
2. 테스트 — 실제 호출 없이 전 과정을 검증한다.

`templates/examples.txt` 의 예시 5개에 각각 대응한다.
요구에 들어간 낱말로 어느 계획을 돌려줄지 고른다.
"""

from __future__ import annotations

import copy

PLANS = {
    "sheet-claude-slack": {
        "workflow_name": "매일 시트 요약 슬랙 알림",
        "summary": "매일 아침 9시에 구글시트를 읽어 Claude 로 요약한 뒤 슬랙 채널에 보냅니다.",
        "steps": [
            {
                "id": "s1",
                "template": "schedule-trigger",
                "name": "매일 9시",
                "params": {
                    "hour": 9,
                    "minute": 0
                },
                "note": "매일 아침 9시에 시작"
            },
            {
                "id": "s2",
                "template": "google-sheets-read",
                "name": "구글시트 읽기",
                "params": {
                    "document_id": "[스프레드시트 ID를 넣으세요]",
                    "sheet_name": "A"
                },
                "note": "A 탭의 행을 읽어옵니다"
            },
            {
                "id": "s3",
                "template": "claude",
                "name": "Claude 요약",
                "params": {
                    "system": "너는 표 데이터를 3줄로 요약하는 비서다.",
                    "prompt": "={{ JSON.stringify($json) }}",
                    "max_tokens": 1000
                },
                "note": "읽은 행을 요약합니다"
            },
            {
                "id": "s4",
                "template": "set",
                "name": "요약 정리",
                "params": {
                    "field_name": "summary",
                    "field_value": "={{ $json.content[0].text }}"
                },
                "note": "Claude 응답에서 본문만 꺼냅니다"
            },
            {
                "id": "s5",
                "template": "slack-post",
                "name": "슬랙 전송",
                "params": {
                    "channel": "report",
                    "text": "={{ $json.summary }}"
                },
                "note": "#report 채널에 보냅니다"
            }
        ],
        "connections": [
            {
                "from": "s1",
                "to": "s2"
            },
            {
                "from": "s2",
                "to": "s3"
            },
            {
                "from": "s3",
                "to": "s4"
            },
            {
                "from": "s4",
                "to": "s5"
            }
        ],
        "unsupported": []
    },
    "webhook-triage": {
        "workflow_name": "문의 폼 자동 분류",
        "summary": "웹훅으로 들어온 문의를 Claude 로 분류해 긴급하면 텔레그램, 아니면 시트에 기록합니다.",
        "steps": [
            {
                "id": "s1",
                "template": "webhook-trigger",
                "name": "문의 수신",
                "params": {
                    "path": "inquiry",
                    "method": "POST"
                },
                "note": "폼 제출을 받습니다"
            },
            {
                "id": "s2",
                "template": "claude",
                "name": "긴급도 분류",
                "params": {
                    "system": "문의 내용을 읽고 urgent 또는 normal 중 하나만 답하라.",
                    "prompt": "={{ $json.body.message }}",
                    "max_tokens": 20
                },
                "note": "긴급 여부를 판단합니다"
            },
            {
                "id": "s3",
                "template": "set",
                "name": "판정 정리",
                "params": {
                    "field_name": "level",
                    "field_value": "={{ $json.content[0].text }}"
                },
                "note": "판정 결과를 필드로 만듭니다"
            },
            {
                "id": "s4",
                "template": "if",
                "name": "긴급인가",
                "params": {
                    "left": "={{ $json.level }}",
                    "operator": "contains",
                    "right": "urgent"
                },
                "note": "긴급이면 참, 아니면 거짓"
            },
            {
                "id": "s5",
                "template": "telegram-send",
                "name": "텔레그램 알림",
                "params": {
                    "chat_id": "[채팅 ID]",
                    "text": "긴급 문의: ={{ $json.level }}"
                },
                "note": "긴급할 때만 보냅니다"
            },
            {
                "id": "s6",
                "template": "google-sheets-append",
                "name": "시트 기록",
                "params": {
                    "document_id": "[스프레드시트 ID를 넣으세요]",
                    "sheet_name": "문의"
                },
                "note": "일반 문의는 시트에 쌓습니다"
            }
        ],
        "connections": [
            {
                "from": "s1",
                "to": "s2"
            },
            {
                "from": "s2",
                "to": "s3"
            },
            {
                "from": "s3",
                "to": "s4"
            },
            {
                "from": "s4",
                "to": "s5",
                "from_output": 0
            },
            {
                "from": "s4",
                "to": "s6",
                "from_output": 1
            }
        ],
        "unsupported": []
    },
    "api-notion": {
        "workflow_name": "주문 데이터 노션 기록",
        "summary": "매일 저녁 외부 API 에서 주문을 받아 가공한 뒤 노션에 페이지로 만듭니다.",
        "steps": [
            {
                "id": "s1",
                "template": "schedule-trigger",
                "name": "매일 18시",
                "params": {
                    "hour": 18,
                    "minute": 0
                },
                "note": "매일 저녁 6시"
            },
            {
                "id": "s2",
                "template": "http-request",
                "name": "주문 API 호출",
                "params": {
                    "method": "GET",
                    "url": "[주문 API 주소를 넣으세요]"
                },
                "note": "외부에서 주문 데이터를 받습니다"
            },
            {
                "id": "s3",
                "template": "code",
                "name": "데이터 가공",
                "params": {
                    "code": "return items.map(i => ({ json: { title: i.json.order_id, amount: i.json.total } }));"
                },
                "note": "노션에 넣을 모양으로 정리합니다"
            },
            {
                "id": "s4",
                "template": "notion-create-page",
                "name": "노션 페이지 생성",
                "params": {
                    "database_id": "[데이터베이스 ID]",
                    "title": "={{ $json.title }}"
                },
                "note": "데이터베이스에 페이지를 만듭니다"
            }
        ],
        "connections": [
            {
                "from": "s1",
                "to": "s2"
            },
            {
                "from": "s2",
                "to": "s3"
            },
            {
                "from": "s3",
                "to": "s4"
            }
        ],
        "unsupported": []
    },
    "payment-receipt": {
        "workflow_name": "결제 확인 영수증 발송",
        "summary": "결제 알림이 오면 잠시 기다렸다 상태를 확인하고 영수증 메일을 보냅니다.",
        "steps": [
            {
                "id": "s1",
                "template": "webhook-trigger",
                "name": "결제 알림 수신",
                "params": {
                    "path": "payment",
                    "method": "POST"
                },
                "note": "결제 웹훅"
            },
            {
                "id": "s2",
                "template": "wait",
                "name": "30초 대기",
                "params": {
                    "amount": 30,
                    "unit": "seconds"
                },
                "note": "결제 확정까지 기다립니다"
            },
            {
                "id": "s3",
                "template": "http-request",
                "name": "결제 상태 확인",
                "params": {
                    "method": "GET",
                    "url": "[결제 상태 조회 API 주소]"
                },
                "note": "상태를 다시 조회합니다"
            },
            {
                "id": "s4",
                "template": "if",
                "name": "결제 완료인가",
                "params": {
                    "left": "={{ $json.status }}",
                    "operator": "equals",
                    "right": "paid"
                },
                "note": "완료일 때만 영수증을 보냅니다"
            },
            {
                "id": "s5",
                "template": "gmail-send",
                "name": "영수증 메일",
                "params": {
                    "to": "={{ $json.email }}",
                    "subject": "결제 영수증",
                    "body": "={{ $json.receipt_url }}"
                },
                "note": "고객에게 영수증을 보냅니다"
            }
        ],
        "connections": [
            {
                "from": "s1",
                "to": "s2"
            },
            {
                "from": "s2",
                "to": "s3"
            },
            {
                "from": "s3",
                "to": "s4"
            },
            {
                "from": "s4",
                "to": "s5",
                "from_output": 0
            }
        ],
        "unsupported": []
    },
    "sales-comment": {
        "workflow_name": "매출 코멘트 자동 기록",
        "summary": "아침마다 어제 매출을 읽어 Claude 코멘트를 붙이고 시트와 슬랙에 남깁니다.",
        "steps": [
            {
                "id": "s1",
                "template": "schedule-trigger",
                "name": "매일 8시",
                "params": {
                    "hour": 8,
                    "minute": 0
                },
                "note": "매일 아침 8시"
            },
            {
                "id": "s2",
                "template": "google-sheets-read",
                "name": "매출 읽기",
                "params": {
                    "document_id": "[스프레드시트 ID를 넣으세요]",
                    "sheet_name": "매출"
                },
                "note": "어제 매출 행을 읽습니다"
            },
            {
                "id": "s3",
                "template": "claude",
                "name": "코멘트 생성",
                "params": {
                    "system": "매출 데이터를 보고 한 문장 코멘트를 쓰는 분석가다.",
                    "prompt": "={{ JSON.stringify($json) }}",
                    "max_tokens": 300
                },
                "note": "코멘트를 만듭니다"
            },
            {
                "id": "s4",
                "template": "set",
                "name": "코멘트 정리",
                "params": {
                    "field_name": "comment",
                    "field_value": "={{ $json.content[0].text }}"
                },
                "note": "응답에서 본문만 꺼냅니다"
            },
            {
                "id": "s5",
                "template": "google-sheets-append",
                "name": "시트에 기록",
                "params": {
                    "document_id": "[스프레드시트 ID를 넣으세요]",
                    "sheet_name": "코멘트"
                },
                "note": "코멘트를 시트에 남깁니다"
            },
            {
                "id": "s6",
                "template": "slack-post",
                "name": "슬랙 알림",
                "params": {
                    "channel": "sales",
                    "text": "={{ $json.comment }}"
                },
                "note": "슬랙에도 알립니다"
            }
        ],
        "connections": [
            {
                "from": "s1",
                "to": "s2"
            },
            {
                "from": "s2",
                "to": "s3"
            },
            {
                "from": "s3",
                "to": "s4"
            },
            {
                "from": "s4",
                "to": "s5"
            },
            {
                "from": "s5",
                "to": "s6"
            }
        ],
        "unsupported": []
    }
}

#: (요구에 들어 있으면 고르는 낱말들, 계획 이름)
#: 구체적인 조건을 앞에 둔다. 위에서부터 먼저 맞는 것을 쓴다.
#: 구체적인 조건을 앞에 둔다. 위에서부터 먼저 맞는 것을 쓴다.
KEYWORDS = [
    [
        [
            "매출"
        ],
        "sales-comment"
    ],
    [
        [
            "결제",
            "영수증"
        ],
        "payment-receipt"
    ],
    [
        [
            "노션"
        ],
        "api-notion"
    ],
    [
        [
            "웹훅",
            "분류"
        ],
        "webhook-triage"
    ],
    [
        [
            "구글시트",
            "슬랙"
        ],
        "sheet-claude-slack"
    ]
]


def pick_plan(request: str) -> str:
    """요구 문장에서 어느 예시 계획을 쓸지 고른다."""
    for words, name in KEYWORDS:
        if all(word in request for word in words):
            return name
    return "sheet-claude-slack"


def fake_ask(system: str, user: str, model: str = "test", json_mode: bool = False, **_):
    """[요구] 줄을 읽어 대응하는 계획을 돌려준다."""
    if "[요구]" not in user:
        raise AssertionError(f"모의 콘텐츠가 모르는 프롬프트입니다:\n{user[:300]}")
    request = user.split("[요구]", 1)[1].split("\n\n", 1)[0].strip()
    return copy.deepcopy(PLANS[pick_plan(request)])
