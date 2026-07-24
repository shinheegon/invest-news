#!/usr/bin/env python3
# KRX 전종목 사전 생성 — 네이버에서 코스피/코스닥 상장사 전체(코드·이름·시장)를 받아
# data/krx-names.json 으로 저장. 틈새 레이더가 '모든 헤드라인을 상장사 이름으로 스캔'하는
# 기반 사전이다. 자주 안 바뀌므로 주 1회 정도 갱신하면 충분(파이프라인에선 없을 때만 생성).
# 표준 라이브러리만.
import json, os, sys
from urllib.request import Request, urlopen
from datetime import datetime, timezone, timedelta

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PROJECT, "data")
KST = timezone(timedelta(hours=9))
OUT = os.path.join(DATA, "krx-names.json")

# 우선주·스팩·리츠 등 노이즈 제외 접미/패턴
def is_noise(name):
    if not name:
        return True
    if name.endswith(("우", "우B")) and len(name) >= 3:  # 우선주(삼성전자우 등)
        return True
    if "스팩" in name:            # SPAC
        return True
    return False


def get(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urlopen(req, timeout=20).read().decode("utf-8", "ignore")


def fetch_market(mkt):
    out = {}
    page = 1
    while page <= 60:
        try:
            j = json.loads(get(f"https://m.stock.naver.com/api/stocks/marketValue/{mkt}?page={page}&pageSize=100"))
        except Exception:
            break
        stocks = j.get("stocks") or []
        if not stocks:
            break
        for s in stocks:
            code, nm = s.get("itemCode"), s.get("stockName")
            if code and nm and not is_noise(nm):
                try:
                    cap = int(str(s.get("marketValue") or "").replace(",", ""))  # 억원 단위
                except Exception:
                    cap = None
                out[code] = {"name": nm, "market": mkt, "cap": cap}
        page += 1
    return out


def main():
    # 자주 안 바뀌므로 7일 이내 갱신됐으면 스킵(파이프라인에서 매번 안 받게)
    if os.path.exists(OUT):
        try:
            prev = json.load(open(OUT, encoding="utf-8"))
            up = datetime.fromisoformat(prev.get("updatedAt"))
            if (datetime.now(KST) - up).days < 7 and prev.get("count", 0) > 2000:
                print(f"[krx] 최근 갱신({up.date()})·{prev['count']}종목 — 스킵"); return
        except Exception:
            pass
    total = {}
    for mkt in ("KOSPI", "KOSDAQ"):
        m = fetch_market(mkt)
        total.update(m)
        print(f"[krx] {mkt}: {len(m)}건")
    if len(total) < 2000:
        print(f"[krx] 수집 부족({len(total)}) — 기존 사전 유지"); return
    doc = {"updatedAt": datetime.now(KST).isoformat(timespec="seconds"),
           "count": len(total), "stocks": total}
    json.dump(doc, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"[krx] 사전 저장 {len(total)}종목 → {OUT}")


if __name__ == "__main__":
    main()
