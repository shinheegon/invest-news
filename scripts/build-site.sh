#!/bin/bash
# 데이터를 docs/(공개 사이트)로 복사하고 아카이브 manifest를 생성한다.
# 맥·클라우드(CI) 양쪽에서 동작하도록 스크립트 위치 기준 상대경로 사용.
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

mkdir -p docs/data/briefings

# 0) 과거·신규 브리핑의 종목별 출처 링크를 기사 아카이브에 소급 병합(멱등)
python3 scripts/backfill-archive.py || echo "WARN backfill-archive 실패(건너뜀)"

# 1) 데이터 파일 복사 (없으면 건너뜀)
for f in keyword-index.json company-index.json discovery-index.json leading-index.json article-archive.json market-indicators.json market-history.json portfolio.json verification.json latest.md synthesis-3day.md analysis.md discovery.md leading-signals.md review.md holdings-analysis.md verification.md; do
  [ -f "data/$f" ] && cp "data/$f" "docs/data/$f"
done

# 2) 브리핑 본문 복사
if ls briefings/*.md >/dev/null 2>&1; then
  cp briefings/*.md docs/data/briefings/ 2>/dev/null || true
fi

# 3) 아카이브 manifest 생성 (파일명: YYYY-MM-DD-AM|PM.md)
python3 - <<'PY'
import json, os, re, glob
items = []
for path in sorted(glob.glob("briefings/*.md")):
    base = os.path.basename(path)
    m = re.match(r"(\d{4}-\d{2}-\d{2})-(AM|PM)\.md$", base)
    if not m:
        continue
    items.append({"date": m.group(1), "session": m.group(2),
                  "file": f"briefings/{base}"})
items.sort(key=lambda x: (x["date"], 0 if x["session"] == "AM" else 1))
os.makedirs("docs/data", exist_ok=True)
with open("docs/data/briefings.json", "w", encoding="utf-8") as f:
    json.dump({"count": len(items), "briefings": items}, f, ensure_ascii=False, indent=2)
print(f"manifest: {len(items)} briefings")
PY

echo "✅ 사이트 빌드 완료 → docs/"
