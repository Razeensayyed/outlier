"""Send the digest through Gmail SMTP using an App Password."""

from __future__ import annotations

import html
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send(gmail: str, app_password: str, to: str, subject: str, body_html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail
    msg["To"] = to
    msg.attach(MIMEText(body_html, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as s:
        s.login(gmail, app_password)
        s.sendmail(gmail, [a.strip() for a in to.split(",") if a.strip()], msg.as_string())


def esc(v) -> str:
    return html.escape(str(v if v is not None else ""))


def table(rows: list[dict], cols: list[str], link_col: str | None = None) -> str:
    if not rows:
        return "<p><i>None.</i></p>"
    head = "".join(f"<th style='text-align:left;padding:4px 8px;border-bottom:1px solid #ccc'>{esc(c)}</th>" for c in cols)
    body = []
    for r in rows:
        cells = []
        for c in cols:
            v = r.get(c, "")
            if c == link_col and v:
                cell = f"<a href='{esc(v)}'>open</a>"
            else:
                cell = esc(v)
            cells.append(f"<td style='padding:4px 8px;border-bottom:1px solid #eee;vertical-align:top'>{cell}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table style='border-collapse:collapse;font-size:14px'><tr>{head}</tr>{''.join(body)}</table>"


def page(title: str, sections: list[tuple[str, str]], sheet_url: str) -> str:
    parts = [f"<h2 style='margin:0 0 8px'>{esc(title)}</h2>",
             f"<p><a href='{esc(sheet_url)}'>Open the Outlier sheet</a></p>"]
    for heading, content in sections:
        parts.append(f"<h3 style='margin:18px 0 6px'>{esc(heading)}</h3>{content}")
    return "<div style='font-family:Arial,sans-serif;max-width:900px'>" + "".join(parts) + "</div>"
