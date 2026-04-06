# Reels Translator Monitor — 자동 실행 설정

매일 오후 9시에 `reels_translator.py --monitor`를 자동 실행하는 cron 설정입니다.

## 파일 구성

| 파일 | 설명 |
|------|------|
| `run_reels_monitor.sh` | 명령어 실행 + 로그/오류 기록 래퍼 스크립트 |
| `setup_cron.sh` | cron 작업 등록 스크립트 |

## 설치 방법

```bash
# 1. 이 저장소를 /Users/comcom 에 클론하거나 스크립트를 복사
git clone <repo-url> /Users/comcom/claude-automation

# 2. cron 작업 등록
bash /Users/comcom/claude-automation/setup_cron.sh
```

등록 후 `crontab -l` 로 확인:
```
0 21 * * * /Users/comcom/claude-automation/run_reels_monitor.sh
```

## 로그 확인

실행 로그는 `/Users/comcom/logs/` 에 날짜별로 저장됩니다:

```bash
# 최신 로그 보기
ls -lt /Users/comcom/logs/ | head

# 오류 로그만 보기
cat /Users/comcom/logs/reels_monitor_*.error.log
```

## 오류 알림 (이메일, 선택사항)

이메일 알림을 받으려면 실행 전 환경변수를 설정하세요:
```bash
export NOTIFY_EMAIL="your@email.com"
```

또는 crontab 에 직접 추가:
```
0 21 * * * NOTIFY_EMAIL=your@email.com /Users/comcom/claude-automation/run_reels_monitor.sh
```
