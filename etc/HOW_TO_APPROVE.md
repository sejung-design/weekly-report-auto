# 보고서 검토 및 승인 방법

## 매주 목요일 오후 — 초안 확인

1. `C:\DesignCenter\reports\` 폴더 열기
2. `report_W{주차}_{날짜}.md` 파일 열기 (메모장 또는 VS Code)
3. 내용 수정/보완
4. 파일 상단의 `STATUS: DRAFT` → `STATUS: APPROVED` 로 변경
5. 저장

→ 금요일 17:00에 자동 발송됩니다.

## 승인 취소 / 발송 보류

`STATUS: APPROVED` → `STATUS: HOLD` 로 변경하면 금요일에 발송되지 않습니다.

## 긴급 수동 발송

Cowork에서 아래 입력:
```
C:\DesignCenter\scripts\send_report.py 를 실행해서 보고서를 즉시 발송해줘
```

