# products/

상품 단위 폴더. 각 상품은 `products/<이름>/` 으로 분리하며 최소 다음을 포함한다 (CLAUDE.md §7).

- `README.md` — 설치·사용 가이드 + 판매 문구 초안
- `requirements.txt` (또는 `package.json`)
- `.env.example` — 실제 키는 절대 커밋하지 않는다

## 계획된 상품 (2주 MVP 우선순위, CLAUDE.md §5)

| 번호 | 폴더 | 상품 | 상태 |
|---|---|---|---|
| 1 | `funnel-builder/` | 강의·전자책 퍼널 빌더 | **운영 중** |
| 2 | `hook-script/` | 후킹 대본 생성기 | **운영 중** |
| 3 | `agency-kit/` | 자동화 대행 납품 키트 3종 | 미착수 |
| 4 | `niche-research/` | 저가 유튜브 니치 리서치 | 미착수 |

번호는 대시보드 표시 순서이고 `program.yaml` 의 `number` 로 정합니다.

## 필수 — `program.yaml`

각 상품 폴더에 `program.yaml` 을 두면 통합 관리자 대시보드에 자동 등록됩니다.
규격은 `core/manifest.py`, 작성 예시는 `docs/admin-manual.md` 5장에 있습니다.
이 파일이 없으면 대시보드에 나타나지 않습니다.

## 필수 — 내부 모듈은 고유 패키지에

상품 내부 코드는 `products/<상품>/<고유_패키지>/` 안에 둡니다.

```
products/hook-script/
  cli.py                  진입점
  hook_script/            ← 고유 패키지 (밑줄 표기)
    schema.py
    generator.py
    sample_content.py
```

상품마다 `schema.py` `generator.py` 같은 이름을 쓰게 되는데, 폴더만 나누면
테스트처럼 여러 상품을 한 프로세스에 올릴 때 서로 덮어씁니다.
패키지 이름을 상품마다 다르게 두면 구조적으로 막힙니다.

## 공통 규칙

- Claude 호출은 anthropic SDK 를 직접 쓰지 말고 `shared.llm.ask()` 를 쓴다.
- 판매용 텍스트는 `shared.banned_phrases.check()` 를 통과해야 한다. 금지 문구 목록은 그 모듈에 있고,
  대체 표현은 "시간 절약 / 반복 작업 자동화 / 검증 필요" 다. (CLAUDE.md §3-2, §7)
- 모든 AI 산출물에 표시 옵션(`--ai-label`)을 기본 on으로 둔다. 텍스트는 `shared.ai_label.add_text_label()`,
  docx/pptx/xlsx 는 `shared.ai_label.add_metadata()` 를 쓴다. (인공지능기본법 2026.1.22 시행)
- 외부 플랫폼은 공식 API + OAuth만. 쿼터 초과 시 재시도가 아니라 대기.
- 콘텐츠 파이프라인은 "초안 생성 → 사람 승인 → 발행" 3단계를 유지한다.
