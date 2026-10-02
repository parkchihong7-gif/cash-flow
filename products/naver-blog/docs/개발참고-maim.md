# 3번 네이버 블로그 초안 생성기 — 개발 참고서 (다른 세션용)

> 기준: 2026-10-02 · maim 브랜치 `claude/great-brown-j376u0` 최신 커밋 `2bcf84e`
> 새 세션은 이 파일 하나로 3번의 구조·최근 수정·남은 일을 파악한다.
> **공개 저장소** — 키·토큰·서버 주소·시트 ID 는 여기에 적지 않는다.

---

## 0. 한눈에

| 항목 | 내용 |
|---|---|
| 본체 저장소 | `parkchihong7-gif/maim` (공개) · 브랜치 `claude/great-brown-j376u0` |
| 기술 | Node 20 · TypeScript(ESM) · Fastify 4 · better-sqlite3 · sharp · node-cron · luxon · zod · @google-cloud/storage |
| 도는 곳 | Google Cloud Run (안 쓸 때 잠듦) + GCS 버킷(DB·로그인·이미지 보관) + Cloud Scheduler(매일 06:00) |
| 하는 일 | 네이버 블로그 **초안**(제목·본문·태그·후킹 제목 3종·이미지 3장)을 AI(Gemini·Claude·Codex 중 택일)가 준비. **발행은 사람이 복사해서** |
| cash-flow 쪽 | `products/naver-blog/` — 판매 문서(`README.md`, `docs/admin.md`·`client.md`·`install.md`·`체험서버-세우기.md`), `program.yaml`(대시보드 카드), `check.py`(서버가 응답하는지만 확인). **코드 본체 없음** |
| 접속키 | 통합 관리자 대시보드(cash-flow)가 발급 → Apps Script 키 장부 → maim 이 `KEYSERVER_URL` 로 물어봄 (`KEYSERVER_PROGRAM=naver-blog`) |

### 세션 시작할 때
```bash
git clone -b claude/great-brown-j376u0 https://github.com/parkchihong7-gif/maim
cd maim && npm install && npm run build
for f in tests/*.ts; do npx tsx $f; done     # 실제 AI 를 부르는 test-ai-cli·test-generate-post 는 키 없으면 실패/건너뜀
```
- 푸시하려면 세션에 maim 을 `add_repo`(access: push) 로 붙인다.
- cash-flow 규칙: «3번» 작업은 `python -m tools.programs scope 3` 범위만, 커밋 앞에 `[3번]`.

### 배포 (사장님이 Cloud Shell 에서)
```bash
cd ~/maim && git pull && gcloud run deploy maim --source . --region=us-central1 --allow-unauthenticated --concurrency=80
```
- 처음 설치 때의 `--set-env-vars` 긴 명령을 **다시 쓰지 않는다** (환경변수를 통째로 덮음). 값 하나는 `gcloud run services update … --update-env-vars`.
- 메모리 **2Gi** (512Mi 에서 `/tmp` 램디스크 때문에 SQLite 가 깨진 적 있음).
- 배포 반영 확인: `/api/health` 의 `builtAt`, `db.writable: true`.

### 로컬 화면 시험 (진짜 AI 없이)
```bash
npm run build
DATA_DIR=<scratchpad>/data PORT=8793 DASHBOARD_TOKEN=owner-test-token-local \
  CLAUDE_BIN=$PWD/tools/fake-claude.mjs FAKE_SLEEP=3000 node dist/index.js &
python tools/ui_shot.py spec.json <출력폴더>     # cash-flow 의 공용 캡처 도구
fuser -k 8793/tcp                                 # 끄기 (pkill -f 는 셸까지 죽인다)
```
- 브라우저 init: `localStorage.setItem('maim-dashboard-token','owner-test-token-local'); sessionStorage.setItem('maim-setup-warned','1')`
- Cloud Run 주소(run.app)는 작업 환경에서 열리지 않는다 → 실제 화면은 사장님께 캡처를 부탁.

---

## 1. 최근 수정 (새 것부터)

| 커밋 | 날짜 | 내용 |
|---|---|---|
| `2bcf84e` | 10-02 | 로컬 화면 시험용 가짜 Claude 를 저장소에 (`tools/fake-claude.mjs`) |
| `52a1cf9` | 10-01 | 블로그 관리 표: 주제 칸을 가장 긴 주제 이름에 맞춰 자동(최소 110px·최대 320px), 남는 자리는 주제 키워드. 이름·창 크기 바뀌면 다시 맞춤. 휴대폰 카드 모양 그대로 |
| `bfa2639` | 10-01 | **포스팅 5분 안으로.** 원인: 블로그 참고 주소가 있으면 글 쓰는 한 번의 부름 안에서 주소를 횟수 제한 없이 열다 600초 초과. → 조사 단계(`pipeline/조사.ts`, 주소 열기 ≤4·검색 ≤3, 로그인 필요한 곳 안 엶, 주소 읽기 120초/소식만 75초에서 끊고 조사 없이 진행) + 글쓰기 단계(도구 없음, 300초). 블로그 메모는 자리에 하나. 분량 보강은 150초 안에서만, 사진 고르기는 남은 시간(최대 60초, 없으면 AI 없이). 상태칸에 걸린 시간(조사·글·사진·모델·도구 횟수). 상태칸 220px |
| `92c3d83` | 10-01 | 주제 칸 줄이고 주제 키워드 넓힘, 상태 «준비된 초안 있음 · 보러 가기» 한 줄 가운데 |
| `5174c25` | 10-01 | **자료 메모**: 카테고리 첫 글 때 주소를 읽은 것을 메모로 남기고, 다음 글부터는 주소를 열지 않음(7일·주소 변경 시 다시 읽음). 분량 보강은 도구 없이. **하루 포스팅 수 삭제**(켜진 카테고리마다 하루 한 편, 0 은 꺼짐으로 옮김). 상태칸 너비·높이 고정. [보러 가기] 는 본문 닫힌 채로. 📒 메모 날짜 · [🔄 다시 읽기]. 시험 `test-자료메모` |
| `2a76c55` | 10-01 | 블로그 관리 표 개편: 칸을 주제/주제 키워드/활성/포스팅 생성/상태로, [수정]·[삭제]는 주제 이름 아래. [지금 생성] 상태를 표 밖에 보관(15초 새로고침에도 유지). 단계별 문구(8초마다)·경과 시간·[글 보러 가기 →]·[이유 보기]. 수정 모드에서 ③ 주제 키워드를 맨 위로. 휴대폰은 카드 |
| `ffc2fd5` | 10-01 | 기업 블로그 업종 «대표 업종 15 × 세부 업종 5» 칩. «외식 > 카페·디저트» 꼴로 저장. 세부 주제 한 칸 40자 |
| `161a742` | 10-01 | 카테고리 참고 주소 «대표 주소 1(`main_url`) + 참고 주소 여러 줄(9줄까지, [+]/[×])». KOSIS 예시 칩 |
| `10eac89` | 09-30 경 | 카테고리·블로그 주제 세분화 (엉뚱한 글이 나오던 것) |
| `8bd618f` | | 제목 3차 — 앞머리 세부 키워드 조합 + 후킹 문구, 32~40자 |
| `ef14de5` / `ca1438a` | | 맨 위 «누가·어느 AI·연결됨» 막대, AI 끊기거나 이미지 키 0개면 글쓰기 막음 |

그 이전(총 99커밋)은 `git log --oneline` 참고. 굵직한 것: Gemini/Codex 엔진 추가, 체험 키(자리별 설정), 접속키를 통합 대시보드 장부로 일원화, GCS 상태 보존, 오류 기록.

## 2. 지금 남은 일 (사장님 확인 대기)

- 배포 후 [지금 생성] 상태칸의 **`⏱` 줄**(전체 · 조사 · 글 · 사진) 을 사장님이 보내 주시기로 함.
  - 글쓰기가 3분을 넘으면 [관리자 설정] **1단계의 모델 칸**을 `sonnet` 으로 바꿀지 사장님이 정한다.
    (엔진마다 모델은 하나 — 조사·글쓰기에 다른 모델을 쓰는 설정은 없다. 모델 칸 `#ai-model-row` 는 키 방식 엔진에서 `canChangeModel` 일 때만 보인다 → 필요하면 확인.)
  - 느린 단계가 있으면 **그 단계만** 손본다.

## 3. 꼭 지킬 것

- **네이버 자동 발행을 되살리자고 제안하지 않는다.** 시도했다가 계정 보호조치(비밀번호 강제 재설정)를 당했다. 네이버 비밀번호 칸도 없다.
- 이미지는 무료 스톡에서 **찾아 오기만**, 생성하지 않는다. 출처·라이선스 기록 유지.
- 공개 저장소에 비밀값 금지(시험 코드 포함). 사용자에게 API 키를 채팅에 붙여넣지 말라고 안내.
- 설명은 한글로, 짧게: 결론 → 정할 것 → 할 일(명령). 수정 전 «정리 → 허락 → 수정» 을 원하실 때가 많다.
- maim 코드 주석에서 추린 제약은 아래 «서버» 11절.

---

# 서버 (백엔드)

진입점 `src/index.ts`: `downloadState()` → `buildServer()` → `listen` → `startScheduler()`.
`GCS_STATE_BUCKET` 이 있으면 60초마다 `uploadState()`, SIGTERM·SIGINT 때 한 번 더 올리고 종료.

## 1. 포스팅 한 편이 만들어지는 순서

### 들어오는 길
- **수동 생성** `POST /api/run/generate` (`src/web/routes/manualRun.ts`)
  1. 체험이면 하루 상한: `todayPostCount` ≥ `체험_하루상한`(3) → 429
  2. `쓸수있나()`(src/ai/run.ts) — 끊김이면 409 `needsAi`
  3. `이미지키들().count === 0` → 409 `needsImages`
  4. `assignDirectives(1)` → `generatePost(category, directive, 기록)` → `attachImage(post, { selectTimeoutMs: 사진고르기시간(지난ms) })` → `markReady`
  5. 응답 `timing`: 조사ms, 글ms, 사진ms, 전체ms, 다시[], 모델, 조사횟수 → 화면 `⏱` 줄
- **매일 작업** `runDailyJob()` (6절)

### generatePost (`src/pipeline/generatePost.ts`)
**0) 준비** — `today`(시간대 기준), `listRecentTitles(20)`(지금 자리의 ready·published), `개인설정들([...])`(자리별 블로그 스타일)

**1) 조사** `조사하기()` (`src/pipeline/조사.ts`)
- 필요 여부:
  - `블로그읽기` — 참고 주소가 있는데 쓸 수 있는 블로그 메모가 없음
  - `카테고리읽기` — 카테고리 주소가 있는데 쓸 수 있는 카테고리 메모가 없음
  - `소식찾기` — `requires_search === 1` 또는 `topic_keyword` 있음 또는 카테고리 주소 있음
- 하나라도 참이면 `runAI({ needsSearch: true, searchOnly: !주소읽기 })` 한 번.
- 한도: 주소 읽기 `읽기한도ms`(`RESEARCH_READ_TIMEOUT_MS`, 기본 **120초**) / 소식만 `소식한도ms`(`RESEARCH_NEWS_TIMEOUT_MS`, 기본 **75초**)
- 지시문 `buildResearchPrompt()`: 주소 열기 ≤4, 검색 ≤3, 인스타·유튜브·페이스북·틱톡 안 엶, 네이버 블로그가 비어 보이면 m.blog 로 딱 한 번. 답은 `{"blog_brief","brief","news"}` JSON.
- 실패해도 예외 없이 빈 자료 + `실패` 사유로 글쓰기로 넘어감. 자르기: blog_brief 1500 · brief 2000 · news 1500자.
- 메모 저장은 결과 **80자 이상**일 때만(`기록.첫글 = true`): `블로그메모적기()`, `메모적기(id, text, 메모지문)`.

**2) 글쓰기 (도구 없음)**
- `buildBlogProfileBlock({주소는메모로: true, ...})` + `buildPostPrompt(category, directive, today, recentTitles, block, {블로그메모, 카테고리메모, 최근소식, 조사실패})`
- `runAI({ prompt, timeoutMs: 글쓰기한도ms = 300초 })` → `parsePostResponse()`
- 실패: 시간 초과(`시간초과인가`)면 **다시 부르지 않고** 오류(문구가 «1단계 모델 칸에 sonnet» 을 안내). JSON 파싱 실패면 «순수 JSON만» 꼬리로 1회 재시도(`다시.push("JSON")`).
- 분량이 `최소분량()` 미만: 시작 **150초(`보강마감ms`) 전**이면 `buildExpandPrompt()` 로 1회 보강(조사 없이, 더 길 때만 채택), 지났으면 `"분량(시간 없어 건너뜀)"`.
- 제목: `제목고르기(title, title_variants, keyword)` — 규칙 어긴 제목을 후보로 교체(AI 재호출 없음).
- 저장: `insertDraftPost` → `markCategoryUsed`

**3) 이미지** `attachImage()` (`src/pipeline/attachImage.ts`)
- 한 편 목표 `한편목표ms` = **300초**. `사진고르기시간(지난ms)` = 300 − 지난 − 20초, 15초 미만이면 0(AI 없이 검색 순서), 상한 60초.
- `searchWithFallback(query, candidatesDir, max(count*2, 6), page)` (`src/images/searchImages.ts`): Unsplash·Pexels·Pixabay 병렬, 원래 검색어·변형 최대 5회 → 모자라면 `GENERIC_FALLBACK_TERMS`.
- `selectBestImages()` (`src/images/selectImage.ts`): `runAI({ readDir })` 로 AI 가 사진을 보고 고르고 alt 도 받음. 실패 시 앞에서부터.
- `processImage()` (`src/images/processImage.ts`): sharp 760px 폭 · 4:3 · `fit: cover` · `position: attention` · 밝기 1.03 · 채도 1.08 · JPEG 88.
- `recordImageDownload`(채택분만) → `addPostImages`. 기본 3장. 재생성은 `append=true`, page 1~3 무작위.
- 이미지가 실패해도 글은 `markReady`, 응답에 `imageError`, `오류적기("이미지")`.

### 자료메모 (`src/pipeline/자료메모.ts`)
- 주소는 한 번 읽고 메모로. `메모유효일 = 7`.
- **블로그 메모**(자리마다 하나, 모든 카테고리 공용): 개인설정 `blog_links_brief` 에 `{text, sig, at}`. 지문 `블로그메모지문(blog_links)` = sha1 앞 16자. `쓸블로그메모()` 는 지문 다르거나 7일 지나면 null.
- **카테고리 메모**: `categories.research_brief`·`brief_sig`·`brief_at`. 지문 `메모지문(category)` = sha1(name, prompt_hint, main_url, reference_urls). `쓸메모()`. 수동 초기화 `POST /api/categories/:id/brief-reset`.

### directives (`src/pipeline/directives.ts`)
- `assignDirectives(n)`: 인사말 오프닝은 n편 중 1편만, 텐션·페르소나 섞어 배정. `targetLength = 최소 + 최소×(0.3~0.6)`, `sectionCount` 3~5.

## 2. AI 엔진 (Gemini · Claude · Codex)

- 정의 `src/ai/engines.ts` `ENGINES`, 실행 `src/ai/run.ts` `runAI()`. 모두 **CLI 자식 프로세스**(Dockerfile 이 세 CLI 전역 설치).
- 작업 폴더는 빈 `DATA_DIR/ai-work/<id>` (소스가 AI 에게 새지 않게).
- 엔진 선택: env `AI_ENGINE` → 설정 `ai_engine` → 기본 claude. 모르는 id 는 claude. `엔진고르기()` 가 `ai_engine_changed`(from/to/at) 기록.
- 모델 `엔진모델()`: 설정 `claude_model`/`gemini_model`/`codex_model` → env `<ID>_MODEL` → CLI 기본. **엔진마다 하나.**
  - 화면의 «1단계» = [관리자 설정] «1단계. 글 쓸 AI 고르고 로그인»(엔진·키·모델 칸·연결 테스트). «2~4단계» = Unsplash·Pexels·Pixabay 키.
- 키 `엔진키()`: 대시보드 저장값(`anthropic_api_key`/`gemini_api_key`/`openai_api_key`) → env. 자식 프로세스 환경에만. 저장 전 `키검사()`(공백·비 ASCII·20자 미만).

| 엔진 | 부르는 법 | 특이점 |
|---|---|---|
| Claude | `-p <prompt> --output-format json --permission-mode acceptEdits [--model]`. `readDir` 면 `--allowedTools Read --add-dir`, 검색만 `WebSearch`, 검색+주소 `WebSearch WebFetch`, 그 밖 `--tools ""` | 봉투 `result`, `is_error`. `속사정읽기()` 로 `num_turns`·`modelUsage`(출력 토큰 가장 많은 모델). 서버 로그인 가능(`.claude`) |
| Gemini | `-p --output-format json [-m]`, 검색·파일이면 `--approval-mode yolo`, env `GEMINI_CLI_TRUST_WORKSPACE=true` | **API 키 필수**(로그인 불가). `집차리기()` 로 깨끗한 HOME + `.gemini/settings.json`. 답은 `response` |
| Codex | `exec <prompt> --json [-m] --skip-git-repo-check --output-last-message <tmpfile>` | 파일 우선, 없으면 JSONL `agent_message`/`output_text`. 로그인 `.codex` |

### 실패 처리
- 기본 타임아웃 `AI_TIMEOUT_MS` 또는 **600초** → SIGKILL, `err.시간초과 = true`.
- ENOENT → «설치돼 있지 않습니다», 끊김 기록.
- 비정상 종료 → `멈춘까닭()`. `로그인풀림` 정규식(401·unauthorized·/login·token expired 등)이면 `상태적기(false)` 로 다음 글 막음. 시간 초과·답 모양 오류는 끊김으로 안 적음.
- 상태 `ai_status` = `{v:2, engine, ok, at, why}` — **실제로 돈 엔진 id** 로 기록.
- `쓸수있나()`: 끊김이면 ① 버킷 로그인 다시 맞추기(`로그인맞추기`) ② 2분 지났으면 «ok» 핑(45초) ③ 그래도 끊김이면 막음.
- 로그인 엔진은 부르기 전 `로그인맞추기(home, freshLogin)`(20초 간격 제한). 연결 테스트 `POST /api/settings/test-claude` 30초, `freshLogin: true`.

## 3. 프롬프트 규칙 (`src/claude/`)

- **`제목규칙.ts`(3차)**: [앞머리 세부 키워드 3~4낱말] + [후킹 문구], 공백 포함 **32~40자**. `keyword` 칸에 앞머리, 제목은 그것으로 시작. 후킹은 멈추는 이유 8가지(돈·시간·관계·지위·안전·호기심·비교·손실회피) 중 하나, 숫자 권장. 금지: 서술형 어미(물음표 질문은 허용), 낚시 꼬리말(내막·전말·충격·경악·반전·논란), 따옴표·꺾쇠, !·? 2개 이상, «요즘·최근·진짜·역대급» 시작, «무조건·100%·수익 보장». 코드 검사 `제목재보기()`(24~45자, 12낱말 이하, 키워드 2~6낱말·제목 시작 일치), `제목고르기()`. 키워드는 첫 문단 1번, 본문 3~5회.
- **`검색노출규칙.ts`(`buildSeoRuleBlock`)**: 근거 통계(구글 50.4%·네이버 이미지검색 24.6%·통합검색 15.1%·PC 76.9%). 첫 2~3문장에 키워드+요지, 이모지 소제목 2개 이상에 키워드 변형, Q&A 구간 1곳(결론부터), 수치·연도·지역(지어내지 않음), 반복 3~5회, 태그 10개 중 절반 이상 «[소재]+[양식·방법·조건·후기·가격·순위]».
- **`styleRules.ts`(`buildStyleRulesBlock`)**: 페르소나, 오프닝 5종, 텐션 3종, targetLength·sectionCount. **마크다운 금지**(`#`·`*`·`■`·`▶`), 소제목·목록은 이모지(👉 ✔️ 📌 🔥), 네이버식 구어체(~해요). 출력: title, keyword, content(제목 반복 금지), image_query(**영어** 1개), tags(10개, #, 첫 태그는 keyword 붙여 쓴 것). `parseResponse.ts` `sanitizeContent()` 가 금지 기호 제거.
- **`blogProfile.ts`**: 프리셋 6종(balanced·friendly_review·polite_info·emotional_essay·humorous_casual·expert_analysis), 사용자 프리셋은 `custom_`. `BLOG_TOPIC_GROUPS`, `BUSINESS_INDUSTRY_GROUPS`(15×5), `LINK_KINDS`. 세부 주제·주소 각 10개. `buildBlogProfileBlock()` = «블로그 전역 설정 — 카테고리 설명보다 우선»(유형·세부 주제·브랜드(과장 금지)·참고 주소(`주소는메모로` 면 «직접 열지 마라»)·프리셋·보강).
- **`promptBuilder.ts`**: `buildPostPrompt`(topic_keyword «최우선 지시», must/exclude, [조사 자료], 최근 제목 겹침 금지, title_variants 3종: 조건·기준형 / 방법·절차형 / 후기·비교형), `buildExpandPrompt`, `buildPreviewPrompt`, `buildImageSelectPrompt`.
- **`parseResponse.ts`**: zod `PostResponseSchema`(content ≥500자, 태그 3~15), `다듬기()`, `읽기쉽게()`(zod 오류 한국어), `parseJsonLoose`(코드펜스·잡문 제거).

## 4. DB (`src/db/index.ts`, SQLite)

- `journal_mode = DELETE`, `foreign_keys = ON`. `_migrations` 기록이 있어도 CREATE TABLE 대상이 없으면 다시 실행(`표가다있나`).
- **칸 추가는 SQL 파일이 아니라 `칸붙이기()`**(PRAGMA 확인 후 ALTER). categories: `owner_key, must_keywords, exclude_keywords, reference_urls, main_url, keyword_keep, daily_count, research_brief, brief_sig, brief_at` · posts: `owner_key` · keyserver_sessions: `key1`. `daily_count = 0` 은 `active = 0` 으로 옮김.

| 마이그레이션 | 내용 |
|---|---|
| 001_init | categories, posts(draft/ready/published/failed), settings, 기본 카테고리 9개 |
| 002 | posts.image_paths_json, requires_search=1 |
| 003 | posts.image_alts_json |
| 004 | categories.topic_keyword |
| 005·006 | access_codes (옛 자체 코드, 지금은 안 씀) |
| 007 | posts.title_variants_json |
| 008 | image_downloads (출처·라이선스) |
| 009 | keyserver_sessions(token, key2, remote_token, holder_name, role, device_label, checked_at) |
| 010 | seat_settings(owner_key, key, value) — 자리별 스타일 |
| 011 | error_log(owner_key, role, stage, category, message) |

repositories(`src/db/repositories/`): `categories.ts`(CRUD·`메모적기`·`markCategoryUsed`), `posts.ts`(`insertDraftPost`·`markReady/Published/Failed`·`addPostImages`·`listHistory`·`listRecentTitles`, 모두 `owner_key` 로 거름), `settings.ts`(`getSetting/setSetting`, 프리셋, 이미지 키·`이미지키들()`, `최소분량()` 기본 3000·범위 800~6000, `개인설정/개인설정들/개인설정정하기`), `tenants.ts`(`listTenants`·`purgeTenant`·`todayPostCount`·`체험자리_차려주기`(맛보기 카테고리 3개)), `keyserverSessions.ts`, `errorLog.ts`(`오류적기`·`최근오류`), `imageDownloads.ts`.

## 5. 인증·접속

- **`DASHBOARD_TOKEN`**(`src/web/server.ts` onRequest 훅): 설정됐을 때만 `/api/*` 보호. 예외 `/api/health`·`/api/auth/redeem`·`/api/auth/heartbeat`·정적 파일. 토큰은 `x-dashboard-token` / `Authorization: Bearer` / `?token=`. 마스터면 주인, 세션 토큰은 `findSession` → role 이 정확히 `"client"` 일 때만 체험 자리(`ownerKey: key1`), 나머지는 주인. **훅은 콜백(`done`) 꼴** — async 면 AsyncLocalStorage 자리가 사라짐. 오류 응답은 `비밀빼고()` 로 가림.
- **keyserver**(`src/keyserver.ts`): Apps Script 장부, `program=KEYSERVER_PROGRAM` 필수, 20초. `validateKeyPair(key1, key2)`, `checkSession(key2, remoteToken)`(화면이 1분마다 heartbeat). 실패 사유 `not_configured`·`unreachable`·`bad_answer`(HTML = Apps Script 배포 권한이 «모든 사용자» 아님).
- **1차키 = 사람(자리), 2차키 = 기기**(PC·노트북·휴대폰). 같은 2차키로 다른 기기 → 먼저 기기 잠김.
  - `/api/auth/redeem`: 대문자화, IP당 1분 10회, 마스터면 `master: true`, 체험이면 `체험자리_차려주기(key1)`.
  - `/api/auth/heartbeat`: `unreachable`·`bad_answer` 는 살아 있음, `not_found/suspended/expired` 면 세션 닫고 `purgeTenant(key1)`, `session_replaced` 는 세션만 닫음.
- **tenancy**(`src/tenancy.ts`): `자리에서`·`지금`·`지금주인`·`체험인가`·`주인자리인가`. 크론은 주인 자리(ownerKey `''`). 체험은 AI 설정·이미지 키·예약·미리보기·프리셋 추가삭제·`/api/run/daily` 불가(403).
- **seat settings**: blog_type, blog_topic, posting_direction_preset, posting_direction_refinement, min_length, blog_topics, blog_links, blog_brand, blog_links_brief. 주인은 `settings`, 체험은 `seat_settings`. 체험은 주인 값을 빌리지 않음(예외 `min_length`). 보강 지시 ≤2000자.

## 6. 스케줄러 (`src/scheduler/`)

- `cron.ts`: node-cron `0 6 * * *`. Cloud Run 에서는 잠들어 안 돎 → **Cloud Scheduler** 가 `POST /api/run/daily`(헤더 x-dashboard-token) 06:00 Asia/Seoul. 작업 이름 `${K_SERVICE||"maim"}-daily`, 명령은 `GET /api/schedule` 의 `setupCommand`.
- `예약.ts`: `발행시각 = "06:00"` **고정**. `daily_cap` 기본 3, 0~10. `schedule_order` sequential / random(기본) / least_used. 켜진 카테고리마다 1편, 상한까지. `last_daily_run`.
- `dailyJob.ts` `runDailyJob()`: 돌았다고 적기 → `죽은자리치우기()` → 이미지 키 없으면 오류 기록 후 중단 → 오늘목록 → 카테고리마다 generatePost(keyword_keep 아니면 topic_keyword 비움) → attachImage → markReady. 하나 실패해도 다음으로.
- `시간예상.ts`: `기다려주는초 = 1800`(Scheduler 30분), 한 편 `180 + 최소분량/1000×60`초, 70% 초과 `tight`, 100% 초과 `over`.
- `죽은자리치우기.ts`: key1 의 **모든 기기**가 `not_found/suspended/expired` 일 때만 `purgeTenant`.

## 7. API

| Method | Path | 설명 |
|---|---|---|
| GET | /api/health | DB 표 수·쓰기 테스트·builtAt·timezone·keyserver 설정 여부 |
| POST | /api/auth/redeem | 마스터 토큰 또는 1차+2차키로 세션 발급 |
| GET | /api/auth/heartbeat | 기기 세션 확인, 죽은 키면 자리 삭제 |
| GET | /api/auth/whoami | 마스터 여부·이름·역할 |
| GET·POST | /api/categories | 목록·생성 |
| PUT·DELETE | /api/categories/:id | 수정·삭제 |
| POST | /api/categories/:id/brief-reset | 카테고리 메모 초기화 |
| GET·PUT | /api/schedule | 예약 조회(미리보기·lastRun·setupCommand·timing) / 변경(주인만) |
| GET | /api/queue | draft·ready 글 |
| GET | /api/history | 최근 글(limit, 기본 50) |
| POST | /api/run/daily | 매일 작업(Scheduler, 체험 403) |
| POST | /api/run/generate | 카테고리 1개로 글 1편 + 이미지 |
| GET | /api/ai/status | 엔진·연결 상태·이미지 키 현황 |
| POST | /api/ai/check | `쓸수있나()` 로 다시 확인 |
| GET | /api/errors | 최근 오류(주인 전체, 체험 자기 것) |
| GET | /api/posts/:id/image/:index | 이미지(없으면 GCS 에서 받아옴) |
| POST | /api/posts/:id/mark-published | 발행 완료 표시 |
| POST | /api/posts/:id/regenerate-image | 이미지 3장 추가 |
| GET·PUT | /api/settings | 설정(비밀값 가림, 자리 기준) / 저장(체험은 스타일 칸만) |
| GET·PUT | /api/settings/ai | 엔진 목록·현재 엔진·모델 / 엔진 고르기(주인만) |
| POST | /api/settings/test-claude | 연결 테스트(30초) |
| POST | /api/settings/preview-post | 예시 포스팅(900자, 120초, 주인만) |
| GET·POST | /api/settings/posting-direction-presets | 프리셋 목록·추가(주인만) |
| DELETE | /api/settings/posting-direction-presets/:id | `custom_` 만 삭제(주인만) |
| GET | /api/image-downloads/csv | 이미지 출처 CSV |
| GET | /api/tenants · POST /api/tenants/purge | 체험 자리 목록·삭제(마스터만) |

## 8. 환경변수 (이름·용도만)

| 이름 | 용도 |
|---|---|
| HOST / PORT | 기본 127.0.0.1:4173 |
| TIMEZONE | 기본 Asia/Seoul |
| DATA_DIR | DB·이미지·home (Cloud Run 은 /tmp 아래) |
| GCS_STATE_BUCKET | 상태 동기화 버킷 (있으면 HOME=DATA_DIR/home) |
| DASHBOARD_TOKEN | 마스터 토큰 |
| KEYSERVER_URL / KEYSERVER_PROGRAM | 접속키 장부 / 프로그램 구분(기본 naver-blog) |
| UNSPLASH_ACCESS_KEY / PEXELS_API_KEY / PIXABAY_API_KEY | 이미지 키(대시보드 저장값 우선) |
| CLAUDE_BIN | claude 경로(가짜 Claude 끼울 때) |
| AI_ENGINE | 엔진 강제 |
| CLAUDE_MODEL / GEMINI_MODEL / CODEX_MODEL | 설정이 비었을 때 모델 |
| ANTHROPIC_API_KEY / GEMINI_API_KEY / OPENAI_API_KEY | 엔진 키(대시보드 저장값 우선) |
| AI_TIMEOUT_MS | runAI 기본 600000 |
| RESEARCH_READ_TIMEOUT_MS / RESEARCH_NEWS_TIMEOUT_MS | 조사 한도 120000 / 75000 |
| K_SERVICE | Cloud Run 서비스 이름 |
| FAKE_SLEEP / FAKE_MODE_FILE | 가짜 Claude 전용 |

## 9. GCS 상태 보존 (`src/persistence/gcsState.ts`)

- FUSE 마운트 대신 시작 때 내려받고 주기적으로 올림(SQLite 잠금 때문).
- `downloadState()`: 버킷 전체 중 `generated/`(이미지)와 `SKIP_PREFIXES`(`cash-flow/` — 통합 대시보드 몫, **절대 건드리지 않음** · `home/.claude/backups/`) 제외, 8개씩. 이미지는 `downloadFileIfMissing(rel)` 로 필요할 때만.
- `uploadState()`(60초마다 + 종료 시): DB 는 `getDb().backup()` 스냅샷으로만(실패하면 안 올림), `-journal/-wal/-shm` 제외, 바뀐 파일만. `home/`(로그인)은 `ifGenerationMatch` — 412 면 버킷이 더 새 것이니 거꾸로 받음.
- `로그인맞추기(폴더, 꼭)`: AI 부르기 직전 `home/<.claude|.codex>/` 에서 바뀐 것만 받음(20초 간격). 서버 재시작 불필요.

## 10. 시험·도구

실행: `npx tsx tests/<파일>`

| 파일 | 내용 |
|---|---|
| test-제목규칙.ts | `제목재보기`/`제목고르기` (오프라인) |
| test-답다듬기.ts | 답 모양 차이 견디기 |
| test-자료메모.ts | 조사→글쓰기 2단계, 메모 7일·지문·재사용 (가짜 Claude) |
| test-자리별설정.ts | seat_settings 자리 분리 |
| test-카테고리세분화.ts | must/exclude/주소/블로그 정보가 지시문까지 |
| test-AI상태.ts | 끊김 막기·풀기, v2 엔진 id |
| test-로그인보존.ts | 새 로그인이 옛 서버 업로드에 안 덮이기 (가짜 버킷) |
| test-ai-cli.ts | 실제 CLI 점검 `AI_ENGINE=… npx tsx …` |
| test-generate-post.ts | 실제 claude 로 1편 `[카테고리이름]` |
| test-image-pipeline.ts | 이미지 검색·선택·가공 |

- `tools/fake-claude.mjs`: «자료만 빠르게» 가 지시문에 있으면 조사 JSON, 아니면 일부러 엉성한 고정 글. `FAKE_SLEEP`(ms), `FAKE_MODE_FILE` 이 `broken` 이면 JSON 아닌 답.
- `tools/건지기.py`: 깨진 SQLite 에서 읽히는 줄만 새 DB 로 (`python3 건지기.py 깨진.db 새.db`).

## 11. 코드 주석에서 추린 제약

- 자동 발행 없음 · 메모리 2Gi · Scheduler 30분 한도(하루 기본 3·최대 10편) · 06:00 고정
- 한 편 5분: 조사 120/75초 → 글 300초 → 보강은 150초 전에만 → 사진 고르기 최대 60초
- 시간 초과는 재시도 안 함, JSON 오류만 1회
- AI 작업 폴더는 빈 방 · HOME 은 코드(`config.ts`)가 정함 · Gemini 는 서버 로그인 불가
- 역할을 모르면 주인 (`!== "admin"` 으로 봤다가 주인이 체험으로 밀린 적 있음)
- `session_replaced`·`unreachable` 은 절대 삭제 사유 아님
- 이미지 키 0개면 생성 막음(수동 409, 매일 작업 건너뜀)
- topic_keyword 는 1회용(`keyword_keep = 1` 이면 유지)
- DB 는 `backup()` 스냅샷으로만 올림 · `cash-flow/` 접두사 건드리지 않음
- ALTER 는 SQL 파일에 쓰지 않음(`칸붙이기()`) · Fastify 인증 훅은 async 금지
- `npm run build` 가 public·migrations 를 dist 로 복사하고 `dist/BUILD_AT` 기록
- Dockerfile: node:20-slim + claude-code·gemini-cli·codex 전역 설치, 4173, `CMD node dist/index.js`

---

# 화면 (프런트엔드)

파일: `src/web/public/index.html`(916줄) · `app.js`(2476줄) · `style.css`(1826줄). 빌드 없는 순수 JS.
클릭은 `document` 위임 리스너가 `data-action` 으로 가름(app.js 1106–1466 큰 분기 + 기능별 리스너). 함수 이름은 영어·한글 혼용.

## 1. 화면 구성

### 공통
- 사이드바 `.sidebar-nav-item[data-action="switch-view"][data-view=…]`: `home` 🏠 홈 · `categories` 📁 블로그 관리 · `drafts` 📝 포스팅 · `history` 📜 발행 이력 · `settings` ⚙️ 관리자 설정 · `guide` 📖 사용법. 체험이면 `#nav-settings-label` 이 «내 글 스타일».
- `switchView(view)`(~990): `section[data-view-panel]` 의 hidden. settings 로 가면 `refreshSettings()` → `refreshSchedule()` → `refreshEngines()` → `refreshErrors()`, home 이면 `renderHome()`.
- `.sidebar-foot`: `#sidebar-who`(roleLabel, settings 를 한 번 열어야 채워짐), **[나가기]** `logout` — confirm → 토큰 지우고 reload(서버 호출 없음).

### 로그인 관문 `#gate` (index.html 15–40)
- `#gate-key1`, `#gate-key2`, `#gate-msg`, `#gate-go`(Enter 도). `openGate(먼저할말)` 은 `gatePromise` 하나로 한 번만 뜸. `redeemToken` → `POST /api/auth/redeem`. 들어오면 `방금들어옴 = true`.
- 오류 문구 `로그인_오류(res, data)`. 401(api) 또는 하트비트 401 때 열림(서버 `data.error` 를 먼저 보여 줌 — 다른 기기 로그인 등).

### 맨 위 상태 막대 `#ai-bar`
- `AI막대그리기()`(~1987) → `GET /api/ai/status` → 전역 `AI상태`.
- 👤 «사장님(주인)»/«체험 회원» · 🤖 `s.label` · 연결: ✅(시각) / ⚠️ 연결 안 됨(주인에게 [AI 설정으로 가기]) / ⏳(주인에게 [연결 테스트]) · 🖼️ 이미지 키 `count/total`(0개면 주인에게 [이미지 키 넣기]).
- 색: `ai-bar-ok`/`bad`/`wait`(style.css 1612–1620). 이미지 키 0개면 `bad`.
- 주인만: `s.why`(300자), 3일 안 엔진 변경 이력. 준비 안 됐으면 `준비안내창(s)`(sessionStorage 로 세션당 1회). `s.ok === null` 이면 한 번 자동 `test-claude`.
- **`AI되나()`**: 글 만들기·이미지 재생성·하루치 만들기 전 관문. ok false 면 `POST /api/ai/check`, 이미지 키 0개면 `AI안내창(…,"images")`.
- `AI설정으로()` / `이미지설정으로()` 스크롤 + `.flash` 2.4초.

### 홈
- `renderHomeStats()`: `#stat-today-count`, `#stat-ready-count`(3건 미만 권장 안내), `#stat-active-categories`, `#stat-ai-status`(문구 «Claude» 고정 — 막대와 따로 계산).
- `renderActivityFeed()`(최근 6건), `renderHomeHistoryTable()`(최근 5건, [오류 보기] alert). 전용 API 없음.

### 블로그 관리
- 표 `#category-table`(2절). `refreshCategories()` → `GET /api/categories`.
- 단추: ✏️ `edit-category` → `카테고리폼채우기(c)`(0.35초 뒤 `topicKeyword` 포커스) · 🗑 `delete-category`(**confirm 없이 삭제**) · 🔄 `brief-reset`(메모 있을 때만, confirm) · 활성 `toggle-active` → PUT + `refreshSchedule()` · `generate`.
- 꼬리표 `카테고리꼬리표(c)`: `+함께 N`, `−빼기 N`, `🔗 N`, `📒 메모 M/D`(`메모있나(c)` 7일 이내).
- **지금 하루치 만들기** `#batch-box` `run-batch` → `하루치만들기(단추)`: `AI되나()` → `GET /api/schedule` preview → 항목마다 `POST /api/run/generate` 차례로, `#batch-log` 에 ✅/❌. 진행 중 `beforeunload`. 예고 `하루치예고()`(random 이면 이름 숨김). 서버 `/api/run/daily` 는 안 씀.
- **카테고리 폼** `#category-form`: ① name ② promptHint ③ topicKeyword + keywordKeep ④ mustKeywords ⑤ excludeKeywords ⑥ mainUrl + `#ref-url-rows`(`참고주소줄그리기/읽기`, 9줄, `data-ref-del`). 예시 칩 `.cf-chips[data-target][data-mode]`(set/add/url/line). 저장 PUT/POST + `requiresSearch:true` 항상.
  - 수정 모드: `#category-form-box.editing`(③ 칸 `order:-1` 맨 위, 나머지 흐림), 표 `tr.is-editing`/`tr.is-dim`(기준 `editingFormId`). [취소] → `카테고리폼비우기()`.
  - 옛 흔적: `save-category`·`cancel-edit-category`·`editingCategoryId` 는 사실상 죽은 코드(단 `refreshAll()` 이 `editingCategoryId` 를 봄).

### 지금 생성 상태창 (표 «상태» 칸 `td.gen-status[data-status-for=id]`)
- 상태는 표 밖 `생성상태` Map(`{state, start, end, 예상, postId, title, msg, timing}`) — 다시 그려도 유지.
- [지금 생성]: `AI되나()` → `running`(예상: 메모 있으면 200초, 없으면 270초) → `POST /api/run/generate` → `imageError` 면 `imgwarn`, 아니면 `done`, `timing` 저장, `refreshQueue()`. `timing.첫글` 이면 `refreshCategories()`.
- 그리기 `상태칸(카id)`, 다시 그리기 `상태칸다시그리기(카id)`(단추 «쓰는 중…» disabled).
- 모습: 없음 → ready 초안 있으면 `gs-idle` «🗂️ 준비된 초안 있음 [보러 가기 →]», 없으면 `gs-none` «-» · `running` `gs-run`(단계 초기/중간/마지막, 경계 15%·70%, 문구 `쓰는중말` 8초마다, `.gs-time` «N분 M초째 · 보통 3~5분») · `done` «🎉 짠! 완성됐어요» [글 보러 가기 →] · `imgwarn` «글은 완성!» «📷 사진만 못 붙였어요» · `error` «😢 앗, 이번엔 못 썼어요» [이유 보기] → `오류창(…)`.
- **⏱ 시간 줄**(done·imgwarn): `⏱ 전체 · 조사 X · 글 Y · 사진 Z`, 조사가 한도로 건너뛰면 ⚠. 마우스 올리면 title 로 도구 횟수·모델·📒 메모 생성/사용·`다시:` 사유. `timing` 없으면 `end - start`. `걸린시간(ms)`, `지난시간(ms)`.
- `초안으로가기(postId)`: drafts 로 가서 카드에 스크롤 + `.flash`, 본문은 접힌 채.

### 포스팅 (준비된 초안, `#ready-list`)
- `refreshQueue()` → `GET /api/queue`(끝나면 블로그 관리 표도 다시 그림).
- 카드 `.post-card`: 머리 [카테고리] [제목 `toggle-content`] [복사하기 `copy-title-variant`] + 글자 수. 후킹 제목 3종(각 [복사하기]). [전체 복사하기] `copy`(`buildCopyText`), [이미지 재생성] `regenerate-image`, [발행 완료로 표시] `mark-published`.
- 품질 체크리스트 `buildQualityChecklist`(화면에서만): 1500자 이상 · 금지 서식 없음 · 첫 태그 키워드 본문 2회 이상 · 최근 제목과 Jaccard 0.5 미만(`findSimilarHistoryTitle`).
- 이미지 `/api/posts/:id/image/:idx?token=…`, [이미지 복사] `copy-image`(canvas→PNG→`ClipboardItem`), [대체텍스트 복사] `copy-alt`.

### 발행 이력
- `refreshHistory()` → `GET /api/history?limit=30`, `#history-table`(ID/카테고리/제목/상태/발행완료 시각/에러). [📥 이미지 출처 내려받기 (CSV)] `download-image-log`.

### 관리자 설정 / 내 글 스타일
- `자리표시하기(s)` 가 제목·부제를 바꿈. 체험만 `#trial-style-note`(하루 한도 `#trial-daily-limit`, [다 정했어요 → 글 만들러 가기]).
- **1) AI 커넥트 연결**(`data-owner-only`), `#setup-progress` «4단계 중 N단계 완료»(`updateSetupProgress`)
  - **1단계** `.setup-step[data-step="claude"]`: `#ai-who`, `#ai-engines` 라디오 `ai_engine`(`refreshEngines()` → `GET /api/settings/ai`). 엔진 바꿀 때 **confirm 필수** → `PUT /api/settings/ai`. `엔진명령보이기()`: 로그인 방식(Claude·Codex) `#ai-way-login`(명령 4줄 `로그인명령들(것)`, 버킷 이름 `저장통()`) / 키 방식(Gemini) `#ai-way-key`([저장] `save-ai-key`).
  - **모델 칸** `#ai-model-row`: `모델칸보이기(것)`, 키 방식에서 `modelSetting`·`canChangeModel` 이 있을 때만 보임. `#ai-model-input`, [저장] `save-ai-model` → `PUT /api/settings`.
  - [연결 테스트] `test-claude`, [매뉴얼 보기] `toggle-manual`, 명령 [복사] `copy-code`.
  - **2~4단계 이미지 키**: `#unsplash-key-input`·`#pexels-key-input`·`#pixabay-key-input`, `save-setting[data-key][data-input]`.
- **2) 블로그 주제 설정**(주인·체험): `blog_type` 즉시 저장, 주제 칩 `#topic-chips`(최대 `catalog.maxTopics`, 직접 추가 `#topic-add-input`), 기업이면 `#brand-box`, 주소 줄 `#link-rows`. [주제·주소 저장] `save-blog-profile` → `PUT /api/settings {blog_topics, blog_links, blog_brand}`(JSON 문자열). 최소 글자수 `#min-length-input` `save-min-length`, 시간 경고 `#timing-warn-length`.
- **3) 포스팅 방향**: [최종 포스팅 기준] `toggle-final-direction`, 프리셋 `#preset-grid`(`select-preset`), 주인만 프리셋 추가 `save-new-preset`·삭제 `delete-preset`, 보강 `save-posting-direction`, 주인만 [예시 포스팅 보기] `preview-post`.
- **🧯 최근 오류**(주인): `#error-log-list`, `refreshErrors()` → `GET /api/errors`, [전부 복사] `copy-errors`.
- **4) 포스팅 예약**(주인): `#schedule-alarm`(lastRun 없거나 36시간 넘으면 `setupCommand` 보임), 06:00 고정, 하루 건수 `#schedule-cap-input`(최대 10) `save-daily-cap`, 차례 `schedule_order`, 시간 경고 `#timing-warn-cap`.

### 사용법
- 정적 HTML, 단계 0~8 + FAQ. `data-owner-only`/`data-trial-only` 로 가림. 7·8단계 주인 전용.

### 모달
- `#error-dialog` `오류창(제목, 내용)`: 읽기 전용 textarea + 한국 시각, [복사](`execCommand` 대체), 배경 누르면 닫힘.
- `#ai-dialog` `AI안내창(말, 어디, 제목)`: 주인은 [확인] 으로 설정 위치로 이동, 체험은 [확인]만.

## 2. 블로그 관리 표 칸·너비

```html
<colgroup><col class="c-topic"><col class="c-kw"><col class="c-active"><col class="c-gen"><col class="c-status"></colgroup>
<tr><th>주제</th><th>주제 키워드</th><th>활성</th><th>포스팅 생성</th><th>상태</th></tr>
```

| 칸 | td | 내용 | 너비 |
|---|---|---|---|
| 주제 | `td.cat-topic` | 이름·꼬리표·`.cat-tools`(수정/삭제/다시 읽기) | **JS 자동** `주제칸맞추기()` |
| 주제 키워드 | `td.cat-keyword` | `.kw-pill`, `🔁 유지` | auto (남는 자리 전부) |
| 활성 | `td.cat-active` | «● 활성»/«○ 꺼짐» | 84px |
| 포스팅 생성 | `td.cat-gen` | [지금 생성] | 104px |
| 상태 | `td.gen-status` | `상태칸()` | **220px** |

- **CSS 는 덮어쓰기가 층층이** (뒤가 이김): 1763–1768 «수정사항-1»(fixed, 24%/18%/92/112/auto) → 1801–1802 «-2»(15.6%/26.4%) → 1812–1822 «-3»(키워드 auto, 84/104, `col.c-status{width:220px}`) → 1823–1825 «-4»(`col.c-topic{width:150px}` 기본, 실제는 JS inline).
- `주제칸맞추기()`(app.js 418–431): canvas `measureText` 로 가장 긴 이름 → `clamp(110, 폭, 320) + 22px` 를 `col.c-topic` 에. 700px 이하면 비움. `renderCategories()` 끝과 `resize` 에서.
- 상태칸 높이: `.gs{min-height:3.3em}`, 실행 중 문구 2줄 clamp, `.gs-time` nowrap(done/warn 만 줄바꿈).
- 겹칠 수 있는 옛 규칙: `.gen-status{min-width:230px;max-width:340px}`(1719행). fixed 에서는 col 220px 가 이기지만 너비 고칠 때 같이 볼 것. CSS 주석의 «하루 포스팅 수» 칸은 이미 없음.
- 휴대폰(≤700px, 1750–1760·1785–1799): thead 숨김, 줄마다 2열 카드, `td[data-label]::before` 라벨, `gs-none` 칸 숨김.

## 3. 주인 / 체험 차이

- 서버 판단 `주인자리인가()` = `!체험인가()`. 주인: 마스터 토큰 또는 대시보드에서 `role:"admin"` 으로 발급된 키. 그 밖은 체험/고객(`client`).
- 화면 신호: `/api/settings` 의 `seat`("owner"/"trial") → `body.is-trial`. CSS `body.is-trial [data-owner-only]` / `body:not(.is-trial) [data-trial-only]` 숨김(1597·1625행).

| 항목 | 주인 | 체험 |
|---|---|---|
| 설정 메뉴 | 관리자 설정 | «내 글 스타일» + 안내 카드 |
| AI 연결·이미지 키 | 보임 | 숨김(서버 403) |
| 주제·방향 | 바꿈 | 자기 자리에만 저장(스타일 칸 외 섞이면 403) |
| 프리셋 추가·삭제 / 예시 포스팅 | 가능 | 숨김·403 |
| 최근 오류 / 예약 설정 | 보임 | 숨김 |
| 지금 생성 | 제한 없음 | 하루 3건(429) |
| 첫 화면 | 홈 | 방금 들어왔거나 스타일 미저장이면 settings 로 한 번 |

## 4. 브라우저 저장소

| 저장소 | 키 | 쓰임 |
|---|---|---|
| localStorage | `maim-dashboard-token` | 세션 토큰(헤더 `x-dashboard-token`, 이미지·CSV 는 `?token=`) |
| sessionStorage | `maim-setup-warned` | 주인 준비 안내창 세션당 1회 |

나머지(`생성상태`, `claudeTestedOk`, `expandedPostIds`)는 메모리 — 새로고침하면 사라짐.

## 5. 주기·타이머

| 주기 | 무엇 |
|---|---|
| 15초 | `safeRefreshAll()` → history·queue·(편집 중 아니면) categories·하루치예고 → `renderHome()` (app.js 1486) |
| 60초 | 하트비트 `GET /api/auth/heartbeat` (401 이면 관문) |
| 60초 | `AI막대그리기()` |
| 4초 | `running` 상태칸만 다시 그림 |
| 1.5초 / 2.4초 | 복사됨 표시 / `.flash` 해제 |

## 6. 오류 표시

- `api(path, options)`(153–195): body 있을 때만 JSON 헤더(빈 body 에 붙이면 Fastify 400). 401 이면 토큰 바뀐 경우 재시도, 아니면 관문 → 다시 보냄. 그 밖은 `Error(data.error)` + `.status`·`.data`.
- 위임 핸들러 catch(1442–1458): `generate` 중이면 `생성상태` 를 error 로, `needsImages`/`needsAi` 면 `AI안내창`, generate·regenerate-image 는 **복사 가능한 `오류창()`**(휴대폰 alert 는 글을 못 고름), 그 밖은 alert.
- 칸 아래 직접 적기: `#ai-key-state`, `#ai-model-state`, `#min-length-state`, `#blog-profile-state`, `#batch-state`/`#batch-log`.
- 서버 기록: 생성·이미지 오류는 서버에도(체험 포함) → 주인 [🧯 최근 오류].
- 꼴: `.setup-warn`/`.setup-good`/`.muted`, `시간경고칠하기(id, t)`(over/tight), `굵게()`, 사용자 문자열은 항상 `escapeHtml()`.

## 화면별 API

| 화면 | API |
|---|---|
| 로그인 | `POST /api/auth/redeem`, `GET /api/auth/heartbeat` |
| 상태 막대 | `GET /api/ai/status`, `POST /api/ai/check`, `POST /api/settings/test-claude` |
| 블로그 관리 | `/api/categories`(GET·POST·PUT·DELETE·brief-reset), `GET /api/schedule`, `POST /api/run/generate` |
| 포스팅 | `GET /api/queue`, 이미지, `regenerate-image`, `mark-published` |
| 발행 이력 | `GET /api/history?limit=30`, `GET /api/image-downloads/csv` |
| 설정 | `/api/settings`(GET·PUT), `/api/auth/whoami`, `/api/settings/ai`, `test-claude`, `preview-post`, 프리셋, `/api/schedule`, `/api/errors` |
| 화면에서 안 씀 | `POST /api/run/daily`, `/api/tenants`, `/api/tenants/purge`, `/api/health` |
