from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path


BASE = Path(__file__).resolve().parent.parent
REPORTS = BASE / "reports"


def monday_of_week(today: date) -> date:
    return today - timedelta(days=today.weekday())


def friday_of_week(today: date) -> date:
    return monday_of_week(today) + timedelta(days=4)


def week_label(today: date) -> str:
    return f"W{today.isocalendar().week}"


def date_range_label(today: date) -> str:
    monday = monday_of_week(today)
    friday = friday_of_week(today)
    return f"{monday.month}.{monday.day}-{friday.month}.{friday.day}"


def year_label(today: date) -> str:
    return today.strftime("%y")


def default_filename(today: date) -> str:
    return f"report_{week_label(today)}_{today.isoformat()}.md"


def build_template(today: date, status: str) -> str:
    week = week_label(today)
    date_range = date_range_label(today)
    created = datetime.now().strftime("%Y-%m-%d %H:%M")
    yy = year_label(today)

    return f"""---
STATUS: {status}
WEEK: {week}
DATE_RANGE: {date_range}
CREATED: {created}
---

# [Design Center] 주간업무보고 | {yy}년 {week} ({date_range})

## 📌 이번 주 핵심 요약
- 이번 주 핵심 내용 1
- 이번 주 핵심 내용 2
- 이번 주 핵심 내용 3

## ✅ 이번 주 주요 업무
| 구분 | 내용 | 상태 |
|------|------|------|
| 운영체계 | 이번 주 주요 업무 내용을 입력하세요 | 진행 중 |
| DLS 리서치 | 이번 주 주요 업무 내용을 입력하세요 | 진행 중 |
| 협업 조율 | 이번 주 주요 업무 내용을 입력하세요 | 진행 중 |

## 🔜 다음 주 계획
- 다음 주 계획 1
- 다음 주 계획 2
- 다음 주 계획 3

## ⚠️ 이슈 / 협조 요청
없음

## 💬 비고
필요 시 참고 메모를 입력하세요.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date",
        help="기준 날짜(YYYY-MM-DD). 기본값은 오늘 날짜입니다.",
    )
    parser.add_argument(
        "--status",
        default="DRAFT",
        choices=["DRAFT", "APPROVED", "SENT"],
        help="생성할 보고서 상태입니다.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="같은 이름의 파일이 있어도 덮어씁니다.",
    )
    args = parser.parse_args()

    today = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()
    REPORTS.mkdir(exist_ok=True)

    target = REPORTS / default_filename(today)
    if target.exists() and not args.force:
        print(f"Report already exists: {target.name}")
        print("Use --force to overwrite the file.")
        return

    target.write_text(build_template(today, args.status), encoding="utf-8")
    print(f"Draft created: {target.name}")
    print(f"Week: {week_label(today)}")
    print(f"Date range: {date_range_label(today)}")
    print("Sections included: summary, tasks, next plan, issues, notes")


if __name__ == "__main__":
    main()
