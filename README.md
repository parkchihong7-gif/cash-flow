# cash-flow

부업 프로그램 제작·판매 프로젝트. 작업 지침과 조사 결과 전문은 [`CLAUDE.md`](./CLAUDE.md)에 있다.

## 구조

```
CLAUDE.md          작업 브리프 (조사 결과 · 금지 사항 · 우선순위)
shared/            모든 상품이 함께 쓰는 공통 기반
  config.py        .env 로드, 경로 상수
  llm.py           Claude API 호출 래퍼 (ask)
  ai_label.py      AI 생성물 표시 (인공지능기본법 제31조)
  banned_phrases.py 판매용 텍스트 금지 문구 검사
products/          상품별 폴더 (상품 1개 = 폴더 1개)
tests/             단위 테스트
```

## 설치

```bash
pip install -r requirements.txt
cp .env.example .env     # ANTHROPIC_API_KEY 를 채운다
```

## 확인

```bash
pytest tests/
python -c "from shared.llm import ask; print(ask('한 줄로 답해','안녕'))"
```

## shared 사용법

```python
from shared.llm import ask
from shared.ai_label import add_text_label, add_metadata
from shared.banned_phrases import assert_clean

# Claude 호출 — json_mode 는 ```json 펜스를 벗기고 파싱, 실패 시 1회 재시도
plan = ask("너는 기획자다", "3가지 항목을 JSON 배열로", json_mode=True)

# 판매용 텍스트는 파일로 쓰기 전에 반드시 검사
copy = assert_clean(ask("너는 카피라이터다", "상세페이지 도입부"))

# AI 생성물 표시 (기본 on)
copy = add_text_label(copy)          # 텍스트 끝에 고지 한 줄
add_metadata("outputs/보고서.docx")   # docx/pptx/xlsx 메타데이터
```

## 규칙

- Claude 호출은 anthropic SDK 를 직접 쓰지 말고 `shared.llm.ask()` 를 쓴다.
- 판매용 텍스트는 `shared.banned_phrases.check()` 를 통과해야 한다. (CLAUDE.md §3-2, §7)
- 모든 AI 산출물에 표시를 기본 on 으로 붙인다. (CLAUDE.md §3-5)
- 비밀키는 `.env` 에 두고 커밋하지 않는다.
