# Weekly Report Auto

이 폴더를 운영 루트로 사용해 Design Center 주간업무보고를 작성, 메일 발송, Notion 저장까지 처리합니다.

## 운영 경로

- root: `C:\Users\Sejung Oh\Downloads\2026\01_BMS\12_Design Center\Weekly Report Auto`
- config: `config\secrets.json`
- reports: `reports`
- archive: `archive`

## 주요 파일

- `REPORT_TEMPLATE.md`: 한국어 기준 보고서 템플릿
- `scripts/generate_report.py`: 아이콘 포함 초안 보고서 자동 생성
- `scripts/send_report.py`: 승인된 보고서를 읽어 메일 발송
- `scripts/save_to_notion.py`: 발송된 보고서를 Notion DB에 저장
- `scripts/run_friday_flow.py`: 금요일 운영용 안전 실행 흐름
- `THURSDAY_TASK.md`: 목요일 초안 생성 프롬프트
- `FRIDAY_TASK.md`: 금요일 발송/저장 프롬프트

## 실무 순서

1. 목요일에 `REPORT_TEMPLATE.md` 형식으로 `reports\report_W{주차}_{날짜}.md` 초안을 작성합니다.
다음 명령으로 기본 초안을 자동 생성할 수 있습니다.

```powershell
python .\scripts\generate_report.py
```

이 명령으로 생성되는 파일에는 `📌✅🔜⚠️💬` 섹션이 이미 포함됩니다.
2. 승인 전까지는 `STATUS: DRAFT`를 유지합니다.
3. 금요일 발송 전 승인되면 `STATUS: APPROVED`로 변경합니다.
4. 발송 전 검증은 아래 명령으로 실행합니다.

```powershell
python .\scripts\send_report.py --dry-run
```

5. 금요일 전체 흐름은 아래 명령으로 안전하게 시작할 수 있습니다.

```powershell
python .\scripts\run_friday_flow.py
```

위 명령은 dry-run까지만 수행하고 멈춥니다.

6. 실제 메일 발송과 Notion 저장까지 진행하려면 아래 명령을 사용합니다.

```powershell
python .\scripts\run_friday_flow.py --execute-send
```

## 참고

- `send_report.py`는 성공 시 `STATUS: APPROVED`를 `STATUS: SENT`로 변경합니다.
- `save_to_notion.py`는 성공 시 기본 동작으로 보고서를 `archive` 폴더로 이동합니다.
- 테스트 시에는 `save_to_notion.py --no-archive`를 사용할 수 있습니다.
