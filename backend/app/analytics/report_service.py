
"""Build and email the weekly anonymous-usage analytics report."""
from __future__ import annotations

import os
import secrets
import base64
import json
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.models import UserSession

REPORT_TZ = ZoneInfo(os.getenv("REPORT_TIMEZONE", "Asia/Kolkata"))


def _duration(seconds: int | float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _change(current: int | float, previous: int | float) -> str:
    if previous == 0:
        return "New" if current else "0%"
    pct = ((current - previous) / previous) * 100
    return f"{pct:+.1f}%"


def collect_weekly_metrics(db: Session, now: datetime | None = None) -> dict:
    """Return rolling seven-day metrics and the preceding seven-day comparison.

    Sessions are attributed to the local date on which they started. Unique
    visitors are distinct anonymous visitor IDs with a session in the period.
    """
    local_now = (now or datetime.now(timezone.utc)).astimezone(REPORT_TZ)
    end_local = local_now
    start_local = end_local - timedelta(days=7)
    previous_start_local = start_local - timedelta(days=7)

    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    previous_start_utc = previous_start_local.astimezone(timezone.utc)

    current_rows = db.execute(
        select(UserSession.visitor_id, UserSession.started_at, UserSession.active_seconds)
        .where(UserSession.started_at >= start_utc, UserSession.started_at < end_utc)
    ).all()
    previous_rows = db.execute(
        select(UserSession.visitor_id, UserSession.started_at, UserSession.active_seconds)
        .where(
            UserSession.started_at >= previous_start_utc,
            UserSession.started_at < start_utc,
        )
    ).all()

    def summarize(rows: list) -> dict:
        visitors = {row.visitor_id for row in rows}
        sessions = len(rows)
        active_seconds = sum(int(row.active_seconds or 0) for row in rows)
        daily: dict[str, set[str]] = defaultdict(set)

        for row in rows:
            started = row.started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            day_key = started.astimezone(REPORT_TZ).date().isoformat()
            daily[day_key].add(row.visitor_id)

        return {
            "unique_visitors": len(visitors),
            "total_sessions": sessions,
            "total_active_seconds": active_seconds,
            "average_active_seconds": round(active_seconds / sessions, 1) if sessions else 0,
            "daily_visitors": daily,
        }

    current = summarize(current_rows)
    previous = summarize(previous_rows)
    day_count = (end_local.date() - start_local.date()).days + 1
    days = [start_local.date() + timedelta(days=i) for i in range(max(day_count, 1))]

    daily_rows = [
        {
            "date": day.isoformat(),
            "visitors": len(current["daily_visitors"].get(day.isoformat(), set()))
        }
        for day in days
    ]

    return {
        "timezone": str(REPORT_TZ),
        "period_start": start_local.isoformat(),
        "period_end": end_local.isoformat(),
        "period_label": f"{start_local:%d %b %Y %I:%M %p} – {end_local:%d %b %Y %I:%M %p} ({REPORT_TZ.key})",
        "current": {k: v for k, v in current.items() if k != "daily_visitors"},
        "previous": {k: v for k, v in previous.items() if k != "daily_visitors"},
        "daily_visitors": daily_rows,
        "changes": {
            "unique_visitors": _change(current["unique_visitors"], previous["unique_visitors"]),
            "total_sessions": _change(current["total_sessions"], previous["total_sessions"]),
            "total_active_seconds": _change(current["total_active_seconds"], previous["total_active_seconds"]),
        },
    }


def generate_pdf(metrics: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title="Weekly Admission Website Usage Report",
        author="Admission Analytics System",
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle", parent=styles["Title"], fontSize=19,
        leading=23, textColor=colors.HexColor("#315F60"), alignment=TA_CENTER,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="SmallMuted", parent=styles["Normal"], fontSize=8,
        textColor=colors.HexColor("#666666"), leading=11,
    ))

    story = [
        Paragraph("Weekly Admission Website Usage Report", styles["ReportTitle"]),
        Paragraph(f"Reporting period: {metrics['period_label']}", styles["Normal"]),
        Spacer(1, 8 * mm),
    ]

    current = metrics["current"]
    previous = metrics["previous"]

    summary_data = [
        ["Metric", "This period", "Previous period", "Change"],
        ["Unique visitors", str(current["unique_visitors"]), str(previous["unique_visitors"]), metrics["changes"]["unique_visitors"]],
        ["Total visits (sessions)", str(current["total_sessions"]), str(previous["total_sessions"]), metrics["changes"]["total_sessions"]],
        ["Total active time", _duration(current["total_active_seconds"]), _duration(previous["total_active_seconds"]), metrics["changes"]["total_active_seconds"]],
        ["Average active time per visit", _duration(current["average_active_seconds"]), _duration(previous["average_active_seconds"]), "—"],
    ]

    table = Table(summary_data, colWidths=[61 * mm, 34 * mm, 34 * mm, 30 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#5F9EA0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D7E0E0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F7F7")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))

    story += [
        Paragraph("Weekly summary", styles["Heading2"]),
        table,
        Spacer(1, 7 * mm)
    ]

    daily_data = [["Date (India time)", "Unique visitors"]]
    daily_data.extend([
        [item["date"], str(item["visitors"])]
        for item in metrics["daily_visitors"]
    ])

    daily_table = Table(daily_data, colWidths=[95 * mm, 45 * mm], repeatRows=1)
    daily_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#5F9EA0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D7E0E0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F7F7")]),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    story += [
        Paragraph("Daily visitor trend", styles["Heading2"]),
        daily_table,
        Spacer(1, 6 * mm)
    ]

    story.append(Paragraph(
        "Notes: Visitors are counted using distinct anonymous browser IDs with a session started during the reporting period. "
        "Active time is the sum of recorded visible-tab activity for sessions started during that period. "
        "This report contains aggregate usage metrics only.",
        styles["SmallMuted"]
    ))

    doc.build(story)
    return buffer.getvalue()


def email_pdf_report(pdf_bytes: bytes, metrics: dict) -> None:
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    sender = os.getenv("REPORT_FROM_EMAIL", "").strip()
    recipient = os.getenv("REPORT_RECIPIENT_EMAIL", "").strip()

    if not api_key or not sender or not recipient:
        raise RuntimeError(
            "RESEND_API_KEY, REPORT_FROM_EMAIL and REPORT_RECIPIENT_EMAIL must be configured"
        )

    report_date = datetime.now(REPORT_TZ).strftime("%Y-%m-%d")
    filename = f"admission-usage-report-{report_date}.pdf"

    message_text = (
        "Hello,\n\n"
        "Please find attached the weekly Admission website usage report.\n\n"
        f"Reporting period: {metrics['period_label']}\n"
        f"Unique visitors: {metrics['current']['unique_visitors']}\n"
        f"Total visits: {metrics['current']['total_sessions']}\n"
        f"Total active time: {_duration(metrics['current']['total_active_seconds'])}\n"
        f"Average active time per visit: {_duration(metrics['current']['average_active_seconds'])}\n\n"
        "Regards,\nAdmission Analytics System"
    )

    payload = {
        "from": sender,
        "to": [recipient],
        "subject": f"Weekly Admission Website Usage Report – {datetime.now(REPORT_TZ):%d %b %Y}",
        "text": message_text,
        "attachments": [
            {
                "filename": filename,
                "content": base64.b64encode(pdf_bytes).decode("ascii"),
            }
        ],
    }

    request = urllib.request.Request(
        url="https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            print(f"Weekly analytics email accepted by Resend. Email ID: {result.get('id')}")

    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Resend API returned HTTP {exc.code}: {error_body}"
        ) from exc

    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Could not connect to Resend API: {exc.reason}"
        ) from exc


def send_weekly_report(db: Session) -> dict:
    metrics = collect_weekly_metrics(db)
    pdf_bytes = generate_pdf(metrics)
    email_pdf_report(pdf_bytes, metrics)

    return {
        "status": "sent",
        "recipient": os.getenv("REPORT_RECIPIENT_EMAIL", "").strip(),
        "period": metrics["period_label"],
        "metrics": metrics["current"],
        "pdf_bytes": len(pdf_bytes),
    }


def valid_report_token(provided: str | None) -> bool:
    expected = os.getenv("REPORT_TRIGGER_TOKEN", "")
    return bool(expected and provided and secrets.compare_digest(expected, provided))
