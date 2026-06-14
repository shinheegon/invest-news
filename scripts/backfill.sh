#!/bin/bash
# 지난 39일을 3일 간격(13구간)으로 누적 인덱스에 1회 백필(근사 복원).
# 1회만 실행하면 됨. 기존(오늘) 데이터는 보존하고 과거 날짜만 추가한다.
set -uo pipefail
PROJECT_DIR="/Users/shinheekon/Desktop/ai-project/news"
export PATH="/Users/shinheekon/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
cd "$PROJECT_DIR" || exit 1
LOG="$PROJECT_DIR/logs/run.log"
MARKER="$PROJECT_DIR/data/.backfill-done"

if [ -f "$MARKER" ]; then
  echo "이미 백필됨($(cat "$MARKER")). 중복 방지를 위해 종료. 다시 하려면 data/.backfill-done 삭제."
  exit 0
fi

# 13개 3일 구간 생성 (어제 기준 최신→과거)
END=$(date -j -v-1d +%Y-%m-%d)            # 어제
BUCKETS=""
for i in $(seq 0 12); do
  be=$(date -j -v-$((i*3))d   -f "%Y-%m-%d" "$END" +%Y-%m-%d)
  bs=$(date -j -v-$((i*3+2))d -f "%Y-%m-%d" "$END" +%Y-%m-%d)
  BUCKETS="${BUCKETS}${bs}..${be}|"
done
export BACKFILL_BUCKETS="$BUCKETS"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] BACKFILL START buckets=$BUCKETS" >> "$LOG"
echo "백필 구간(13): $BUCKETS"

claude -p "$(cat "$PROJECT_DIR/prompt/backfill-prompt.md")" \
  --permission-mode acceptEdits \
  --allowedTools "WebSearch,WebFetch,Read,Write,Edit,Bash" \
  >> "$LOG" 2>&1
RC=$?

if [ $RC -eq 0 ]; then
  date '+%Y-%m-%d %H:%M:%S' > "$MARKER"
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] BACKFILL DONE rc=0" >> "$LOG"
  bash "$PROJECT_DIR/scripts/build-site.sh" >> "$LOG" 2>&1 || true
  echo "✅ 백필 완료 — 사이트 빌드까지 반영"
else
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] BACKFILL ERROR rc=$RC" >> "$LOG"
  echo "❌ 백필 실패 (logs/run.log 확인)"
fi
exit $RC
