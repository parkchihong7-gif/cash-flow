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

처음이라면 대시보드의 **매뉴얼 → 관리자 매뉴얼** 을 1장부터 읽으세요.
([docs/admin-manual.md](./docs/admin-manual.md))

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
| 6 | `agency-kit/` | 자동화 대행 납품 키트 | 미착수 |
| 7 | `niche-research/` | 저가 유튜브 니치 리서치 | 미착수 |

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
