import argparse
import html
import json
import re
import smtplib
import ssl
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


BASE = Path(__file__).resolve().parent.parent
CONFIG = BASE / "config" / "secrets.json"
LEGACY_CONFIG = BASE / "secrets.json"
REPORTS = BASE / "reports"


def load_config():
    config_path = CONFIG if CONFIG.exists() else LEGACY_CONFIG
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def load_report(report_arg=None):
    if report_arg:
        path = Path(report_arg)
        if not path.is_absolute():
            path = BASE / path
        if not path.exists():
            raise FileNotFoundError(f"Report file not found: {path}")
        return path, path.read_text(encoding="utf-8")

    for path in sorted(REPORTS.glob("report_W*.md"), reverse=True):
        content = path.read_text(encoding="utf-8")
        if "STATUS: APPROVED" in content:
            return path, content
    raise FileNotFoundError("No approved report found.")


def extract_meta(content):
    week_match = re.search(r"^WEEK:\s*(W\d+)", content, re.MULTILINE)
    date_range_match = re.search(r"^DATE_RANGE:\s*(.+)", content, re.MULTILINE)
    created_match = re.search(r"^CREATED:\s*(.+)", content, re.MULTILINE)
    return {
        "week": week_match.group(1) if week_match else "W??",
        "date_range": date_range_match.group(1).strip() if date_range_match else "",
        "created": created_match.group(1).strip() if created_match else "",
    }


def extract_section(content, heading):
    lines = content.splitlines()
    collected = []
    collecting = False

    for line in lines:
        stripped = line.strip()
        if stripped == heading:
            collecting = True
            continue
        if collecting and stripped.startswith("## "):
            break
        if collecting:
            collected.append(line.rstrip())

    return "\n".join(collected).strip()


def extract_bullets(block):
    return [line.strip()[2:].strip() for line in block.splitlines() if line.strip().startswith("- ")]


def extract_table_rows(block):
    rows = []
    for line in block.splitlines():
        if "|" not in line:
            continue
        cells = [cell.strip() for cell in line.split("|") if cell.strip()]
        if len(cells) != 3:
            continue
        if cells[0] == "구분" or set("".join(cells)) == {"-"}:
            continue
        rows.append(cells)
    return rows


def parse_report(content):
    summary_block = extract_section(content, "## 📌 이번 주 핵심 요약")
    tasks_block = extract_section(content, "## ✅ 이번 주 주요 업무")
    next_plan_block = extract_section(content, "## 🔜 다음 주 계획")
    issue_block = extract_section(content, "## ⚠️ 이슈 / 협조 요청")
    note_block = extract_section(content, "## 💬 비고")

    return {
        "summary_items": extract_bullets(summary_block),
        "task_rows": extract_table_rows(tasks_block),
        "next_plan_items": extract_bullets(next_plan_block),
        "issue_text": issue_block.strip() or "없음",
        "note_text": note_block.strip(),
    }


def build_html(meta, sections):
    summary_html = "".join(
        f"<li style='margin:0 0 6px 0'>{html.escape(item)}</li>"
        for item in sections["summary_items"]
    )
    F = "font-family:Noto Sans KR,-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif;"
    TABLE_BODY_TEXT = f"font-size:11pt !important;line-height:1.45;mso-line-height-rule:exactly;{F}"
    task_rows_html = "".join(
        (
            "<tr>"
            f"<td style='padding:10px 12px;border-bottom:1px solid #ececec;color:#555;vertical-align:top;{TABLE_BODY_TEXT}'><span style='color:#555;{TABLE_BODY_TEXT}'>{html.escape(category)}</span></td>"
            f"<td style='padding:10px 12px;border-bottom:1px solid #ececec;color:#222;vertical-align:top;{TABLE_BODY_TEXT}'><span style='color:#222;{TABLE_BODY_TEXT}'>{html.escape(task)}</span></td>"
            f"<td style='padding:10px 12px;border-bottom:1px solid #ececec;color:#0b6bcb;text-align:center;vertical-align:top;white-space:nowrap;{TABLE_BODY_TEXT}'><span style='color:#0b6bcb;{TABLE_BODY_TEXT}'>{html.escape(status)}</span></td>"
            "</tr>"
        )
        for category, task, status in sections["task_rows"]
    )
    next_plan_html = "".join(
        f"<li style='margin:0 0 6px 0;color:#222;font-size:11pt !important;line-height:1.7;mso-line-height-rule:exactly;{F}'><span style='color:#222;font-size:11pt !important;line-height:1.7;mso-line-height-rule:exactly;{F}'>{html.escape(item)}</span></li>"
        for item in sections["next_plan_items"]
    )
    note_html = (
        "<div style='padding:0 28px 28px'>"
        "<h2 style='font-size:14px;margin:0 0 10px 0;color:#666'>비고</h2>"
        f"<p style='margin:0;color:#222;line-height:1.7'>{html.escape(sections['note_text'])}</p>"
        "</div>"
        if sections["note_text"]
        else ""
    )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:24px;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:760px;margin:0 auto;background:#ffffff;border:1px solid #e8e8e8;border-radius:12px;overflow:hidden;">
    <div style="background:#18212f;padding:28px;color:#ffffff;">
      <div style="font-size:11px;letter-spacing:1.6px;color:#9eb0c9;">DESIGN CENTER</div>
      <div style="display:flex;justify-content:space-between;gap:16px;align-items:flex-end;margin-top:12px;">
        <div>
          <div style="font-size:24px;font-weight:700;">주간업무보고</div>
          <div style="font-size:13px;color:#d6deea;margin-top:6px;">{html.escape(meta['date_range'])}</div>
        </div>
        <div style="text-align:right;">
          <div style="font-size:22px;font-weight:700;">{html.escape(meta['week'])}</div>
          <div style="font-size:12px;color:#d6deea;">작성일 {html.escape(meta['created'])}</div>
        </div>
      </div>
    </div>
    <div style="padding:28px 28px 20px">
      <h2 style="font-size:14px;margin:0 0 10px 0;color:#666">📌 이번 주 핵심 요약</h2>
      <ul style="margin:0;padding-left:20px;color:#222;line-height:1.7">{summary_html}</ul>
    </div>
    <div style="padding:0 28px 20px">
      <h2 style="font-size:14px;margin:0 0 10px 0;color:#666">✅ 이번 주 주요 업무</h2>
      <table style="width:100%;border-collapse:collapse;border:1px solid #ececec;border-radius:8px;overflow:hidden;">
        <thead>
          <tr style="background:#fafafa;">
            <th style="padding:10px 12px;text-align:left;border-bottom:1px solid #ececec;color:#777;font-size:12px;">구분</th>
            <th style="padding:10px 12px;text-align:left;border-bottom:1px solid #ececec;color:#777;font-size:12px;">내용</th>
            <th style="padding:10px 12px;text-align:center;border-bottom:1px solid #ececec;color:#777;font-size:12px;">상태</th>
          </tr>
        </thead>
        <tbody>{task_rows_html}</tbody>
      </table>
    </div>
    <div style="padding:0 28px 20px">
      <h2 style="font-size:14px;margin:0 0 10px 0;color:#666">🔜 다음 주 계획</h2>
      <ul style="margin:0;padding-left:20px;color:#222;line-height:1.7">{next_plan_html}</ul>
    </div>
    <div style="padding:0 28px 20px">
      <h2 style="font-size:14px;margin:0 0 10px 0;color:#666">⚠️ 이슈 / 협조 요청</h2>
      <p style="margin:0;color:#222;line-height:1.7">{html.escape(sections['issue_text'])}</p>
    </div>
    {note_html}
  </div>
</body>
</html>"""


def build_message(config, meta, html_body):
    smtp = config["smtp"]
    date_range_for_subject = meta["date_range"].replace(" ", "")
    subject = f"[Design Center] 주간업무보고 | {datetime.now().strftime('%y')}년 {meta['week']} ({date_range_for_subject})"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{config.get('sender_name', 'Design Center')} <{smtp['user']}>"
    msg["To"] = ", ".join(config["recipients"])
    if config.get("cc"):
        msg["Cc"] = ", ".join(config["cc"])
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return subject, msg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", help="Report path to send.")
    args = parser.parse_args()

    config = load_config()
    try:
        filepath, content = load_report(args.report)
    except FileNotFoundError as exc:
        print(str(exc))
        sys.exit(1)

    meta = extract_meta(content)
    sections = parse_report(content)
    html_body = build_html(meta, sections)
    subject, msg = build_message(config, meta, html_body)
    all_recipients = config["recipients"] + config.get("cc", [])

    if args.dry_run:
        print("DRY RUN: email was not sent.")
        print(f"Report: {filepath.name}")
        print(f"Subject: {subject}")
        print(f"To count: {len(config['recipients'])}")
        print(f"Cc count: {len(config.get('cc', []))}")
        print(f"Total recipients: {len(all_recipients)}")
        print(f"Summary items: {len(sections['summary_items'])}")
        print(f"Task rows: {len(sections['task_rows'])}")
        print(f"HTML size: {len(html_body)}")
        print(f"MIME size: {len(msg.as_string())}")
        sys.exit(0)

    smtp = config["smtp"]
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp["host"], smtp["port"], context=ctx) as server:
            server.login(smtp["user"], smtp["password"])
            server.sendmail(smtp["user"], all_recipients, msg.as_string())
        print(f"Email sent to {len(config['recipients'])} recipients.")
        filepath.write_text(
            content.replace("STATUS: APPROVED", "STATUS: SENT", 1),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"Send failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
