# 17. 연예인 착용템 쇼츠 기획기 — 관리자 안내

## 구조

| 파일 | 하는 일 |
|---|---|
| `cli.py` | `build` / `check` / `approve` |
| `celeb_shorts/schema.py` | 입력·기획 모양. 장면 화면 종류(`VISUALS`)에 얼굴·방송 화면이 없음 |
| `celeb_shorts/rules.py` | 입력 검사(이름 허용·아이템 방식·가격)와 기획 검사(시간·자막·단정 표현·가격·금지 문구) |
| `celeb_shorts/generator.py` | Claude 요청을 만들고(쓰면 안 되는 값은 넘기지 않음) 한 번 부름 |
| `celeb_shorts/output.py` | 산출물 6종과 승인 |
| `celeb_shorts/disclosure.py` | 대가성 문구 — 지우는 옵션 없음 |
| `celeb_shorts/sample_content.py` | 모의 실행용 가짜 응답 |
| `prompts/plan.md` | 기획 규칙. 고쳐도 위 검사는 그대로 돈다 |

## 검사 수준

- **고침(·)**: 프로그램이 알아서 고친 것 — 시간 맞춤, 긴 자막 두 줄로, 출처 없는 이름 지움.
- **경고(⚠)**: 사람이 볼 것 — 두 줄로 나눠도 15자를 넘는 자막.
- **막음(⛔)**: 승인 불가 — 확인 안 된 아이템에 "똑같은/정품", 출처 없는 가격, '원가', 금지 문구,
  건강식품 효능 표현(`HEALTH_CLAIMS`), 화장품 의약품 표현(`BEAUTY_BLOCK`),
  확인 안 된 아이템의 추천 표현(`ENDORSE_WORDS`), '연예인들' 류 주장(`CROWD_WORDS`).
- 화장품 '미백·주름 개선'(`BEAUTY_WARN`)은 기능성 인증 확인 경고입니다.

낱말 목록은 `celeb_shorts/rules.py` 맨 위에 있습니다. 새로 걸러야 할 표현이 보이면 거기에 더하세요.

## 비용

실제 실행은 Claude 1회(max_tokens 4000). 15초 기획이라 한 편에 수십 원 수준입니다.

## 시험

```bash
python -m tools.programs test 17
```
