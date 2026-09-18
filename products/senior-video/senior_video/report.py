"""견적서 — 사장님께 그대로 보여 드리는 문서."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from senior_video.estimate import Estimate
from senior_video.savings import Saving
from senior_video.senior import Finding, SPEC_SUMMARY, grade
from senior_video.upload import AUDIT_NOTE, MAX_UPLOADS_PER_DAY, UPLOAD_UNITS, uploads_possible

__all__ = ["write_report", "DISCLAIMER"]

DISCLAIMER = (
    "이 견적은 공개 요금표를 기준으로 **추정한 값**입니다. 실제 청구액은 각 "
    "서비스의 사용량 화면이 기준이고, 요금제는 예고 없이 바뀝니다. "
    "수익이나 조회수를 예측하지 않습니다."
)


def _won(value: float) -> str:
    return f"{value:,.0f}원"


def write_report(est: Estimate, savings: list[Saving], findings: list[Finding],
                 out_dir: str | Path, note: str = "") -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    plan = est.plan
    quota = uploads_possible(plan.monthly_videos)

    lines = [f"# 시니어 영상 제작 비용 견적 — {today}", "",
             f"> {DISCLAIMER}", "",
             f"**{plan.title}** · 월 {plan.monthly_videos}편 · "
             f"대본 {plan.script_chars:,}자 · 이미지 {plan.images}장", ""]
    if note:
        lines += [f"> {note}", ""]

    lines += ["## 한 줄", ""]
    if est.free:
        lines.append("지금 고르신 조합은 **어디에도 청구서가 날아오지 않습니다**"
                     "(무료 구간·무료 스톡·직접 작성). 전기값 말고는 안 듭니다. "
                     "대신 시간이 듭니다.")
    else:
        lines.append(f"영상 한 편에 **{_won(est.per_video)}**, "
                     f"월 {plan.monthly_videos}편이면 **{_won(est.per_month)}**, "
                     f"1년이면 {_won(est.per_year)} 입니다.")
        biggest = est.biggest
        if biggest:
            lines.append("")
            lines.append(f"가장 큰 줄은 **{biggest.label}** 로 "
                         f"편당 {_won(biggest.won)}, 전체의 {est.share(biggest)}% 입니다. "
                         f"줄이시려면 여기부터 보셔야 합니다.")
    lines.append("")

    lines += ["## 항목별", "",
              "| 항목 | 계산 | 편당 | 월 | 비중 |", "|---|---|---:|---:|---:|"]
    for line in est.lines:
        lines.append(
            f"| {line.label} | {line.detail} | {_won(line.won)} | "
            f"{_won(line.won * plan.monthly_videos)} | {est.share(line)}% |")
    lines.append(f"| **합계** |  | **{_won(est.per_video)}** | "
                 f"**{_won(est.per_month)}** | 100% |")
    lines += ["", f"단가 기준일: {est.asof}", ""]

    lines += ["## 줄일 수 있는 것", ""]
    if not savings:
        lines.append("더 줄일 것이 없습니다. 이미 무료 조합입니다.")
    else:
        lines += ["**공짜 절감은 하나뿐입니다.** 나머지는 무언가를 내줍니다. "
                  "무엇을 내주는지 같이 적었습니다.", "",
                  "| 무엇 | 월 절감 | 연 절감 | 대가 |", "|---|---:|---:|---|"]
        for item in savings:
            mark = "" if item.senior_safe else " ⚠"
            lines.append(f"| {item.title}{mark} | {_won(item.monthly_won)} | "
                         f"{_won(item.yearly_won)} | {item.cost} |")
        lines += ["", "⚠ 표시는 **시니어 시청자에게 불리해지는** 선택입니다. "
                  "돈은 아끼지만 이 채널이 노리는 시청자가 떠날 수 있습니다.", ""]
        top = savings[0]
        lines += [f"가장 큰 것은 '{top.title}' 로 연 {_won(top.yearly_won)} 입니다. "
                  f"{top.how}", ""]

    lines += ["## 시니어 시청자 규격", "",
              f"권장값: {SPEC_SUMMARY}", "", grade(findings), "",
              "| 항목 | 권장 | 적으신 값 | 판정 |", "|---|---|---|---|"]
    for finding in findings:
        value = finding.value if finding.value not in (None, "") else "—"
        mark = {"ok": "✓", "warn": "⚠", "na": "·", "advice": "→"}[finding.status]
        lines.append(f"| {finding.rule.title} | {finding.rule.recommended} | "
                     f"{value} | {mark} {finding.label} |")
    lines.append("")
    warns = [item for item in findings if item.warn]
    if warns:
        lines += ["### 왜 이게 중요한가", ""]
        for item in warns:
            lines += [f"**{item.rule.title}** — {item.rule.why}", ""]

    lines += ["## 업로드 한도", "",
              f"유튜브 Data API 는 하루 {10_000:,} 유닛인데 **업로드 한 번이 "
              f"{UPLOAD_UNITS:,} 유닛**입니다. 그래서 하루 "
              f"**{MAX_UPLOADS_PER_DAY}편**이 끝입니다.", "",
              f"- 계획하신 월 {quota['monthly']}편 = 하루 {quota['per_day']}편 "
              f"({quota['units_per_day']:,} 유닛)",
              f"- 쿼터 안에 {'들어갑니다' if quota['fits'] else '**안 들어갑니다**'}",
              f"- API 로 올릴 수 있는 최대: 월 {quota['max_monthly']}편", "",
              f"> {AUDIT_NOTE}", ""]

    lines += ["## 올리기 전에", "",
              "**사람이 승인한 것만 올라갑니다.** 이 프로그램에는 승인 없이 올리는 "
              "경로가 없습니다.", "",
              "유튜브는 2025년 7월부터 사람 손이 안 닿은 양산형 콘텐츠를 수익 창출에서 "
              "빼는 방향으로 정책을 정리했습니다. 비용을 아끼자고 검수를 건너뛰면 "
              "채널 자체가 위험해집니다.", "",
              "1. 대본과 자막을 **소리 내어 한 번 읽어 보세요**. 어색한 문장이 바로 걸립니다",
              "2. 이미지 라이선스를 확인하세요",
              "3. `python cli.py approve <번호> --by <이름>` 으로 승인합니다",
              "4. 그 뒤에 올립니다", ""]

    path = out_dir / f"estimate_{today}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
