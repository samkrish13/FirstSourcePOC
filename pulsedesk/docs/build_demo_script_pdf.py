#!/usr/bin/env python3
"""Build PulseDesk_Demo_Script.pdf — 5-min panel walkthrough (2 pages)."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUT = Path(__file__).resolve().parent / "PulseDesk_Demo_Script.pdf"
ACCENT = colors.HexColor("#0B6E4F")
DARK = colors.HexColor("#111827")
MUTED = colors.HexColor("#4B5563")
LINE = colors.HexColor("#E5E7EB")
SOFT = colors.HexColor("#F3F4F6")


def styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=16,
            textColor=DARK,
            alignment=TA_CENTER,
            spaceAfter=2,
        ),
        "sub": ParagraphStyle(
            "sub",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            textColor=MUTED,
            alignment=TA_CENTER,
            leading=11,
            spaceAfter=6,
        ),
        "h": ParagraphStyle(
            "h",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=10,
            textColor=ACCENT,
            spaceBefore=7,
            spaceAfter=2,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            textColor=MUTED,
            leading=10.5,
            spaceAfter=1,
        ),
        "say": ParagraphStyle(
            "say",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=8,
            textColor=DARK,
            leading=10.5,
            leftIndent=4,
            spaceBefore=1,
            spaceAfter=3,
            backColor=SOFT,
            borderPadding=3,
        ),
        "cell": ParagraphStyle(
            "cell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            textColor=DARK,
            leading=9.5,
        ),
        "cell_h": ParagraphStyle(
            "cell_h",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            textColor=DARK,
            leading=9.5,
        ),
    }


def p(text: str, style) -> Paragraph:
    return Paragraph(text, style)


def bullets(items: list[str], s) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(i, s["body"]), leftIndent=4, bulletColor=ACCENT) for i in items],
        bulletType="bullet",
        start="•",
        leftIndent=8,
        spaceBefore=0,
        spaceAfter=2,
    )


def add_footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(36, 26, A4[0] - 36, 26)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#9CA3AF"))
    canvas.drawString(36, 14, "PulseDesk · 5-min panel demo script")
    canvas.drawRightString(A4[0] - 36, 14, f"{doc.page}")
    canvas.restoreState()


def build() -> Path:
    s = styles()
    story = []

    story.append(p("PulseDesk — 5-minute demo script", s["title"]))
    story.append(
        p(
            "Live: https://pulsedesk-firstsource.streamlit.app &nbsp;|&nbsp; "
            "Local: <font face='Courier'>cd pulsedesk && streamlit run app.py</font><br/>"
            "Italic = say out loud &nbsp;·&nbsp; Bullets = clicks &nbsp;·&nbsp; Skip §3 if the room is tight",
            s["sub"],
        )
    )

    data = [
        [
            Paragraph("Role", s["cell_h"]),
            Paragraph("Login", s["cell_h"]),
            Paragraph("Password", s["cell_h"]),
        ],
        [
            Paragraph("Agent", s["cell"]),
            Paragraph("p.sharma@pulsedesk.demo", s["cell"]),
            Paragraph("agent", s["cell"]),
        ],
        [
            Paragraph("Tech Lead", s["cell"]),
            Paragraph("r.mehta@pulsedesk.demo", s["cell"]),
            Paragraph("lead", s["cell"]),
        ],
    ]
    t = Table(data, colWidths=[70, 300, 70])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), SOFT),
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(t)

    story.append(p("0 · Frame the problem (30 sec)", s["h"]))
    story.append(
        p(
            "“Telecom BPO desks get mixed inbound mail — billing, outages, escalations, SIM/port, "
            "plans, FAQs. Agents invent next steps by hand: slow, inconsistent, hard to audit.”",
            s["say"],
        )
    )
    story.append(
        p(
            "“PulseDesk proves AI can classify, run the right multi-step playbook, and leave a Case Log — "
            "with a human gate when confidence is low.”",
            s["say"],
        )
    )

    story.append(p("1 · Agent login → Process (40 sec)", s["h"]))
    story.append(
        bullets(
            [
                "Sign in <b>p.sharma / agent</b> → Process",
                "Point at sidebar + Mine / Unassigned / All + workbench",
            ],
            s,
        )
    )
    story.append(
        p(
            "“Left rail is the work inbox. Right side is the case workbench — same metaphor as a real ops console.”",
            s["say"],
        )
    )

    story.append(p("2 · Golden path — REQ-001 billing (90 sec)", s["h"]))
    story.append(
        bullets(
            [
                "Load demo sample → <b>REQ-001</b> → Load → <b>Run playbook</b>",
                "Walk spine: Classification → Why/entities → Branch map → Timeline → Draft → Queue/48h → Checklist",
            ],
            s,
        )
    )
    story.append(
        p(
            "“Billing dispute — hold, ticket, draft, 48h follow-up. Six playbooks; Billing is lit. "
            "Every branch must hit response, route, follow-up, and log.”",
            s["say"],
        )
    )

    story.append(p("3 · Second branch contrast (40 sec) — optional", s["h"]))
    story.append(
        bullets(
            ["Load <b>REQ-002</b> or <b>REQ-003</b> → Run → different queue / SLA vs callback"],
            s,
        )
    )
    story.append(
        p(
            "“Different ops paths — classification alone isn’t enough; the remediation spine is the value.”",
            s["say"],
        )
    )

    story.append(p("4 · Human-in-the-loop (60 sec)", s["h"]))
    story.append(
        bullets(
            [
                "Load <b>REQ-E01</b> → Run → Needs Review / locked draft",
                "<b>Escalate to lead</b> with a reason (or Release — closed; real send if Gmail connected)",
            ],
            s,
        )
    )
    story.append(
        p(
            "“Below 65% confidence we pause unsupervised release. Edit/release or escalate with a reason — governance, not a black box.”",
            s["say"],
        )
    )

    story.append(p("5 · Case Log (40 sec)", s["h"]))
    story.append(
        bullets(
            ["Case Log → select case → expand actions + messages → optional Replay"],
            s,
        )
    )
    story.append(
        p(
            "“Audit proof — what ran, what was drafted, who decided, when.”",
            s["say"],
        )
    )

    story.append(p("6 · Tech Lead (50 sec)", s["h"]))
    story.append(
        bullets(
            [
                "Sign out → <b>r.mehta / lead</b>",
                "Process → Escalated queue → Approve release <i>or</i> Return (reason + note)",
            ],
            s,
        )
    )
    story.append(
        p(
            "“Leads only see escalations. Acknowledge, approve the reply, or return with guidance.”",
            s["say"],
        )
    )

    story.append(p("7 · Playbooks + close (30 sec)", s["h"]))
    story.append(bullets(["Open Playbooks — six-row table + 65% gate"], s))
    story.append(
        p(
            "“Six distinct branches. PulseDesk: request in → typed playbook → governed outcome → logged evidence.”",
            s["say"],
        )
    )

    story.append(p("Timing (skip §3 ≈ 5 min)", s["h"]))
    timing = [
        [
            Paragraph("Block", s["cell_h"]),
            Paragraph("Time", s["cell_h"]),
            Paragraph("Block", s["cell_h"]),
            Paragraph("Time", s["cell_h"]),
        ],
        [
            Paragraph("0 Frame", s["cell"]),
            Paragraph("0:30", s["cell"]),
            Paragraph("4 HITL", s["cell"]),
            Paragraph("1:00", s["cell"]),
        ],
        [
            Paragraph("1 Login", s["cell"]),
            Paragraph("0:40", s["cell"]),
            Paragraph("5 Case Log", s["cell"]),
            Paragraph("0:40", s["cell"]),
        ],
        [
            Paragraph("2 REQ-001", s["cell"]),
            Paragraph("1:30", s["cell"]),
            Paragraph("6 Lead", s["cell"]),
            Paragraph("0:50", s["cell"]),
        ],
        [
            Paragraph("3 Optional branch", s["cell"]),
            Paragraph("0:40", s["cell"]),
            Paragraph("7 Close", s["cell"]),
            Paragraph("0:30", s["cell"]),
        ],
    ]
    tt = Table(timing, colWidths=[110, 50, 110, 50])
    tt.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), SOFT),
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(tt)
    story.append(Spacer(1, 4))
    story.append(
        p(
            "<b>Backup:</b> record locally if Cloud fails. "
            "<b>Don’t derail:</b> deep Gmail setup, OpenAI vs heuristic, SignalForge, CSS.",
            s["body"],
        )
    )

    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=40,
        rightMargin=40,
        topMargin=32,
        bottomMargin=36,
        title="PulseDesk — 5-minute demo script",
        author="PulseDesk POC",
    )
    doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
    return OUT


if __name__ == "__main__":
    print(f"Wrote {build()}")
