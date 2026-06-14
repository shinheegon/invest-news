#!/bin/bash
# 매일 2회 투자 브리핑 실행 래퍼 (launchd가 호출)
set -uo pipefail

# --- 경로 설정 ---
PROJECT_DIR="/Users/shinheekon/Desktop/ai-project/news"
export PATH="/Users/shinheekon/.local/bin:/Users/shinheekon/.local/node/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# 로컬 비밀키(이메일 등) — 맥에만 보관, git에 안 올라감
[ -f "$HOME/.news-briefing.env" ] && set -a && . "$HOME/.news-briefing.env" && set +a
cd "$PROJECT_DIR" || exit 1

LOG="$PROJECT_DIR/logs/run.log"

# --- 회차(AM/PM) 판정: 인자 > 환경변수 > 현재시각 ---
SESSION="${1:-${BRIEFING_SESSION:-}}"
if [ -z "$SESSION" ]; then
  HOUR=$(date +%H)
  if [ "$HOUR" -lt 12 ]; then SESSION="AM"; else SESSION="PM"; fi
fi
DATE=$(date +%Y-%m-%d)
export BRIEFING_SESSION="$SESSION"
export BRIEFING_DATE="$DATE"

# --- 멱등성: 같은 날짜+회차가 이미 집계됐으면 카운트 중복 방지 ---
MARKER="$PROJECT_DIR/data/.last-session"
if [ -f "$MARKER" ] && [ "$(cat "$MARKER" 2>/dev/null)" = "$DATE-$SESSION" ]; then
  export COUNT_MODE="skip"   # 이미 집계됨 → 인덱스 증가 금지, 콘텐츠만 재생성
else
  export COUNT_MODE="count"  # 신규 회차 → 정상 집계
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] START session=$SESSION date=$DATE count_mode=$COUNT_MODE" >> "$LOG"

# --- 헤드리스 Claude 실행 ---
claude -p "$(cat "$PROJECT_DIR/prompt/briefing-prompt.md")" \
  --permission-mode acceptEdits \
  --allowedTools "WebSearch,WebFetch,Read,Write,Edit,Bash" \
  >> "$LOG" 2>&1
RC=$?

if [ $RC -eq 0 ]; then
  echo "$DATE-$SESSION" > "$MARKER"   # 이 회차 집계 완료 표시
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] DONE  session=$SESSION rc=0" >> "$LOG"
else
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR session=$SESSION rc=$RC" >> "$LOG"
fi

# --- 사이트 빌드 + GitHub 배포 (git 원격이 설정된 경우에만 push) ---
bash "$PROJECT_DIR/scripts/build-site.sh" >> "$LOG" 2>&1 || \
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARN build-site failed" >> "$LOG"

if git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git -C "$PROJECT_DIR" add -A >> "$LOG" 2>&1 || true
  if ! git -C "$PROJECT_DIR" diff --cached --quiet 2>/dev/null; then
    git -C "$PROJECT_DIR" commit -m "briefing: $DATE $SESSION" >> "$LOG" 2>&1 || true
    if git -C "$PROJECT_DIR" remote get-url origin >/dev/null 2>&1; then
      git -C "$PROJECT_DIR" push origin HEAD >> "$LOG" 2>&1 \
        && echo "[$(date '+%Y-%m-%d %H:%M:%S')] PUSHED $DATE $SESSION" >> "$LOG" \
        || echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARN push failed (인증/원격 확인)" >> "$LOG"
    fi
  fi
fi

# --- 이메일 요약 + 급등 알림 발송 (RESEND_API_KEY 있으면 발송) ---
BRIEFING_SESSION="$SESSION" BRIEFING_DATE="$DATE" \
  python3 "$PROJECT_DIR/scripts/notify-email.py" >> "$LOG" 2>&1 \
  && echo "[$(date '+%Y-%m-%d %H:%M:%S')] EMAIL sent/preview $DATE $SESSION" >> "$LOG" \
  || echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARN email failed" >> "$LOG"

# --- Vercel 자동 재배포 (docs/.vercel 링크가 있으면 = 최초 배포 완료 후) ---
if command -v vercel >/dev/null 2>&1 && [ -f "$PROJECT_DIR/docs/.vercel/project.json" ]; then
  ( cd "$PROJECT_DIR/docs" && vercel deploy --prod --yes >> "$LOG" 2>&1 ) \
    && echo "[$(date '+%Y-%m-%d %H:%M:%S')] VERCEL DEPLOYED $DATE $SESSION" >> "$LOG" \
    || echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARN vercel deploy failed (vercel login 확인)" >> "$LOG"
fi
exit $RC
