#!/bin/bash
# launchd LaunchAgent 설치/로드 (1회 실행). 매일 07:00 / 19:00 브리핑 자동 실행.
set -euo pipefail

PROJECT_DIR="/Users/shinheekon/Desktop/ai-project/news"
LABEL="com.shinhee.news-briefing"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT_DIR/logs"
chmod +x "$PROJECT_DIR/scripts/run-briefing.sh"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$PROJECT_DIR/scripts/run-briefing.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <array>
        <dict>
            <key>Hour</key><integer>7</integer>
            <key>Minute</key><integer>0</integer>
        </dict>
        <dict>
            <key>Hour</key><integer>19</integer>
            <key>Minute</key><integer>0</integer>
        </dict>
    </array>
    <key>StandardOutPath</key>
    <string>$PROJECT_DIR/logs/launchd.out.log</string>
    <key>StandardErrorPath</key>
    <string>$PROJECT_DIR/logs/launchd.err.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
EOF

# 기존 등록 해제 후 재로드 (idempotent)
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo "✅ 설치 완료: $PLIST"
echo "   등록 확인:  launchctl list | grep news-briefing"
echo "   즉시 테스트: launchctl start $LABEL"
echo "   해제:        launchctl unload $PLIST"
