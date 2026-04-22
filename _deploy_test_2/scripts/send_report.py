import json, smtplib, ssl, re, sys
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

BASE = Path("C:/DesignCenter")
CONFIG = BASE / "config" / "secrets.json"
REPORTS = BASE / "reports"

def load_config():
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)

def find_approved_report():
    for f in sorted(REPORTS.glob("report_W*.md"), reverse=True):
        content = f.read_text(encoding="utf-8")
        if "STATUS: APPROVED" in content:
            return f, content
    return None, None

def parse_report(content):
    week = re.search(r'WEEK:\s*(W\d+)', content)
    date_range = re.search(r'DATE_RANGE:\s*(.+)', content)
    summary_raw = content.split("## 📌 핵심 요약")[1].split("##")[0] if "## 📌" in content else ""
    summary = [l.lstrip("- ").strip() for l in summary_raw.split("\n") if l.strip().startswith("-")]
    return {
        "week": week.group(1) if week else "W??",
        "date_range": date_range.group(1).strip() if date_range else "",
        "summary": summary[:3]
    }

def md_to_html(content, meta):
    table_rows = ""
    if "## ✅" in content:
        table_section = content.split("## ✅ 이번 주 주요 업무")[1].split("##")[0]
        for line in table_section.split("\n"):
            cells = [c.strip() for c in line.split("|") if c.strip()]
            if len(cells) == 3 and cells[0] not in ["구분", "---", "-"*3]:
                sc = {"완료": "#1D9E75", "진행 중": "#378ADD", "보류": "#E24B4A"}.get(cells[2], "#888")
                table_rows += f'<tr><td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;color:#555;font-size:13px;">{cells[0]}</td><td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;font-size:13px;">{cells[1]}</td><td style="padding:8px 12px;text-align:center;border-bottom:1px solid #f0f0f0;"><span style="background:{sc}18;color:{sc};padding:2px 10px;border-radius:20px;font-size:12px;">{cells[2]}</span></td></tr>'

    next_items = ""
    if "## 🔜" in content:
        next_section = content.split("## 🔜 다음 주 계획")[1].split("##")[0]
        for line in next_section.split("\n"):
            line = line.lstrip("- ").strip()
            if line:
                next_items += f'<li style="padding:4px 0;font-size:13px;color:#333;">{line}</li>'

    issue_text = "없음"
    if "## ⚠️" in content:
        raw = content.split("## ⚠️")[1].split("##")[0].strip()
        raw = re.sub(r'^이슈 / 협조 요청\s*', '', raw).strip()
        issue_text = raw if raw else "없음"

    summary_html = "".join(f'<p style="margin:2px 0;font-size:13px;color:#444;">· {s}</p>' for s in meta["summary"] if s)
    today = datetime.now().strftime("%Y년 %m월 %d일")
    year = datetime.now().strftime("%Y")

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<div style="max-width:640px;margin:24px auto;background:#fff;border-radius:8px;overflow:hidden;border:1px solid #e8e8e8;">
  <div style="background:#1a1a2e;padding:24px 28px;display:flex;justify-content:space-between;align-items:flex-start;">
    <div><p style="margin:0 0 4px;font-size:11px;color:#8888aa;letter-spacing:1.5px;">WEEKLY REPORT</p><h1 style="margin:0;font-size:20px;color:#fff;font-weight:500;">Design Center</h1></div>
    <div style="text-align:right;"><p style="margin:0 0 2px;font-size:18px;color:#fff;font-weight:600;">{meta['week']}</p><p style="margin:0;font-size:12px;color:#8888aa;">{year}. {meta['date_range']}</p></div>
  </div>
  {'<div style="padding:16px 28px;background:#f8f9ff;border-bottom:1px solid #eee;">' + summary_html + '</div>' if summary_html else ''}
  <div style="padding:20px 28px 8px;">
    <p style="margin:0 0 10px;font-size:11px;color:#999;letter-spacing:1px;font-weight:500;">이번 주 주요 업무</p>
    <table style="width:100%;border-collapse:collapse;"><thead><tr style="background:#fafafa;"><th style="padding:8px 12px;text-align:left;font-size:11px;color:#999;font-weight:500;width:22%;">구분</th><th style="padding:8px 12px;text-align:left;font-size:11px;color:#999;font-weight:500;">내용</th><th style="padding:8px 12px;text-align:center;font-size:11px;color:#999;font-weight:500;width:18%;">상태</th></tr></thead><tbody>{table_rows}</tbody></table>
  </div>
  <div style="padding:16px 28px 8px;"><p style="margin:0 0 10px;font-size:11px;color:#999;letter-spacing:1px;font-weight:500;">다음 주 계획</p><ul style="margin:0;padding-left:18px;">{next_items}</ul></div>
  <div style="padding:16px 28px 20px;"><p style="margin:0 0 8px;font-size:11px;color:#999;letter-spacing:1px;font-weight:500;">이슈 / 협조 요청</p><p style="margin:0;font-size:13px;color:#333;">{issue_text}</p></div>
  <div style="padding:12px 28px;background:#fafafa;border-top:1px solid #eee;"><p style="margin:0;font-size:11px;color:#bbb;">BMS Design Center · {today}</p></div>
</div></body></html>"""

def main():
    config = load_config()
    filepath, content = find_approved_report()
    if not filepath:
        print("❌ APPROVED 보고서 없음. 발송 중단.")
        sys.exit(1)
    print(f"✅ 보고서 발견: {filepath.name}")
    meta = parse_report(content)
    html = md_to_html(content, meta)
    subject = f"[Design Center] 주간업무보고 | {datetime.now().strftime('%y')}년 {meta['week']} ({meta['date_range']})"
    smtp = config["smtp"]
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{config.get('sender_name','Design Center')} <{smtp['user']}>"
    msg["To"] = ", ".join(config["recipients"])
    if config.get("cc"):
        msg["Cc"] = ", ".join(config["cc"])
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp["host"], smtp["port"], context=ctx) as s:
            s.login(smtp["user"], smtp["password"])
            all_recipients = config["recipients"] + config.get("cc", [])
            s.sendmail(smtp["user"], all_recipients, msg.as_string())
        print(f"✅ 발송 완료 → {len(config['recipients'])}명")
        filepath.write_text(content.replace("STATUS: APPROVED", "STATUS: SENT"), encoding="utf-8")
    except Exception as e:
        print(f"❌ 발송 실패: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
