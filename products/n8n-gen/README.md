# n8n 워크플로 JSON 생성기

자연어로 적은 자동화 요구를 **n8n 에 그대로 가져올 수 있는 `workflow.json`** 으로 바꿉니다.
자동화 대행(크몽 55~88만 원 구조)에서 가장 오래 걸리는 "워크플로 초안 짜기"를 줄이는 것이 목적입니다.

```
"매일 아침 9시에 구글시트 매출 탭을 읽어 Claude로 세 줄 요약해 슬랙 #report 에 보내줘"
        ↓
workflow.json · plan.md · setup_guide.md · test_payload.json
```

> **이 도구는 초안 생성기입니다.** 만들어진 워크플로는 credential 이 비어 있고 비활성 상태입니다.
> 반드시 사람이 n8n 에서 열어 값을 채우고, 테스트로 한 번 돌려본 뒤 켜야 합니다.
> 자동으로 켜지는 경로는 프로그램 어디에도 없습니다.

---

## 1. 핵심 설계 — LLM 에게 노드 스키마를 맡기지 않는다

n8n 노드 JSON 은 노드마다 `typeVersion` 과 파라미터 구조가 다르고, 한 글자만 틀려도
import 할 때 "노드를 인식할 수 없음"으로 깨집니다. LLM 에게 노드 JSON 을 통째로 쓰게 하면
그럴듯하지만 열리지 않는 파일이 나옵니다.

그래서 역할을 둘로 쪼갰습니다.

| | 사람이 미리 검증한 것 | Claude 가 그때그때 정하는 것 |
|---|---|---|
| 무엇 | `templates/nodes/*.json` 15종의 노드 스키마·`typeVersion`·파라미터 구조 | 어떤 템플릿을, 어떤 순서로, 어떤 파라미터 값으로 |
| 형식 | 사람이 작성한 고정 JSON | `{steps:[], connections:[]}` 계획 JSON |
| 틀리면 | 템플릿을 고칩니다 (한 번 고치면 전부 반영) | pydantic 이 되돌려 보내 다시 시키고, 그래도 안 되면 대체합니다 |

Claude 가 내놓는 것은 **계획**뿐이고, 실제 노드 JSON 은 `assembler.py` 가 검증된 템플릿에
값만 끼워 넣어 만듭니다. 그래서 "열리지 않는 workflow.json" 이 원리적으로 나오지 않습니다.

Claude 가 목록에 없는 노드를 고르면 **오류를 내지 않고** HTTP Request 노드로 대체한 뒤,
무엇을 대체했고 수동으로 무엇을 해야 하는지 `plan.md` 에 적습니다.

---

## 2. 설치

```bash
pip install -r requirements.txt          # 루트 requirements.txt 로도 됩니다
cp .env.example .env                     # ANTHROPIC_API_KEY 를 넣으세요
```

`.env` 는 커밋되지 않습니다(`.gitignore`). API 키를 `workflow.json` 이나 Git 에 넣지 마세요.

---

## 3. 사용법

```bash
# 모의 실행 — Claude 를 부르지 않습니다. 비용 0원
python cli.py "매일 9시에 구글시트를 읽어 Claude로 요약해 슬랙에 보내줘" --dry-run

# 실제 생성
python cli.py "매일 9시에 구글시트를 읽어 Claude로 요약해 슬랙에 보내줘"

# 예시 5개를 한 번에 (완료 기준 확인용)
python cli.py --examples --dry-run

# 요구를 파일에 적어두고 처리 (통합 대시보드가 쓰는 방식)
python cli.py --request-file request.txt

# 로컬 n8n 에 REST API 로 바로 만들기
python cli.py "..." --push
```

| 옵션 | 설명 |
|---|---|
| `--dry-run` | Claude 호출 없이 예시 계획으로 조립·검증만. 비용이 들지 않습니다 |
| `--examples` | `templates/examples.txt` 의 요구 5개를 전부 처리 |
| `--request-file PATH` | 한 줄에 하나씩 적은 요구 파일을 처리 (`#` 줄은 무시) |
| `--push` | `N8N_URL`·`N8N_API_KEY` 가 있으면 n8n 에 워크플로를 만듭니다 (비활성 상태로) |
| `--model` | Claude 모델 (기본 `claude-sonnet-4-6`) |
| `--no-ai-label` | AI 생성물 표시를 끕니다. 기본은 켜짐 |
| `--out` | 산출물 상위 폴더 (기본 `outputs/`) |

종료 코드: `0` 전부 검증 통과 / `2` 만들었지만 사람이 손볼 곳이 있음 / `1` 오류.

### 요구를 적는 요령

한 문장에 네 가지가 들어가면 결과가 정확해집니다.

1. **언제 시작** — "매일 아침 9시에" / "웹훅으로 주문이 들어오면"
2. **어디서 가져와** — "구글시트 매출 탭에서" / "결제 API 에서"
3. **무엇을 해** — "Claude 로 세 줄 요약해서" / "금액이 10만원 넘으면"
4. **어디로 보내** — "슬랙 #report 채널에" / "고객에게 Gmail 로"

---

## 4. 산출물 4종

| 파일 | 내용 | 누구에게 |
|---|---|---|
| `workflow.json` | n8n 에서 Import 하는 파일. credential 은 이름만 비워둔 자리표시 | n8n 에 넣습니다 |
| `plan.md` | 노드 순서·역할·필요한 credential·노드별 파라미터 표, 대체한 항목 기록 | 대행자(본인)가 봅니다 |
| `setup_guide.md` | 고객에게 그대로 넘기는 설치 가이드 7단계 | **납품물** |
| `test_payload.json` | 웹훅 트리거일 때만 생성. 테스트로 쏴볼 샘플 요청 | 테스트용 |

`plan.md` 와 `setup_guide.md` 에는 AI 생성물 표시가 기본으로 들어갑니다(인공지능기본법 제31조).

---

## 5. 지원 노드 15종

`templates/nodes/*.json` 에 있는 것만 씁니다. 여기 없는 노드는 HTTP Request 로 대체되고 기록됩니다.

| 템플릿 id | 이름 | n8n 노드 | credential | 파라미터 |
|---|---|---|---|---|
| `schedule-trigger` | 스케줄 트리거 | scheduleTrigger v1.2 | — | hour, minute |
| `webhook-trigger` | 웹훅 트리거 | webhook v2 | — | path, method |
| `google-sheets-read` | 구글시트 읽기 | googleSheets v4.5 | googleSheetsOAuth2Api | document_id, sheet_name |
| `google-sheets-append` | 구글시트 추가 | googleSheets v4.5 | googleSheetsOAuth2Api | document_id, sheet_name |
| `http-request` | HTTP 요청 | httpRequest v4.2 | — | method, url, body |
| `claude` | Claude 호출 | httpRequest v4.2 | httpHeaderAuth | model, max_tokens, system, prompt |
| `code` | 코드 (JavaScript) | code v2 | — | code |
| `if` | 조건 분기 | if v2.2 | — | left, operator, right |
| `set` | 필드 설정 | set v3.4 | — | field_name, field_value |
| `merge` | 합치기 | merge v3 | — | mode |
| `wait` | 대기 | wait v1.1 | — | amount, unit |
| `gmail-send` | Gmail 보내기 | gmail v2.1 | gmailOAuth2 | to, subject, body |
| `slack-post` | 슬랙 메시지 | slack v2.2 | slackApi | channel, text |
| `telegram-send` | 텔레그램 메시지 | telegram v1.2 | telegramApi | chat_id, text |
| `notion-create-page` | 노션 페이지 생성 | notion v2.2 | notionApi | database_id, title |

`claude` 는 전용 노드 대신 HTTP Request 로 Anthropic Messages API 를 직접 부릅니다.
n8n 버전에 따라 AI 노드 구성이 달라져도 깨지지 않기 때문입니다.

### 노드를 추가하려면

1. n8n 화면에서 원하는 노드를 하나 놓고 값을 채운 뒤 **Ctrl+C** 로 복사합니다 (노드 JSON 이 클립보드에 들어옵니다).
2. `templates/nodes/<이름>.json` 으로 저장하고, 바뀌어야 할 값을 `{{키}}` 로 바꿉니다.
3. `id`·`label`·`description`·`params`·`credential` 메타를 채웁니다.
4. `tests/test_n8n_gen.py` 를 돌립니다. credential 이 있으면 `writers.py` 의 `CREDENTIAL_GUIDE` 에 안내를 추가해야 통과합니다.

프롬프트는 템플릿 목록에서 자동으로 만들어지므로 프롬프트를 따로 고칠 필요가 없습니다.

---

## 6. 검증 — `validator.py`

조립된 workflow 를 7가지로 검사합니다. 하나라도 걸리면 종료 코드 `2` 입니다.

| 검사 | 걸리면 |
|---|---|
| 필수 키 (`id`·`nodes`·`connections`) | 오류 |
| **최상위 `id` 존재** | 오류 — 없으면 n8n CLI import 가 DB 제약으로 실패합니다 |
| 노드 이름 중복 | 오류 — connections 가 이름으로 연결되므로 엉뚱한 곳에 붙습니다 |
| 연결 대상 노드 존재 | 오류 |
| 트리거 노드 정확히 1개 | 오류 |
| 고아 노드 0개 (트리거에서 도달 불가) | 오류 |
| position 이 숫자 2개 | 오류 |
| 모르는 노드 타입 | 경고 (오류 아님) |

---

## 7. 실제 n8n 에서 열어보기

### Docker 로 n8n 띄우기

```bash
docker run -it --rm \
  -p 5678:5678 \
  -v n8n_data:/home/node/.n8n \
  docker.n8n.io/n8nio/n8n
```

브라우저에서 `http://localhost:5678` 을 열고 계정을 만든 뒤,
좌측 상단 **⋯ → Import from File** 로 `workflow.json` 을 고릅니다.

### npm 으로 띄우기 (Docker 를 못 쓸 때)

```bash
npm install -g n8n
n8n start                                  # http://localhost:5678
n8n import:workflow --input=outputs/<폴더>/workflow.json
```

### 검증 기록

이 저장소의 예시 5개는 **실제 n8n 2.35.7** 에 `n8n import:workflow` 로 넣어
5건 모두 오류 없이 들어가는 것을 확인했습니다. `export:workflow --all` 로 되읽었을 때
노드 수와 연결 수가 그대로였습니다.

| 워크플로 | 노드 | 연결 |
|---|---|---|
| 매일 시트 요약 슬랙 알림 | 5 | 4 |
| 문의 폼 자동 분류 | 6 | 5 |
| 주문 데이터 노션 기록 | 4 | 3 |
| 결제 확인 영수증 발송 | 5 | 4 |
| 매출 코멘트 자동 기록 | 6 | 5 |

이 과정에서 **찾아낸 결함 하나**를 기록해 둡니다. n8n CLI 의 `import:workflow` 는
workflow JSON 에 **최상위 `id` 가 없으면** 다음으로 실패합니다.

```
SQLITE_CONSTRAINT: NOT NULL constraint failed: workflow_entity.id
```

화면의 Import from File 은 id 를 알아서 만들어 주지만 CLI 는 만들어 주지 않습니다.
그래서 `assembler.workflow_id()` 가 워크플로 이름의 sha256 을 nanoid 문자집합으로
16자로 접어 넣습니다. 이름이 같으면 id 도 같으므로 **다시 import 하면 새로 쌓이지 않고
덮어써집니다.** validator 의 `missing-id` 검사가 이 조건을 고정합니다.

(참고: 이 컨테이너에서는 Docker 레지스트리가 프록시에 막혀 이미지를 받지 못해
npm 설치본으로 확인했습니다. 두 경로 모두 같은 n8n 코어를 씁니다.)

---

## 8. `--push` 로 바로 만들기

n8n 에 API 키가 있으면 파일을 옮기지 않고 REST API 로 바로 만들 수 있습니다.

```bash
# .env
N8N_URL=http://localhost:5678
N8N_API_KEY=여기에_n8n_에서_발급한_키
```

n8n 화면에서 **Settings → API → Create an API key** 로 발급합니다.

```bash
python cli.py "..." --push
```

- 검증에 실패한 워크플로가 하나라도 있으면 push 를 건너뜁니다.
- 만들어진 워크플로는 **비활성** 상태입니다. credential 을 연결하고 테스트한 뒤 사람이 켜야 합니다.
- 보내는 필드는 `name`·`nodes`·`connections`·`settings` 뿐입니다. 키가 섞여 나가지 않습니다.

---

## 9. 비밀키를 다루는 방식

- `workflow.json` 의 credential 자리에는 **이름만** 들어갑니다: `{"id": null, "name": "[Slack 연결 필요]"}`
- 실제 토큰·비밀번호는 n8n 안에서만 입력하고, 파일에도 Git 에도 남지 않습니다.
- 그래서 **만들어진 workflow.json 을 고객에게 그대로 보내도 안전합니다.**
- 고객 계정 정보를 대신 받아 입력하지 마세요. 화면 공유로 고객이 직접 넣게 하는 편이 안전하고, 문제가 생겼을 때 책임 소재도 분명합니다.

---

## 10. 파일 구조

```
products/n8n-gen/
├─ cli.py                     3단계 명령 진입점
├─ request.txt                대시보드가 읽는 요구 파일
├─ n8n_gen/
│  ├─ nodes.py                템플릿 적재·목록 문자열
│  ├─ schema.py               Plan/PlanStep/PlanConnection (pydantic)
│  ├─ generator.py            Claude 에게 계획을 받고 형식이 틀리면 되돌려 보냄
│  ├─ assembler.py            템플릿 + 값 → nodes[]·connections{}
│  ├─ validator.py            7가지 검사
│  ├─ writers.py              산출물 4종
│  ├─ pusher.py               n8n REST API
│  └─ sample_content.py       모의 실행용 예시 계획 5개
├─ templates/
│  ├─ nodes/*.json            검증된 노드 템플릿 15종
│  └─ examples.txt            예시 요구 5개
├─ prompts/plan.md            계획 생성 프롬프트
└─ docs/
   ├─ admin.md                관리자 매뉴얼
   └─ client.md               고객용 매뉴얼
```

---

## 11. 판매 문구 초안

### 서비스 제목 후보

- n8n 자동화 워크플로 설계 + 설치 가이드 납품
- 반복 업무 자동화 — n8n 워크플로 제작해 드립니다
- 구글시트·슬랙·Gmail 연동 자동화 설계

### 상세 설명 초안

> 매일 손으로 하시는 반복 작업을 n8n 워크플로로 옮겨 드립니다.
>
> "매일 아침 시트를 열어 어제 매출을 확인하고 슬랙에 정리해 올린다" 같은 일이라면
> 사람이 하지 않아도 되는 부분이 있습니다. 어디까지가 자동화할 수 있는 부분인지 먼저 정리해 드리고,
> 실제로 도는 워크플로와 **사장님이 직접 관리할 수 있는 설치 가이드**를 함께 드립니다.
>
> **드리는 것**
> - n8n 워크플로 파일 (`workflow.json`) — 계정 정보는 사장님이 직접 넣으시므로 저희가 보관하지 않습니다
> - 설치 가이드 — 화면 순서대로 따라가면 되는 7단계
> - 노드별 역할 설명서 — 나중에 직접 고치실 때 보시는 문서
>
> **말씀드릴 점**
> - 자동화는 사람이 하던 일의 순서를 옮기는 것이지, 없던 성과를 만들지 않습니다. 효과는 원래 그 일에 쓰시던 시간에 달려 있습니다.
> - 연동하려는 서비스가 공식 API 를 제공하지 않으면 자동화할 수 없습니다. 상담 때 먼저 확인해 드립니다.
> - 처음 켤 때는 반드시 테스트로 한 번 돌려보고 결과를 확인하신 뒤 사용하시길 권합니다.
>
> 이 워크플로 설계에는 생성형 AI 를 사용하며, 산출 문서에 그 사실을 표시합니다.

### 패키지 예시

| | BASIC | STANDARD | PREMIUM |
|---|---|---|---|
| 워크플로 | 1개 | 3개 | 3개 |
| 설치 가이드 | ○ | ○ | ○ |
| 설치 대행 | — | 화면공유 1회 | 화면공유 2회 |
| 월 유지보수 | — | — | 1개월 포함 |

가격은 시장 상황과 작업 범위에 맞춰 직접 정하세요. 월 유지보수를 붙이면 매출이 이어집니다.

---

## 12. 하지 않는 것

- 계정 비밀번호를 받아 대신 입력하지 않습니다. 공식 OAuth·API 키만 씁니다.
- 브라우저 매크로처럼 비공식 자동화를 만들지 않습니다.
- 사람 확인 없이 대량으로 글을 올리는 워크플로를 만들지 않습니다.
- 콜드 DM·자동 팔로우처럼 플랫폼 정책을 어기는 워크플로를 만들지 않습니다.
- 만든 워크플로를 자동으로 켜지 않습니다. 켜는 것은 언제나 사람의 결정입니다.
