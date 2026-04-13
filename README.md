# 릴스 번역 모니터

인스타그램 벤치마킹 계정의 릴스를 매일 자동 수집·번역하여 이메일로 발송합니다.

## 동작 방식

1. Chrome 쿠키로 Instagram API 인증
2. 7개 대상 계정의 오늘 업로드된 릴스 수집
3. Whisper로 음성 인식 → 한국어 번역
4. Gmail로 HTML 이메일 1통 발송

## 설치

```bash
# 1. 레포 클론
git clone https://github.com/ye-ezzi/claude-automation.git ~/claude-automation
cd ~/claude-automation
git checkout claude/setup-reels-translator-monitor-YgA3N

# 2. 가상환경 + 패키지 설치
bash setup_venv.sh

# 3. cron 등록 (매일 오후 9시)
bash setup_cron.sh
```

## 수동 실행

```bash
cd ~/claude-automation
bash run_reels_monitor.sh
```

## 로그 확인

```bash
cat ~/logs/reels_monitor_$(date '+%Y-%m-%d').log
```
