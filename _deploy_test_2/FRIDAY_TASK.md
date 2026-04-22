# 금요일 17:00 — 발송 + Notion 저장 스케줄 태스크

## Cowork에 입력할 태스크 프롬프트

---

```
[주간보고 발송 및 Notion 저장]

오늘은 금요일입니다. 승인된 주간보고를 이메일 발송하고 Notion에 저장해주세요.

## 작업 순서

1. C:\DesignCenter\reports\ 에서 STATUS: APPROVED 인 파일 탐색
2. APPROVED 파일이 없으면 → 작업 중단, 메시지 출력: "승인된 보고서가 없습니다. 보고서를 확인해주세요."
3. APPROVED 파일 발견 시:
   a. C:\DesignCenter\scripts\send_report.py 실행
   b. 이메일 발송 완료 확인
   c. C:\DesignCenter\scripts\save_to_notion.py 실행
   d. Notion 저장 완료 확인
   e. 파일을 C:\DesignCenter\archive\ 로 이동
   f. 파일 상단 STATUS를 SENT로 변경

## 오류 처리
- 이메일 발송 실패 시: 오류 내용 출력 후 중단 (재시도 금지)
- Notion 저장 실패 시: 오류 로그 출력, 이메일은 이미 발송됐으므로 수동 저장 안내

## 스케줄 설정
- Repeat: Weekly
- Day: Friday  
- Time: 17:00
```

