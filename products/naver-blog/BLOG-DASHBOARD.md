# 3번 네이버 블로그 초안 생성기 (maim) — 작업 안내서

> **이 파일은 사본입니다.** 원본은 maim 저장소의 `CLAUDE.md` 입니다. 고칠 때는 원본을 고치고 여기로 복사하세요.
> **3번 작업을 하려면 세션을 maim 저장소로 열거나, 이 세션에 maim 을 붙이세요**(add_repo `parkchihong7-gif/maim`).

> 새 세션은 이 파일을 먼저 읽는다. 블로그 포스팅 대시보드의 **본체 코드는 이 저장소(maim)에만 있다.**
> 통합 관리자 대시보드(`parkchihong7-gif/cash-flow`)에는 판매 문서·점검·접속키 발급만 있다.
> 마지막 갱신: 2026-10-02

## 0. 먼저 알아 둘 것
- **운영 주소(체험 서버)**: https://maim-1048530680370.us-central1.run.app/ — Google Cloud Run(us-central1), 서비스 이름 `maim`.
- **기본 브랜치**: `claude/great-brown-j376u0` (이 저장소의 유일한 브랜치. 커밋 64개)
- **실제 데이터(카테고리·초안·설정·접속 기록)는 git 에 없다.** 서버의 SQLite 파일이 GCS 저장통(`GCS_STATE_BUCKET`)에
  동기화돼 있다. 새 세션은 코드는 보지만 **사장님이 넣은 카테고리·글 내용은 볼 수 없다.** 필요하면 사장님께 화면을
  캡처하거나 내용을 붙여 달라고 한다. (이 작업 환경에서는 run.app 주소가 열리지 않는다.)
- **설명은 반드시 한글로**, 짧게: 결론 → 결정할 것 → 할 일. 고치기 전에 «정리 → 허락 → 수정» 을 원하실 때가 많다.
- 커밋 메시지는 한국어, 기능 단위. 끝에 `Co-Authored-By`·`Claude-Session` 줄.

## 1. 이 프로그램이 하는 일
네이버 블로그에 올릴 **글(제목·본문·태그·후킹 제목 3종) + 무료 스톡 사진 3장(대체텍스트 포함)** 을 AI 가 준비한다.
**발행은 사람이 한다** — 복사해서 네이버 에디터에 붙여넣는다. 자동 발행은 네이버 계정 보호조치를 맞아 걷어냈다.
**자동 발행을 되살리자고 제안하지 않는다.** 이미지는 찾아 오기만 하고 생성하지 않는다.

## 2. 화면 (왼쪽 메뉴, `src/web/public/index.html` · `app.js` · `style.css`)
| 메뉴 | 하는 일 |
|---|---|
| 🏠 홈 | 오늘 할 일, 숫자 요약, 맨 위 상태 막대(누가·어느 AI·연결됨) |
| 📝 포스팅 | 준비된 초안 카드: `[카테고리] [제목 N자] [복사하기]` / 후킹 제목 3종 / 전체 복사 / 이미지 재생성 / 발행 완료로 표시 / 품질 체크 |
| 📁 블로그 관리 | 카테고리 표 `주제 / 주제 키워드 / 활성(눌러 켬·끔) / 포스팅 생성 / 상태(220px)` + 새 카테고리 폼(①주제 ②설명 ③주제 키워드[계속 유지] ④함께 들어갈 말 ⑤빼야 할 말 ⑥대표 주소·참고 주소[+/×]) + [지금 하루치 만들기] |
| 📜 발행 이력 | 발행한 글과 이미지 출처 CSV |
| ⚙️ 관리자 설정 | 1) AI 연결(Claude·Gemini·Codex, 모델, 연결 확인) 2) 블로그 주제(개인/기업, 기업은 대표 업종 15 × 세부 5, 브랜드 정보, 참고 주소) 3) 말투·방향 프리셋 4) 본문 최소 글자수 · 포스팅 예약(아침 6시 고정, 하루 총 건수, 차례) · 무료 이미지 키 3종 · 최근 오류 |
| 📖 사용법 | 단계별 안내 |

- [지금 생성] → 상태칸에 초기·중간·마지막 귀여운 문구(8초마다) → 완료 시 `⏱ 전체·조사·글·사진` 시간과 [글 보러 가기 →].
- 하루 포스팅 수 칸은 없앴다 — **켜진 카테고리마다 하루 한 편**, 전체는 하루 총 건수까지.
- 수정 모드: ③ 주제 키워드를 맨 위로 강조, 다른 칸·다른 줄은 흐리게.

## 3. 글 한 편이 만들어지는 길 (목표 5분 안)
`src/pipeline/generatePost.ts`
1. **조사** (`pipeline/조사.ts`) — 도구(WebSearch/WebFetch)를 켜고 주소 열기 최대 4번·검색 3번. 주소를 읽으면 120초,
   최근 소식만이면 75초에서 끊고 **조사 없이 다음으로**. 인스타·유튜브 등 로그인 필요한 곳은 안 연다.
2. **자료 메모** (`pipeline/자료메모.ts`) — 읽은 것을 메모로 남겨 다음 글부터 주소를 다시 안 연다.
   블로그 참고 주소 메모는 **자리에 하나**(설정 `blog_links_brief`), 카테고리 주소 메모는 카테고리마다
   (`research_brief`·`brief_sig`·`brief_at`). 주소·설명이 바뀌거나 7일이 지나거나 [🔄 다시 읽기] 하면 새로 읽는다.
3. **글쓰기** — 도구 없이 자료·메모만 보고 쓴다(한도 300초). 자료에 없는 최신 숫자는 지어내지 않게 지시.
   분량 보강은 150초 안에서만, 검색 없이 «받은 글을 늘리기».
4. **제목** (`claude/제목규칙.ts`) — 앞머리 세부 키워드 조합 3~4낱말 + 후킹 문구, 32~40자. 어긋나면 후보로 교체.
5. **사진** (`pipeline/attachImage.ts`, `images/`) — Unsplash·Pexels·Pixabay 검색 → AI 가 고름(전체 5분에서 남은 시간,
   최대 60초, 없으면 검색 순서대로) → 가공. 무료 이미지 키가 0개면 글쓰기를 막는다.
6. 지시문: `claude/promptBuilder.ts`(키워드 뜻 좁히기·빼야 할 말·자료), `blogProfile.ts`(블로그 유형·업종·브랜드·참고 주소),
   `styleRules.ts`, `검색노출규칙.ts`. 답 읽기: `parseResponse.ts`(자잘한 모양 차이는 다듬어 받는다).

## 4. AI 엔진 (`src/ai/engines.ts`, `run.ts`)
- Claude(Claude Code CLI, Pro 이상 구독) · Gemini(gemini CLI, API 키 무료 등급) · Codex(codex CLI). **기본은 Claude.**
- 엔진을 바꾸면 확인창. 연결 상태는 `ai_status`(엔진별, 2분 지나면 다시 확인)로 적고, 끊겼으면 409 로 막고 설정 화면으로 보낸다.
- 로그인 폴더는 GCS 와 맞춘다(`persistence/gcsState.ts` — 바뀐 파일만 올리고, 세대 번호로 덮어쓰기 방지).

## 5. 자리(주인·체험)와 접속
- `src/tenancy.ts` — 요청마다 «누구의 자리인가»(AsyncLocalStorage). 체험 키는 자기 카테고리·글·글 스타일만 본다.
- 접속: 주인은 `DASHBOARD_TOKEN`, 체험 회원은 통합 대시보드에서 발급한 접속키(키 서버 `KEYSERVER_URL`)로 들어온다
  (`web/routes/auth.ts`, `keyserver.ts`). 체험은 하루 3편, 기본 1일 뒤 자리가 지워진다(`scheduler/죽은자리치우기.ts`).
- 자리별 설정: `seat_settings` 표, `db/repositories/settings.ts` 의 `개인설정키` 목록.

## 6. 코드 지도
```
src/index.ts            서버 시작          src/config.ts        설정·경로
src/web/server.ts       Fastify            src/web/routes/      auth·categories·posts·queue·history·settings·manualRun·tenants·imageDownloads
src/db/index.ts         SQLite + 칸붙이기  src/db/migrations/   001~011 SQL
src/db/repositories/    categories·posts·settings·tenants·errorLog·imageDownloads·keyserverSessions
src/pipeline/           generatePost·조사·자료메모·attachImage·directives
src/claude/             promptBuilder·blogProfile·제목규칙·parseResponse·styleRules·검색노출규칙
src/ai/                 engines·run      src/images/  searchImages·selectImage·processImage
src/scheduler/          dailyJob(아침 6시)·예약·시간예상·cron·죽은자리치우기
src/persistence/        gcsState         tools/  fake-claude.mjs(시험용 가짜 AI)·건지기.py
```
주요 API: `POST /api/run/generate`(지금 생성, 응답에 `timing`) · `POST /api/run/daily` · `GET/POST/PUT/DELETE /api/categories`
· `POST /api/categories/:id/brief-reset` · `GET /api/queue` · `POST /api/posts/:id/regenerate-image|mark-published`
· `GET/PUT /api/settings`·`/api/settings/ai` · `GET /api/ai/status` · `POST /api/ai/check` · `GET /api/errors` · `GET/PUT /api/schedule`

## 7. 환경변수 (이름만 — 값은 서버 비밀 설정에. **채팅·저장소에 값을 적지 않는다**)
`DASHBOARD_TOKEN` `KEYSERVER_URL` `KEYSERVER_PROGRAM` `GCS_STATE_BUCKET` `DATA_DIR` `AI_ENGINE` `AI_TIMEOUT_MS` `CLAUDE_BIN`
`UNSPLASH_ACCESS_KEY` `PEXELS_API_KEY` `PIXABAY_API_KEY` `TIMEZONE` `HOST` (시험용: `RESEARCH_READ_TIMEOUT_MS` `RESEARCH_NEWS_TIMEOUT_MS`)

## 8. 시험·확인·배포
```
npm install && npm run build
for f in tests/*.ts; do npx tsx $f; done          # 자동 시험 10개 (가짜 AI 로 돈다)
# 화면 확인 — 진짜 AI 없이
DATA_DIR=/tmp/maim-data PORT=8793 DASHBOARD_TOKEN=owner-test-token-local \
  CLAUDE_BIN=$PWD/tools/fake-claude.mjs FAKE_SLEEP=3000 node dist/index.js &
#   브라우저 init: localStorage.setItem('maim-dashboard-token','owner-test-token-local')
#   cash-flow 저장소의 tools/ui_shot.py 로 숫자 검사·캡처. 끄기: fuser -k 8793/tcp  (pkill -f 는 셸까지 죽인다)
```
배포는 **사장님이 Cloud Shell 에서**:
```
cd ~/maim && git pull && gcloud run deploy maim --source . --region=us-central1 --allow-unauthenticated --concurrency=80
```

## 9. 지킬 것
- 네이버 자동 발행·자동 로그인 금지(제안도 하지 않는다). 공식 API·OAuth 만.
- 사람 검수 3단계(초안 → 사람 확인 → 사람이 발행). 과장 광고 문구(금지 문구 목록: cash-flow `shared/banned_phrases.py`) 금지. AI 생성물 표시 기본 on.
- 표절 유도 금지 — 참고 주소는 사실·숫자 보강용, 문장은 베끼지 않게 지시돼 있다.
- 비밀값(키·토큰·시트 ID·키 서버 주소) 커밋 금지. 예전에 채팅에 노출된 무료 이미지 키 3종은 교체 권고 상태(사용자 미처리).

## 10. 최근 작업 (2026-09-23 ~ 10-02)과 남은 일
- 09-23~24: 엔진 3종 안정화, 모델 선택, 체험 칸막이, 아침 6시 고정·하루치 만들기, 최소 글자수 설정
- 09-29~30: 제목 «세부 키워드 조합 + 후킹», 검색 노출 구조, 체험 키별 글 스타일, AI 연결 상태 막대·막기, 이미지 키 0개 막기, Codex 401 수정
- 10-01: 카테고리·블로그 주제 세분화(업종 15×5, 대표·참고 주소), 블로그 관리 표·상태창·수정 모드 개편,
  하루 포스팅 수 삭제, **조사/글쓰기 분리로 5분 안**, 주제 칸 자동 너비
- 검토 문서(사진 포함): https://claude.ai/artifact/3bAgSSyMai7nA6F9heHPvD
- **남은 일**: 배포 후 사장님이 보내 주는 `⏱`(조사·글·사진 시간) 보고 → 느린 단계만 손본다. 글쓰기가 3분 넘으면
  [관리자 설정] 1단계 모델을 `sonnet` 으로 바꿀지 사장님이 정한다.

## 11. 통합 관리자 대시보드와의 관계 (cash-flow 저장소)
- 3번 = `products/naver-blog/` (판매 문서 `README.md`·`docs/`, 점검 `check.py` — 체험 서버 주소를 두드림, `program.yaml`).
- 접속키 발급·메일 발송은 통합 대시보드 [접속키] 탭. 체험 키 메일에만 위 주소가 나가고, 판매 키에는 설치 안내서가 간다.
- 두 저장소를 같이 다룰 때는 세션에 둘 다 붙인다(add_repo).
