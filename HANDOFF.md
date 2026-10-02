# 이어받기 메모 (HANDOFF)

> 새 세션은 이 파일을 먼저 읽는다. 끝낼 때 «지금 상태» 와 «다음 할 일» 을 고쳐 둔다.
> **공개 저장소** — 키·토큰·시트 ID·Apps Script 주소·서버 주소 같은 값은 여기에도 적지 않는다.

마지막 갱신: 2026-10-02 (세션 종료 시)

## 지금 상태

| 저장소 | 브랜치 | 내용 |
|---|---|---|
| `parkchihong7-gif/cash-flow` (공개) | `claude/cash-flow-repo-setup-ijd19o` (이전 `claude/new-session-9lqy1t` 와 같은 내용에서 시작) | 통합 관리자 대시보드, 상품 안내서, `tools/` |
| maim (네이버 블로그 초안 생성기) | `claude/great-brown-j376u0` | Node 20/TS · Fastify · SQLite · Cloud Run |

### 네이버 블로그 초안 생성기 — 마지막 작업
- 포스팅 5분 안: **조사(도구, 120초/75초 한도) → 글쓰기(도구 없음, 300초)**, 블로그 참고 주소 메모는 자리에 하나,
  카테고리 주소 메모는 카테고리마다(7일·주소 변경 시 다시 읽음). `src/pipeline/조사.ts`, `자료메모.ts`, `generatePost.ts`
- 블로그 관리 표: 주제(가장 긴 이름에 맞춰 자동) / 주제 키워드 / 활성(눌러 켜고 끔) / 포스팅 생성 / 상태(220px).
  하루 포스팅 수는 삭제(켜진 카테고리마다 하루 한 편).
- **사용자 확인 대기:** 배포 후 [지금 생성]의 `⏱` 줄(조사·글·사진 시간). 글쓰기가 3분 넘으면
  [관리자 설정] 1단계 모델을 `sonnet` 으로 바꿀지 사용자가 정한다.

배포(사용자가 Cloud Shell 에서):
```
cd ~/maim && git pull && gcloud run deploy maim --source . --region=us-central1 --allow-unauthenticated --concurrency=80
```

### 통합 대시보드(cash-flow) — 마지막 작업 (2026-10-02)
- **프로그램 순번**: 대시보드 순서 = `program.yaml` 의 `number` (1 공인중개사 · 2 시니어 영상 · 3 네이버 블로그 · 4 해외 연사 ·
  5 퍼널 · 6 후킹 · 7 전자책 · 8 강의 슬라이드 · 9 크몽 · 10 n8n · 11 공구 정산 · 12 수익 시뮬 · 13 노션 · 14 제휴 · 15 대행 키트 · 16 니치).
  `products/README.md` 와 문서·주석·시험 설명의 옛 번호(옛 1~12 → 5~16, 옛 13~16 → 1~4)를 모두 고쳤다.
  각 프로그램 **안의** 번호(수익 시뮬 모델 번호, 크몽 칸 번호 등)는 그대로다.
- **접속 코드**: 코드·문서에서 기본 접속 코드를 없앴다. `DASHBOARD_ACCESS_CODE` 가 없으면 로그인 자체를 막고 안내한다
  (`core/auth.py` `code_is_set`). 스냅샷은 그 자리에서만 임시 코드로 찍는다. GitHub Pages 잠금은 저장소 비밀
  `SNAPSHOT_KEY`(사용자가 등록함) — 없으면 빌드가 멈춘다. 시험은 `tests/conftest.py` 의 시험 전용 코드로 돈다.
- **점검(check.py)**: 3번은 자체 설치형이라 체험 서버(`live.demo`) 주소를 본다. 2·4번 종료 코드 2 는 «주의»(실패 아님).

## 검토 문서(아티팩트)
- 블로그 카테고리 개편안: https://claude.ai/artifact/3bAgSSyMai7nA6F9heHPvD (v7, 사진 분리 후 페이지 32KB)
- 원본은 그 아티팩트의 `src/page.txt`, `src/rounds/*.txt`. 새 회차를 더하려면
  Artifact read(`path`)로 받아 `page.html`·`rounds/*.html` 로 되돌리고, 사진은 `img/` 에 있는 것을 그대로 둔 채
  새 사진만 `tools/review_page.py img` → `build` → 같은 url 로 publish (새 사진·새 조각만 `files` 에).
- 규칙: CLAUDE.md 10장.

## 로컬 화면 시험 (진짜 AI 없이)
```
cd <maim> && npm run build
DATA_DIR=<scratchpad>/data PORT=8793 DASHBOARD_TOKEN=owner-test-token-local \
  CLAUDE_BIN=$PWD/tools/fake-claude.mjs FAKE_SLEEP=3000 node dist/index.js &
python tools/ui_shot.py spec.json <출력폴더>     # cash-flow 의 공용 도구
fuser -k 8793/tcp                                 # 끄기 (pkill -f 는 셸까지 죽인다)
```
- init 스크립트: `localStorage.setItem('maim-dashboard-token','owner-test-token-local'); sessionStorage.setItem('maim-setup-warned','1')`
- 시험: maim `for f in tests/*.ts; do npx tsx $f; done` (10개) · cash-flow `python -m pytest -q`

## 꼭 지킬 것 (이전 세션에서 정해진 것)
- 공개 저장소에 비밀값 커밋 금지. 시험 코드에도 넣지 않는다.
- maim 의 네이버 자동 발행을 되살리자고 제안하지 않는다.
- 사용자에게 API 키를 채팅에 붙여넣지 말라고 안내한다(서버 비밀 저장소로).
- 사용자 지시: **사장님이 말하지 않은 번호는 먼저 꺼내지 않는다. 번호를 말하면 그 번호만 (CLAUDE.md 11장).**
- 브랜드 위탁 프로그램 작업은 **보류**(사용자가 홀딩).
- 예전에 채팅에 노출된 무료 이미지 사이트 키 3종은 교체 권고 상태(사용자 미처리) — 값은 적지 않는다.
- 커밋 메시지는 한국어, 기능 단위.

## 번호별 작업 (CLAUDE.md 11장 · PROGRAMS.md)
- `python -m tools.programs list | scope N | test N | guard N | doc`
- 2026-10-02 기준 `test N`: 2~16번 모두 통과. 1번만 점검 실패 — `.env` 의 KEYSERVER_URL 이 이 작업 환경에 없어서
  (사장님 PC·서버에선 있음, 고칠 것 아님).
- **새로 받은 저장소에서는 일부 시험이 실패한다(무시하기로 함, 2026-10-02 사장님 결정).** 공용 `.gitignore` 의 `data/` 규칙 때문에
  `products/*/data/` 자료(1번 기록표 샘플, 2번 단가표, 3번 키워드 수요 샘플, 14번 수수료율표, 16번 수집 자료)가 저장소에 한 번도 올라가지 않았다.
  아직 판매한 적이 없어 단가표는 필요 없고, 3번 본체는 maim 이라 수요 샘플도 필요 없다. 다시 꺼내지 않는다.
- 점검 종료 코드는 대시보드(core/runner.py)와 같게 읽는다: 0 성공 · 2 주의(결과 나옴, ⚠ 볼 것) · 그 밖 실패.

## 3번 네이버 키워드 고도화 (2026-10-02, 배포 전)
- maim 브랜치 **`claude/naver-keywords`** (기본 브랜치에 아직 안 합침). 계획·바뀐 결정: maim `docs/네이버키워드-계획.md` **0장**.
- 왼쪽 메뉴 «🔎 네이버 키워드»(주인만): 키 5개·연결 테스트 / [지금 모으기] / 보관함(골드·실버·브론즈) / 포스팅 적용 체크(기본 꺼짐).
  **글쓰기·아침 6시 작업은 네이버를 부르지 않는다** — 체크한 카테고리만 보관함을 읽는다. 사장님 걱정(글 지연)이 이것으로 풀렸다.
- 3번 개발 참고서: `products/naver-blog/docs/개발참고-maim.md` (네이버 키워드 이전 기준).
- 배포(사장님 Cloud Shell): `cd ~/maim && git fetch origin && git checkout claude/naver-keywords && git pull origin claude/naver-keywords`
  → `gcloud run deploy maim --source . --region=us-central1 --allow-unauthenticated --concurrency=80`
- 다음: 배포 후 실제 키로 연결 테스트·모으기 확인 → 고칠 것 반영 → 기본 브랜치 합치기 → 6단계(차별화 메모)·7단계(준비 자료 먼저 보기, 선택).

## 다음 할 일
0. **당분간 1~3번에만 집중.** 1~3번은 실제 대시보드를 만들고 고치고 시험한 프로그램이다.
   4~16번은 기본 세팅만 해 둔 상태(화면·시험 등 작업 없음)이고, 1~3번이 완성되면 차례로 손본다.
1. 3번(maim) 배포 후 사용자가 보내 주는 `⏱` 시간 보고 → 느린 단계가 있으면 그 단계만 손본다.
   maim 을 고칠 땐 세션에 maim 저장소를 붙인다(add_repo `parkchihong7-gif/maim`).
2. 새 요청은 CLAUDE.md 10장(적은 사용량)·11장(«N번» 은 N번만) 규칙대로.

## 사용자와 일하는 방식
- **설명은 반드시 한글로.** 영어로 정리하면 이해하지 못하신다.
- 짧게: 결론 → 결정할 것 → 할 일(명령) 순서. 수정 전에 «정리 → 허락 → 수정» 을 원하실 때가 많다.
- 대시보드 등 외부 서버(run.app)는 이 작업 환경에서 열리지 않는다 — 화면 확인이 필요하면 사용자에게 부탁한다.
