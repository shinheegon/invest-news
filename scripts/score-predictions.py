#!/usr/bin/env python3
# 예측 자동 채점기 (brain 설계 B/C) — verification.json의 각 케이스를 네이버 금융 일별시세로
# 채점한다. 핵심: 절대수익이 아니라 **초과수익률(종목 − 지수)** 로 판정(급락장 왜곡 제거).
# 후발경고(type=warning)는 부호 반대(떨어지면 적중). priceLog(주가곡선)도 여기서 채운다.
# 에이전트 아님 — 결정적 파이썬. 표준 라이브러리만(urllib).
import json, os, re, sys, time
from urllib.request import Request, urlopen
from datetime import datetime, timezone, timedelta

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PROJECT, "data")
KST = timezone(timedelta(hours=9))
VF = os.path.join(DATA, "verification.json")
HIT, PART, MISS = "적중", "중립", "빗나감"

def get(url, enc="euc-kr"):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (news-briefing)"})
    return urlopen(req, timeout=12).read().decode(enc, "ignore")

def ticker(name):
    m = re.search(r"\((\d{6})\)", name or "")
    return m.group(1) if m else None

_price_cache, _mkt_cache = {}, {}

def stock_series(code, need_date=None, max_pages=9):
    """네이버 일별시세 → {날짜:종가}. need_date까지 커버되면 조기 종료(성능)."""
    if code in _price_cache:
        return _price_cache[code]
    out = {}
    for p in range(1, max_pages + 1):
        try:
            h = get(f"https://finance.naver.com/item/sise_day.naver?code={code}&page={p}")
        except Exception:
            break
        rows = re.findall(r'class="tah p10 gray03">([\d.]+)</span></td>\s*<td class="num">'
                          r'<span class="tah p11">([\d,]+)</span>', h)
        if not rows:
            break
        for d, c in rows:
            out[d.replace(".", "-")] = int(c.replace(",", ""))
        # 필요한 과거 날짜까지 받았으면 더 안 넘긴다(대부분 1~3페이지에서 종료)
        if need_date and min(out) <= need_date:
            break
    _price_cache[code] = out
    return out

def market_index_code(code):
    """종목의 시장(KOSPI/KOSDAQ) 판별 → 지수 코드."""
    if code in _mkt_cache:
        return _mkt_cache[code]
    idx = "KOSPI"
    try:
        j = json.loads(get(f"https://m.stock.naver.com/api/stock/{code}/basic", "utf-8"))
        et = j.get("stockExchangeType") or {}
        code_s = (et.get("code") or "").upper()          # 'KS'=코스피, 'KQ'=코스닥
        name_s = (et.get("nameEng") or et.get("name") or "").upper()
        if code_s == "KQ" or "KOSDAQ" in name_s:
            idx = "KOSDAQ"
    except Exception:
        pass
    _mkt_cache[code] = idx
    return idx

_index_cache = {}

def index_series(idx_code):
    if idx_code in _index_cache:
        return _index_cache[idx_code]
    out = {}
    for p in range(1, 10):
        try:
            h = get(f"https://finance.naver.com/sise/sise_index_day.naver?code={idx_code}&page={p}")
        except Exception:
            break
        rows = re.findall(r'<td class="date">([\d.]+)</td>\s*<td class="number_1">([\d,]+\.\d+)</td>', h)
        if not rows:
            break
        for d, c in rows:
            out[d.replace(".", "-")] = float(c.replace(",", ""))
    _index_cache[idx_code] = out
    return out

def on_or_before(series_dates, d):
    cand = [x for x in series_dates if x <= d]
    return max(cand) if cand else None

def nth_trading_day(trading_dates, start, n):
    """start(당일 포함 아님) 이후 n번째 영업일 날짜."""
    after = sorted(x for x in trading_dates if x > start)
    return after[n - 1] if len(after) >= n else None

def verdict_of(exc, is_warn):
    """초과수익률 기준 판정(후발경고는 부호 반대)."""
    if is_warn:
        return HIT if exc <= -5 else MISS if exc >= 5 else PART
    return HIT if exc >= 5 else MISS if exc < 0 else PART

def score_case(c, today):
    code = ticker(c.get("name"))
    if not code or (c.get("market") and c["market"] != "韓"):
        return  # 국내 상장만 채점(미국주는 스킵)
    fd = c.get("flagDate")
    is_warn = c.get("type") == "warning"
    c.setdefault("checks", [])
    # 성능: 이미 두 지평(D+3·D+7) 모두 초과수익으로 채점됐고 오늘 priceLog도 있으면 스킵.
    have = {ch.get("horizon"): ch for ch in c["checks"]}
    all_scored = all(h in have and isinstance(have[h].get("excessPct"), (int, float))
                     for h in ("D+3", "D+7"))
    pl_today = any(p.get("date", "") >= today for p in c.get("priceLog", []))
    if c.get("status") == "verified" and all_scored and pl_today:
        return

    px = stock_series(code, need_date=fd)   # flagDate까지만 받고 조기 종료
    if not px:
        return
    idxc = market_index_code(code)
    idx = index_series(idxc)
    pdates, idates = sorted(px), sorted(idx)
    fday = on_or_before(pdates, fd)
    if fday and c.get("flagPrice") in (None, 0):
        c["flagPrice"] = px[fday]
    base = c.get("flagPrice") or (px[fday] if fday else None)
    ibase_day = on_or_before(idates, fd)
    ibase = idx[ibase_day] if ibase_day else None
    if not base or not ibase:
        return

    for hz, n in (("D+3", 3), ("D+7", 7)):
        # 이미 초과수익으로 채점된 지평은 건너뜀. (절대수익만 있던 옛 체크는 재채점)
        if hz in have and isinstance(have[hz].get("excessPct"), (int, float)):
            continue
        tday = nth_trading_day(idates, fd, n)
        if not tday or tday > today:
            continue  # 아직 만기 전
        sday = on_or_before(pdates, tday)
        if not sday:
            continue
        sret = (px[sday] - base) / base * 100
        iret = (idx[tday] - ibase) / ibase * 100
        exc = round(sret - iret, 2)
        rec = {"horizon": hz, "date": sday, "price": px[sday],
               "changePct": round(sret, 2), "indexPct": round(iret, 2),
               "excessPct": exc, "index": idxc, "verdict": verdict_of(exc, is_warn)}
        if hz in have:                      # 기존(절대수익) 체크를 초과수익으로 교체
            have[hz].update(rec)
        else:
            c["checks"].append(rec); have[hz] = rec
    # 오늘 종가 → priceLog(주가곡선)
    tday = on_or_before(pdates, today)
    if tday:
        pl = c.setdefault("priceLog", [])
        if not any(p.get("date") == tday for p in pl):
            pl.append({"date": tday, "price": px[tday]})
    # D+7까지 있거나 flagDate가 7영업일 지났으면 verified
    d7 = nth_trading_day(idates, fd, 7)
    if "D+7" in have or ("D+3" in have and d7 and d7 <= today):
        c["status"] = "verified"

def main():
    if not os.path.exists(VF):
        print("[score] verification.json 없음 — skip"); return
    vf = json.load(open(VF, encoding="utf-8"))
    today = datetime.now(KST).strftime("%Y-%m-%d")
    scored = 0
    for c in vf.get("cases", []):
        try:
            before = len(c.get("checks", []))
            score_case(c, today)
            if len(c.get("checks", [])) > before:
                scored += 1
        except Exception as e:
            sys.stderr.write(f"[score] {c.get('name')} 실패: {e}\n")
    vf["updatedAt"] = datetime.now(KST).isoformat(timespec="seconds")
    json.dump(vf, open(VF, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[score] 신규 채점 {scored}건 / 총 {len(vf.get('cases',[]))}건 (초과수익 기준)")

if __name__ == "__main__":
    main()
