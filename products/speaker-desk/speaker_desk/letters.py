"""초청장과 계약서 — **비자 심사에 그대로 내는 문서.**

초청장은 형식이 정해져 있지 않지만, 심사에서 보는 항목은 대체로 정해져 있다.

* 초청 주체가 누구이고 실재하는가
* 언제부터 언제까지, 무엇을 하러 오는가
* 체류 비용을 누가 대는가
* 대가를 주는가 (주면 체류자격이 달라진다)

마지막 줄을 얼버무리면 안 된다. **"all expenses covered" 라고만 써 놓고 실제로
강연료를 주면** 서류와 사실이 달라진다.

계약서는 **초안**이다. 법률 자문이 아니므로 그대로 쓰지 말고 검토를 받으라고
문서 안에 적는다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from speaker_desk.roster import Event, Speaker
from speaker_desk.tax import TOTAL_RATE, compute

__all__ = ["invitation_text", "contract_text", "write_docx", "NOT_LEGAL_ADVICE"]

NOT_LEGAL_ADVICE = (
    "This is a draft prepared by an automated tool. It is not legal advice. "
    "Have it reviewed by counsel before signing. / "
    "이 문서는 자동으로 만든 초안이며 법률 자문이 아닙니다. "
    "서명 전에 반드시 검토를 받으세요."
)


def _fee_clause(speaker: Speaker) -> str:
    if not speaker.paid:
        if speaker.expenses_only:
            return ("No honorarium will be paid. The host will cover travel and "
                    "accommodation expenses only.")
        return "No honorarium or expenses will be paid."
    result = compute(speaker.fee_krw, speaker.fee_basis, speaker.treaty_rate)
    if speaker.fee_basis == "net":
        return (f"An honorarium of KRW {result.net:,} will be paid to the Speaker "
                f"net of Korean withholding tax. The host will bear the tax "
                f"(gross amount KRW {result.gross:,}).")
    return (f"An honorarium of KRW {result.gross:,} (gross) will be paid. "
            f"Korean withholding tax of approximately "
            f"{result.rate_percent}% will be deducted at source, "
            f"resulting in a net payment of about KRW {result.net:,}.")


def invitation_text(event: Event, speaker: Speaker,
                    issued: date | None = None) -> str:
    """영문 초청장. 비자 신청에 그대로 쓸 수 있는 형태."""
    issued = issued or date.today()
    arrival = speaker.arrival.isoformat() if speaker.arrival else "[arrival date]"
    departure = speaker.departure.isoformat() if speaker.departure else "[departure date]"
    host = event.host or "[Host organization]"

    lines = [
        "LETTER OF INVITATION",
        "",
        f"Date: {issued.isoformat()}",
        "",
        "To whom it may concern,",
        "",
        f"{host} cordially invites {speaker.name}"
        + (f" of {speaker.affiliation}" if speaker.affiliation else "")
        + f", a national/resident of {speaker.country}, to participate as an "
          f"invited speaker in the following event held in the Republic of Korea.",
        "",
        f"  Event      : {event.title}",
        f"  Date       : {event.event_date.isoformat()}",
        f"  Venue      : {event.venue or '[venue]'}",
        f"  Session    : {speaker.session_title or '[session title]'}",
        f"  Stay in ROK: {arrival} to {departure}"
        + (f" ({speaker.stay_days} days)" if speaker.stay_days else ""),
        "",
        "Purpose of visit",
        f"  To deliver an invited presentation at the above event.",
        "",
        "Financial arrangements",
        f"  {_fee_clause(speaker)}",
        "  Travel: " + ("covered by the host." if speaker.airfare_krw
                        else "borne by the Speaker."),
        "  Accommodation: " + ("covered by the host." if speaker.hotel_krw
                               else "borne by the Speaker."),
        "",
        "The Speaker will return to their country of residence upon completion "
        "of the event. This invitation is issued solely for the purpose of the "
        "above event and for any visa application arising from it.",
        "",
        "Sincerely,",
        "",
        f"  {event.contact_name or '[Name]'}",
        f"  {host}",
        f"  {event.contact_email or '[email]'}",
        "",
        "-" * 68,
        NOT_LEGAL_ADVICE,
    ]
    return "\n".join(lines)


def contract_text(event: Event, speaker: Speaker) -> str:
    """영문 강연 계약서 초안. **세금 조항을 흐리지 않는다.**"""
    result = compute(speaker.fee_krw, speaker.fee_basis, speaker.treaty_rate) \
        if speaker.paid else None

    lines = [
        "SPEAKER AGREEMENT (DRAFT)",
        "",
        f"Between : {event.host or '[Host organization]'} (the \"Host\")",
        f"And     : {speaker.name} (the \"Speaker\")",
        f"Event   : {event.title}, {event.event_date.isoformat()}",
        "",
        "1. Engagement",
        f"   The Speaker will deliver a presentation titled "
        f"\"{speaker.session_title or '[title]'}\" at the Event.",
        "",
        "2. Honorarium and taxes",
    ]
    if result is None:
        lines.append("   No honorarium is payable under this Agreement.")
    else:
        lines += [
            f"   {_fee_clause(speaker)}",
            "",
            "   The parties acknowledge that payments to a non-resident for "
            "personal services rendered in Korea are subject to withholding tax "
            f"at a default combined rate of {TOTAL_RATE * 100:.0f}% "
            "(income tax plus local income tax) under the Korean Income Tax Act.",
            "",
            "   A reduced rate or exemption may apply under an applicable tax "
            "treaty. To claim it, the Speaker shall provide, before the payment "
            "date, a Certificate of Residence issued by the tax authority of "
            "their country of residence, together with the prescribed "
            "application form. If these documents are not received before the "
            "payment date, the default rate will be withheld.",
        ]
    lines += [
        "",
        "3. Travel and accommodation",
        "   " + ("The Host will arrange and pay for economy-class air travel."
                 if speaker.airfare_krw else "Travel is at the Speaker's expense."),
        "   " + ("The Host will arrange and pay for accommodation."
                 if speaker.hotel_krw else "Accommodation is at the Speaker's expense."),
        "",
        "4. Materials and rights",
        "   The Speaker retains copyright in their presentation materials and "
        "grants the Host a non-exclusive licence to record the session and to "
        "distribute the recording for [scope] for [period].",
        "   [Agree the scope and period explicitly. Leaving this open is the "
        "most common source of later disputes.]",
        "",
        "5. Cancellation",
        "   If the Speaker cancels later than [N] days before the Event, "
        "[consequence]. If the Host cancels, [consequence].",
        "   [Visa refusal should be addressed here explicitly.]",
        "",
        "6. Governing law",
        "   [Jurisdiction]",
        "",
        "Signed:",
        "",
        "  ____________________          ____________________",
        "  Host                          Speaker",
        "",
        "-" * 68,
        NOT_LEGAL_ADVICE,
    ]
    return "\n".join(lines)


def write_docx(text: str, path: str | Path, title: str = "") -> Path:
    """텍스트를 docx 로. AI 생성물 표시를 문서 속성에 남긴다."""
    from docx import Document
    from docx.shared import Pt

    from shared.ai_label import add_metadata

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    document = Document()
    style = document.styles["Normal"]
    style.font.name = "Malgun Gothic"
    style.font.size = Pt(10.5)

    for index, line in enumerate(text.splitlines()):
        paragraph = document.add_paragraph(line)
        if index == 0 and line.strip():
            paragraph.runs[0].bold = True

    document.core_properties.title = title or "Speaker document"
    document.save(path)
    add_metadata(path)
    return path
