# cash-flow

부업 프로그램을 만들고 파는 프로젝트. 작업 지침 전문은 [`CLAUDE.md`](./CLAUDE.md)에 있습니다.

프로그램은 **통합 관리자 대시보드**에서 관리합니다. 터미널을 몰라도 브라우저에서
열람·수정·테스트·회원관리를 할 수 있습니다.

## 빠른 시작

```bash
pip install -r requirements.txt
cp .env.example .env          # ANTHROPIC_API_KEY 를 채웁니다
python -m dashboard           # http://127.0.0.1:8000
```

브라우저가 열리면 **접속 코드**를 넣어야 화면이 나옵니다.

```
기본 접속 코드: redwind7
```

한 번 넣으면 12시간 동안 유지됩니다. 왼쪽 아래 **나가기** 로 끊을 수 있습니다.

처음이라면 대시보드의 **매뉴얼 → 관리자 매뉴얼** 을 1장부터 읽으세요.
([docs/admin-manual.md](./docs/admin-manual.md))

## 어디서나 접속하기

내 PC 가 아닌 곳에서도 열려면 두 가지 길이 있습니다.

### ① 지금 당장 — 임시 주소 (설치 5분)

내 PC 에서 대시보드를 켠 채로, 바깥에서 닿는 https 주소를 하나 빌립니다.

```bash
# 한 번만 설치
brew install cloudflared                          # macOS
winget install --id Cloudflare.cloudflared        # Windows

python -m dashboard --public
```

터미널에 이렇게 뜹니다.

```
==========================================================
어디서나 접속:  https://아무글자-여기.trycloudflare.com
접속 코드:      redwind7
==========================================================
```

이 주소를 휴대폰이든 사무실 PC 든 어디서나 열면 됩니다.

- 가입도 카드도 필요 없습니다
- **내 PC 가 켜져 있고 이 터미널 창이 떠 있는 동안만** 열립니다
- **껐다 켜면 주소가 바뀝니다**

### ② 계속 쓰려면 — 항상 켜 두기 (permanent 주소)

내 PC 와 상관없이 늘 같은 주소로 열리게 하려면 클라우드에 올립니다.
저장소에 [`Dockerfile`](./Dockerfile) 과 [`render.yaml`](./render.yaml) 이 들어 있어
Render(render.com) 기준으로는 이 순서면 됩니다.

1. 이 저장소를 GitHub 에 올립니다
2. render.com 에 가입 → **New → Blueprint** → 저장소 선택
3. `render.yaml` 을 알아서 읽습니다. 물어보는 값만 채웁니다
   - `DASHBOARD_ACCESS_CODE` — **꼭 바꾸세요**
   - `ANTHROPIC_API_KEY` — 없으면 모의 실행만 됩니다
4. 몇 분 뒤 `https://이름.onrender.com` 주소가 나옵니다

Railway·Fly 도 같은 `Dockerfile` 을 그대로 씁니다.

**꼭 알아 두실 것**

| | |
|---|---|
| 요금제 | `render.yaml` 은 `starter` 로 되어 있습니다. `free` 로 바꾸면 15분 쉬면 잠들고 다시 깨는 데 1분쯤 걸립니다 |
| 디스크 | `render.yaml` 의 `disk` 를 빼면 **배포할 때마다 고객 정보가 지워집니다.** 붙여 두세요 |
| 산출물 | 엑셀·리포트 같은 산출물은 디스크에 들어가지 않아 배포 때 사라집니다. 다시 만들면 되는 것들이라 그대로 두었습니다 |
| 파일 수정 | 대시보드의 '수정' 탭에서 고친 내용도 배포하면 되돌아갑니다. 오래 남길 수정은 GitHub 에 올리세요 |

## 인터넷에 열기 전에 읽어 주세요

이 대시보드는 **접속 코드 하나로 전부를 엽니다.** 코드를 아는 사람은

- 고객 이름·연락처·주소를 모두 볼 수 있고
- 프로그램을 실행할 수 있고 (실제 실행은 API 요금이 나갑니다)
- `products/` 안의 파일을 고칠 수 있습니다

그래서 인터넷에 여신다면 아래를 지켜 주세요.

1. **접속 코드를 바꾸세요.** `.env` 에 넣습니다. 기본값을 쓰는 동안에는 화면 위에 경고가 뜹니다.
   ```
   DASHBOARD_ACCESS_CODE=직접-정한-긴-코드
   ```
2. **코드를 단톡방이나 메일에 그대로 올리지 마세요.** 한 번 퍼지면 회수할 방법이 없습니다.
3. **주소를 공개된 곳에 적지 마세요.** 코드가 있어도 주소가 안 알려지는 편이 안전합니다.
4. 코드가 샜다 싶으면 `.env` 의 코드와 `DASHBOARD_SECRET` 을 함께 바꾸고 다시 띄우세요.
   열려 있던 창이 전부 끊깁니다.

코드를 여러 번 틀리면 그 접속자는 10분 동안 잠깁니다. 자동으로 코드를 찍어 보는
방법은 이 때문에 통하지 않습니다.

### 접속 코드 관련 설정

| 환경변수 | 하는 일 | 기본값 |
|---|---|---|
| `DASHBOARD_ACCESS_CODE` | 접속 코드 | `redwind7` |
| `DASHBOARD_SESSION_HOURS` | 한 번 들어가면 유지되는 시간 | `12` |
| `DASHBOARD_SECRET` | 쿠키 서명용 비밀값. 바꾸면 모두 로그아웃됩니다 | 자동 생성 |
| `DASHBOARD_DATA_DIR` | 고객 DB 와 비밀값을 둘 폴더 | 저장소 폴더 |
| `PORT` | 포트. 클라우드가 정해 줍니다 | `8000` |

## 구조

```
CLAUDE.md          작업 브리프 (조사 결과 · 금지 사항 · 우선순위)
dashboard/         통합 관리자 대시보드 (FastAPI)
core/              프로그램 관리 공통 레이어
  manifest.py        program.yaml 규격
  registry.py        products/ 스캔
  db.py              고객·라이선스·실행 이력 (SQLite)
  runner.py          프로그램 실행과 이력 기록
shared/            상품이 함께 쓰는 유틸
  llm.py             Claude API 래퍼
  ai_label.py        AI 생성물 표시 (인공지능기본법 제31조)
  banned_phrases.py  판매용 텍스트 금지 문구 검사
  config.py          .env 로드, 경로 상수
products/          상품별 폴더 (상품 1개 = 폴더 1개)
  <상품>/program.yaml  대시보드 등록용 매니페스트
  <상품>/<고유패키지>/  내부 모듈 (이름 충돌 방지용 고유 패키지)
docs/              통합 매뉴얼 (관리자용 / 클라이언트용)
tests/             테스트
```

## 새 프로그램을 추가하려면

`products/<이름>/program.yaml` 하나만 만들면 대시보드에 자동 등록됩니다.
**대시보드 코드는 고치지 않습니다.**

규격은 [`core/manifest.py`](./core/manifest.py), 작성 예시는
[관리자 매뉴얼 5장](./docs/admin-manual.md)에 있습니다.

## 등록된 프로그램

| 번호 | 폴더 | 상품 | 상태 |
|---|---|---|---|
| 1 | [`funnel-builder/`](./products/funnel-builder) | 퍼널 빌더 (랜딩 + 이메일 5통) | 운영 중 |
| 2 | [`hook-script/`](./products/hook-script) | 후킹 대본 생성기 (롱폼·쇼츠·릴스) | 운영 중 |
| 3 | [`ebook-gen/`](./products/ebook-gen) | 전자책 원고 생성기 (docx) | 운영 중 |
| 4 | [`lecture-deck/`](./products/lecture-deck) | 강의 슬라이드 생성기 (pptx) | 운영 중 |
| 5 | [`kmong-copy/`](./products/kmong-copy) | 크몽 상세페이지 카피 생성기 | 운영 중 |
| 6 | [`n8n-gen/`](./products/n8n-gen) | n8n 워크플로 JSON 생성기 | 운영 중 |
| 7 | [`groupbuy-ledger/`](./products/groupbuy-ledger) | 공구 정산 엑셀 자동 생성기 | 운영 중 |
| 8 | [`income-sim/`](./products/income-sim) | 수익 시뮬레이터 | 운영 중 |
| 9 | `agency-kit/` | 자동화 대행 납품 키트 | 미착수 |
| 10 | `niche-research/` | 저가 유튜브 니치 리서치 | 미착수 |

## 확인

```bash
pytest tests/
```

## 규칙

- Claude 호출은 anthropic SDK 를 직접 쓰지 말고 `shared.llm.ask()` 를 씁니다.
- 판매용 텍스트는 `shared.banned_phrases.check()` 를 통과해야 합니다. (CLAUDE.md §3-2, §7)
- 모든 AI 산출물에 표시를 기본 on 으로 붙입니다. (CLAUDE.md §3-5)
- 비밀키는 `.env` 에, 고객 데이터는 `dashboard.db` 에 있고 둘 다 커밋하지 않습니다.
  **`dashboard.db` 는 직접 백업해야 합니다.**
