#!/bin/bash
# launchd LaunchAgent 설치/로드 (1회 실행). 매일 07:00 / 19:00 브리핑 자동 실행.
set -euo pipefail

PROJECT_DIR="/Users/shinheekon/Desktop/ai-project/news"
LABEL="com.shinhee.news-briefing"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
WLABEL="com.shinhee.news-briefing-watchdog"
WPLIST="$HOME/Library/LaunchAgents/$WLABEL.plist"

mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT_DIR/logs"
chmod +x "$PROJECT_DIR/scripts/run-briefing.sh" "$PROJECT_DIR/scripts/catch-up.sh"

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

# --- 워치독 LaunchAgent: 30분마다 누락/실패 회차 자가복구 ---
cat > "$WPLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$WLABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$PROJECT_DIR/scripts/catch-up.sh</string>
    </array>
    <key>StartInterval</key>
    <integer>1800</integer>
    <key>StandardOutPath</key>
    <string>$PROJECT_DIR/logs/watchdog.out.log</string>
    <key>StandardErrorPath</key>
    <string>$PROJECT_DIR/logs/watchdog.err.log</string>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
EOF

# 기존 등록 해제 후 재로드 (idempotent)
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
launchctl unload "$WPLIST" 2>/dev/null || true
launchctl load "$WPLIST"

echo "✅ 설치 완료:"
echo "   - 정시 실행:   $PLIST (07:00 / 19:00)"
echo "   - 워치독 복구: $WPLIST (30분마다 누락 점검)"
echo "   등록 확인:  launchctl list | grep news-briefing"
echo "   즉시 테스트: launchctl start $LABEL"
echo "   해제:        launchctl unload $PLIST $WPLIST"
