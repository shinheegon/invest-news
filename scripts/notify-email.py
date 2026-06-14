#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""브리핑 요약 + 키워드/종목 급등 감지 → 이메일 발송 (Resend API, 표준 라이브러리만 사용).
환경변수:
  RESEND_API_KEY : Resend API 키 (없으면 발송 대신 data/email-preview.html 로 저장)
  TO_EMAIL       : 받는 사람 (기본 shinheegon@gmail.com)
  FROM_EMAIL     : 보내는 사람 (기본 onboarding@resend.dev — Resend 무료 발신 주소)
  BRIEFING_SESSION, BRIEFING_DATE : 회차/날짜 (없으면 자동)
"""
import os, re, json, datetime, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SITE_URL = "https://invest-news-olive.vercel.app"

def read(path):
    try:
        with open(os.path.join(DATA, path), encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""

def load(path):
    try:
        with open(os.path.join(DATA, path), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def section(md, header):
    """마크다운에서 '## header' 섹션 본문만 추출."""
    if not md:
        return ""
    lines = md.splitlines()
    out, cap = [], False
    for ln in lines:
        if ln.startswith("## "):
            cap = header in ln
            continue
        if cap:
            out.append(ln)
    return "\n".join(out).strip()

def bullets(text, limit=6):
    items = [re.sub(r"\[출처\]\([^)]*\)", "", l).strip(" -*").strip()
             for l in text.splitlines() if l.strip().startswith("-")]
    return [i for i in items if i][:limit]

# ---------- 급등 감지 ----------
def spikes(index, coll, min_today=2, min_delta=2):
    """가장 최근 두 날짜의 daily 비교 → 급등 항목."""
    items = index.get(coll, {})
    res = []
    for name, v in items.items():
        daily = v.get("daily", {})
        ds = sorted(daily.keys())
        if len(ds) < 1:
            continue
        today = daily.get(ds[-1], 0)
        prev = daily.get(ds[-2], 0) if len(ds) >= 2 else 0
        delta = today - prev
        if today >= min_today and delta >= min_delta:
            pct = int(delta / prev * 100) if prev > 0 else 100
            res.append((name, today, delta, pct, v.get("market", "")))
    res.sort(key=lambda x: (x[2], x[1]), reverse=True)
    return res[:8]

def watchlist_hits(wl, kw_idx, co_idx, dc_idx):
    """관심종목/키워드가 오늘 등장/급등했는지."""
    hits = []
    names = set(wl.get("tickers", []))
    kws = set(wl.get("keywords_to_watch", []))
    for nm in names:
        for idx, coll in ((co_idx, "companies"), (dc_idx, "companies")):
            v = idx.get(coll, {}).get(nm)
            if v:
                ds = sorted(v.get("daily", {}).keys())
                if ds:
                    hits.append(f"{nm} — 오늘 {v['daily'][ds[-1]]}회 언급 (누적 {v.get('count',0)})")
                break
    for kw in kws:
        v = kw_idx.get("keywords", {}).get(kw)
        if v:
            ds = sorted(v.get("daily", {}).keys())
            if ds:
                hits.append(f"키워드 '{kw}' — 오늘 {v['daily'][ds[-1]]}회")
    return hits

# ---------- 본문 구성 ----------
def build():
    session = os.environ.get("BRIEFING_SESSION", "")
    date = os.environ.get("BRIEFING_DATE", datetime.date.today().isoformat())
    sess_ko = "오전" if session == "AM" else "오후" if session == "PM" else ""

    latest = read("latest.md")
    review = read("review.md")
    discovery = read("discovery.md")

    tldr = bullets(section(latest, "한눈에 보기"), 5)
    watch_sec = bullets(section(latest, "관심종목 동향"), 5)
    boss = bullets(section(review, "최종 의견"), 3) or bullets(section(review, "Top 3"), 3)
    rising = bullets(section(discovery, "누적 부상"), 4)

    kw, co, dc = load("keyword-index.json"), load("company-index.json"), load("discovery-index.json")
    wl = load("watchlist.json")
    kw_spikes = spikes(kw, "keywords")
    co_spikes = spikes(co, "companies")
    dc_spikes = spikes(dc, "companies")
    wl_hits = watchlist_hits(wl, kw, co, dc)

    def ul(items):
        return "".join(f"<li>{x}</li>" for x in items) if items else "<li style='color:#888'>특이사항 없음</li>"

    def spike_ul(rows, kind):
        if not rows:
            return "<li style='color:#888'>오늘 두드러진 급등 없음</li>"
        return "".join(
            f"<li><b>{n}</b> {('('+m+') ' if m else '')}— 오늘 {t}회 "
            f"<span style='color:#c0392b'>▲{d} ({p}%)</span></li>" for n, t, d, p, m in rows)

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,'Apple SD Gothic Neo',sans-serif;max-width:640px;margin:0 auto;color:#1a1a1a;line-height:1.6">
  <h2 style="border-bottom:2px solid #2f81f7;padding-bottom:8px">📰 투자 브리핑 — {date} {sess_ko}</h2>

  <h3>🎯 한눈에 보기</h3><ul>{ul(tldr)}</ul>

  <h3>⭐ 관심종목 동향</h3><ul>{ul(watch_sec)}</ul>
  {('<p style="background:#fff8e1;padding:8px;border-radius:6px"><b>🔔 관심 신호</b><br>'+'<br>'.join(wl_hits)+'</p>') if wl_hits else ''}

  <h3>🔥 누적 부상 소형주</h3><ul>{ul(rising)}</ul>

  <h3>🕵️ 중간보스 최종 의견 (오늘 주목 Top3)</h3><ul>{ul(boss)}</ul>

  <h3>📈 오늘 급등 감지</h3>
  <p style="margin:4px 0"><b>키워드</b></p><ul>{spike_ul(kw_spikes,'kw')}</ul>
  <p style="margin:4px 0"><b>회사</b></p><ul>{spike_ul(co_spikes,'co')}</ul>
  <p style="margin:4px 0"><b>발굴 소형주</b></p><ul>{spike_ul(dc_spikes,'dc')}</ul>

  <p style="margin-top:24px"><a href="{SITE_URL}" style="background:#2f81f7;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none">📊 전체 대시보드 보기</a></p>
  <p style="color:#888;font-size:13px;margin-top:20px">⚠️ 본 메일은 공개 정보를 요약한 자료이며 투자 권유가 아닙니다. 모든 판단과 책임은 투자자 본인에게 있습니다.</p>
</body></html>"""

    subject = f"📰 투자 브리핑 {date} {sess_ko}"
    if kw_spikes or co_spikes or wl_hits:
        top = (kw_spikes or co_spikes)[0][0] if (kw_spikes or co_spikes) else ""
        subject += f" · 🔔 급등 {top}"
    return subject, html

def send(subject, html):
    key = os.environ.get("RESEND_API_KEY", "").strip()
    to = os.environ.get("TO_EMAIL", "shinheegon@gmail.com")
    frm = os.environ.get("FROM_EMAIL", "onboarding@resend.dev")
    if not key:
        out = os.path.join(DATA, "email-preview.html")
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[notify] RESEND_API_KEY 없음 → 미리보기 저장: {out}")
        print(f"[notify] 제목: {subject} / 받는이: {to}")
        return 0
    payload = json.dumps({"from": frm, "to": [to], "subject": subject, "html": html}).encode()
    req = urllib.request.Request("https://api.resend.com/emails", data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"[notify] 이메일 발송 완료 → {to} (status {r.status})")
            return 0
    except urllib.error.HTTPError as e:
        print(f"[notify] 발송 실패 {e.code}: {e.read().decode()[:300]}")
        return 1
    except Exception as e:
        print(f"[notify] 발송 오류: {e}")
        return 1

if __name__ == "__main__":
    s, h = build()
    raise SystemExit(send(s, h))
