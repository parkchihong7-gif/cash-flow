# 프로그램 번호표 (자동 생성 — 손으로 고치지 마세요)

`python -m tools.programs doc` 이 각 `products/*/program.yaml` 에서 만듭니다.
번호 작업 규칙은 CLAUDE.md 11장.

| 번호 | 이름 | 폴더 | 자기 시험 | 본체 |
|---|---|---|---|---|
| 1 | 공인중개사 기출문제 | `products/exam-drill/` | `test_exam_drill.py` | parkchihong7-gif/gongin-jungsagsa-exam |
| 2 | 시니어 영상 비용 견적·절감기 | `products/senior-video/` | `test_senior_video.py` | 이 저장소 |
| 3 | 네이버 블로그 초안 생성기 | `products/naver-blog/` | `test_naver_blog.py`, `test_naver_blog_live.py` | parkchihong7-gif/maim |
| 4 | 해외 연사 초청 관리 | `products/speaker-desk/` | `test_speaker_desk.py` | 이 저장소 |
| 5 | 퍼널 빌더 | `products/funnel-builder/` | `test_funnel.py` | 이 저장소 |
| 6 | 후킹 대본 생성기 | `products/hook-script/` | `test_hook_script.py` | 이 저장소 |
| 7 | 전자책 원고 생성기 | `products/ebook-gen/` | `test_ebook.py` | 이 저장소 |
| 8 | 강의 슬라이드 생성기 | `products/lecture-deck/` | `test_lecture_deck.py` | 이 저장소 |
| 9 | 크몽 상세페이지 카피 생성기 | `products/kmong-copy/` | `test_kmong_copy.py` | 이 저장소 |
| 10 | n8n 워크플로 JSON 생성기 | `products/n8n-gen/` | `test_n8n_gen.py` | 이 저장소 |
| 11 | 공구 정산 엑셀 자동 생성기 | `products/groupbuy-ledger/` | `test_groupbuy.py` | 이 저장소 |
| 12 | 수익 시뮬레이터 | `products/income-sim/` | `test_income_sim.py` | 이 저장소 |
| 13 | 노션 템플릿 기획·설명서 생성기 | `products/notion-template-kit/` | `test_notion_kit.py` | 이 저장소 |
| 14 | 제휴 상품 매칭 로직 | `products/affiliate-matcher/` | `test_affiliate_matcher.py` | 이 저장소 |
| 15 | 자동화 대행 납품 키트 | `products/agency-kit/` | `test_agency_kit.py` | 이 저장소 |
| 16 | 니치 리서치 | `products/niche-research/` | `test_niche_research.py` | 이 저장소 |

## 공용 자산 (여러 번호가 함께 씀 — 번호 작업 중 고치려면 먼저 확인)

| 무엇 | 어디 | 실행·시험 |
|---|---|---|
| 통합 관리자 대시보드 | `dashboard/` (FastAPI·템플릿) | `python -m dashboard` → http://127.0.0.1:8000 |
| 공용 엔진 | `core/` (등록부·실행기·접속키·콘솔·메일 등) | `pytest tests/` |
| 공용 도우미 | `shared/` (AI 표시·금지 문구·LLM) | `pytest tests/test_shared.py` |
| 접속키 서버 (Apps Script) | `server/keyserver.gs`, `web/admin.html` | `node --test server/tests/keyserver.test.js` · `pytest tests/test_keyserver_web.py` |
| 생성물 | `web/programs.js`, `server/keyserver.bundle.gs` | `python -m tools.gen_programs_js` · `python -m tools.build_keyserver` |
| 대시보드 스냅샷 | `dashboard/snapshot.py` | `python -m dashboard.snapshot --demo --single` |
| 교육자료 PPT | `tools/build_training_decks.js` 외 | README 참고 |
| 배포 | `deploy/`, `Dockerfile`, `render.yaml` | `deploy/cloudrun.md` |
| 검토 문서·화면 확인 | `tools/review_page.py`, `tools/ui_shot.py` | CLAUDE.md 10장 |
| 전체 시험 | `tests/` | `python -m pytest -q` (오래 걸림 — 공용을 고쳤을 때만) |

- **1번 본체** — parkchihong7-gif/gongin-jungsagsa-exam (GitHub Pages). 시험: `그 저장소를 세션에 붙인 뒤(add_repo) 확인 — 이 저장소에는 판매 문서·점검(check.py)만 있다`
- **3번 본체** — parkchihong7-gif/maim (Cloud Run) · 브랜치 claude/great-brown-j376u0. 시험: `cd <maim> && npm run build && for f in tests/*.ts; do npx tsx $f; done`. 배포: `cd ~/maim && git pull && gcloud run deploy maim --source . --region=us-central1 --allow-unauthenticated --concurrency=80  (사장님이 Cloud Shell 에서)`
