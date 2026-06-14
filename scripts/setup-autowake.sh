#!/bin/bash
# 맥 자동 깨우기 설정 (관리자 암호 1회 필요).
# 매일 아침 06:50에 맥을 깨워 07:00 브리핑이 자고 있어도 실행되게 한다.
# (pmset 반복 깨우기는 하루 1회만 지원 → 가장 중요한 아침을 커버.
#  저녁 19시는 보통 맥이 켜져 있고, 자고 있었으면 깨어난 직후 자동 보강된다.)
set -e
echo "▶ 자동 깨우기 설정 — 관리자(맥 로그인) 암호를 물어보면 입력하세요."
sudo pmset repeat wakeorpoweron MTWRFSU 06:50:00
echo ""
echo "✅ 설정 완료. 현재 예약:"
pmset -g sched
echo ""
echo "해제하려면:  sudo pmset repeat cancel"
