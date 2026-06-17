#!/bin/bash
# 워치독 자가복구 — 30분마다 launchd가 호출.
# 정시(7시/19시) 실행이 실패/누락됐는지 점검하고, 비어 있으면 그 회차를 보충 실행한다.
# run-briefing.sh의 잠금·멱등성이 중복을 막아주므로 안심하고 자주 돌려도 된다.
set -uo pipefail
PROJECT_DIR="/Users/shinheekon/Desktop/ai-project/news"
export PATH="/Users/shinheekon/.local/bin:/Users/shinheekon/.local/node/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
cd "$PROJECT_DIR" || exit 1
LOG="$PROJECT_DIR/logs/watchdog.log"
mkdir -p "$PROJECT_DIR/logs"
ts() { date '+%Y-%m-%d %H:%M:%S'; }

DATE=$(date +%Y-%m-%d)
H=$(date +%H); H=$((10#$H))   # 8진수 오해 방지

# run-briefing이 돌고 있으면 보통 손대지 않는다. 단 **40분 넘게 잠금이 유지되면
# hang(절전 중 멈춤 등)으로 보고 강제 정리** 후 보충 실행한다(좀비가 다음 회차를 막는 것 방지).
LOCK="$PROJECT_DIR/data/.run-lock"
if [ -f "$LOCK" ]; then
  PID="$(cat "$LOCK" 2>/dev/null)"
  if [ -n "${PID:-}" ] && kill -0 "$PID" 2>/dev/null; then
    AGE=$(( $(date +%s) - $(stat -f %m "$LOCK" 2>/dev/null || echo 0) ))
    if [ "$AGE" -lt 2400 ]; then
      exit 0   # 정상 실행 중(40분 이내) — 조용히 종료
    fi
    echo "[$(ts)] HUNG 감지 — 잠금 ${AGE}s 경과, 좀비 정리" >> "$LOG"
    pkill -f "claude -p # 투자용 경제뉴스 브리핑 생성 지시문" 2>/dev/null
    kill "$PID" 2>/dev/null
    rm -f "$LOCK"
  fi
fi

trigger() {  # $1 = AM|PM
  local sess="$1"
  echo "[$(ts)] CATCHUP 누락 감지 → $DATE-$sess 보충 실행" >> "$LOG"
  bash "$PROJECT_DIR/scripts/run-briefing.sh" "$sess" >> "$LOG" 2>&1 &
}

# AM 창: 07시 이후인데 오늘 AM 브리핑 파일이 없으면 보충
if [ "$H" -ge 7 ] && [ ! -f "$PROJECT_DIR/briefings/$DATE-AM.md" ]; then
  trigger AM
  exit 0   # 한 번에 하나만(자원 보호) — 다음 점검에서 PM 처리
fi

# PM 창: 19시 이후인데 오늘 PM 브리핑 파일이 없으면 보충
if [ "$H" -ge 19 ] && [ ! -f "$PROJECT_DIR/briefings/$DATE-PM.md" ]; then
  trigger PM
fi
