import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib import error, request


BASE = Path(__file__).resolve().parent.parent
CONFIG = BASE / "config" / "secrets.json"
LEGACY_CONFIG = BASE / "secrets.json"
REPORTS = BASE / "reports"
ARCHIVE = BASE / "archive"


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
        if "STATUS: SENT" in content:
            return path, content
    raise FileNotFoundError("No sent report found.")


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


def parse_report(content):
    week_match = re.search(r"^WEEK:\s*(W\d+)", content, re.MULTILINE)
    date_range_match = re.search(r"^DATE_RANGE:\s*(.+)", content, re.MULTILINE)
    week = week_match.group(1) if week_match else "W0"
    week_num_match = re.search(r"W(\d+)", week)

    return {
        "week": week,
        "week_num": int(week_num_match.group(1)) if week_num_match else 0,
        "date_range": date_range_match.group(1).strip() if date_range_match else "",
        "summary": extract_section(content, "## 📌 이번 주 핵심 요약")[:2000],
        "tasks": extract_section(content, "## ✅ 이번 주 주요 업무")[:2000],
        "next_plan": extract_section(content, "## 🔜 다음 주 계획")[:2000],
        "issue": (extract_section(content, "## ⚠️ 이슈 / 협조 요청") or "없음")[:2000],
        "sent_at": datetime.now().isoformat(),
    }


def build_payload(config, data):
    title = f"Design Center 주간업무보고 {data['week']} ({data['date_range']})"
    return {
        "parent": {"database_id": config["notion"]["database_id"]},
        "properties": {
            "제목": {"title": [{"text": {"content": title}}]},
            "주차": {"number": data["week_num"]},
            "보고일": {"date": {"start": datetime.now().strftime("%Y-%m-%d")}},
            "핵심요약": {"rich_text": [{"text": {"content": data["summary"]}}]},
            "이번주업무": {"rich_text": [{"text": {"content": data["tasks"]}}]},
            "다음주계획": {"rich_text": [{"text": {"content": data["next_plan"]}}]},
            "이슈협조": {"rich_text": [{"text": {"content": data["issue"]}}]},
            "발송여부": {"checkbox": True},
            "발송시각": {"date": {"start": data["sent_at"]}},
        },
    }, title


def save_to_notion(config, data, dry_run=False):
    payload, title = build_payload(config, data)
    if dry_run:
        print("DRY RUN: Notion page was not created.")
        print(f"Title: {title}")
        print(f"Database: {config['notion']['database_id']}")
        print(f"Week number: {data['week_num']}")
        print(f"Summary length: {len(data['summary'])}")
        return True, None

    headers = {
        "Authorization": f"Bearer {config['notion']['api_key']}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        "https://api.notion.com/v1/pages",
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=30) as response:
            response_body = response.read().decode("utf-8")
            response_json = json.loads(response_body)
            print(f"Notion save complete: {title}")
            if response_json.get("id"):
                print(f"Page ID: {response_json['id']}")
            if response_json.get("url"):
                print(f"Page URL: {response_json['url']}")
            return True, response_json
    except error.HTTPError as exc:
        print(f"Notion save failed: {exc.code}")
        print(exc.read().decode("utf-8", errors="replace"))
        return False, None
    except error.URLError as exc:
        print(f"Notion request failed: {exc}")
        return False, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", help="Report path to save.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-archive", action="store_true")
    args = parser.parse_args()

    config = load_config()
    try:
        filepath, content = load_report(args.report)
    except FileNotFoundError as exc:
        print(str(exc))
        sys.exit(1)

    report_data = parse_report(content)
    ok, _ = save_to_notion(config, report_data, dry_run=args.dry_run)
    if not ok:
        sys.exit(1)

    if args.dry_run:
        print(f"Report used: {filepath.name}")
        sys.exit(0)

    if args.no_archive:
        print(f"Archive skipped for test run: {filepath.name}")
        sys.exit(0)

    ARCHIVE.mkdir(exist_ok=True)
    target = ARCHIVE / filepath.name
    filepath.rename(target)
    print(f"Archived: {filepath.name}")


if __name__ == "__main__":
    main()
