#!/usr/bin/env python3
# 매매일지 엔진 — 매수/매도 기록 + 성공률·수익 통계를 결정적으로 계산.
# 사용:
#   buy:  portfolio.py buy  --name "대한광통신(010170)" --price 12000 --qty 10 \
#                           [--date 2026-06-16] [--market 韓] [--theme "AI DC 광케이블"] \
#                           [--reason "선행포착 355억 계약"] [--source URL]
#   sell: portfolio.py sell --id p1 --price 14000 [--date ...] [--reason "목표가 도달"]
#         (또는 --name 으로 가장 오래된 open 포지션을 청산)
#   stats: portfolio.py recompute
import json, os, sys, argparse
from datetime import datetime, timezone, timedelta

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PROJECT, "data")
FILE = os.path.join(DATA, "portfolio.json")
KST = timezone(timedelta(hours=9))

def today():
    return datetime.now(KST).strftime("%Y-%m-%d")

def load():
    if os.path.exists(FILE):
        return json.load(open(FILE, encoding="utf-8"))
    return {"updatedAt": None, "positions": [], "stats": {}}

def days_between(a, b):
    try:
        da = datetime.strptime(a[:10], "%Y-%m-%d"); db = datetime.strptime(b[:10], "%Y-%m-%d")
        return (db - da).days
    except Exception:
        return None

def recompute(pf):
    closed = [p for p in pf["positions"] if p.get("status") == "closed" and p.get("sell")]
    rets, pnl, wins = [], 0.0, 0
    for p in closed:
        bp = p["buy"]["price"]; sp = p["sell"]["price"]; qty = p["buy"].get("qty", 0) or 0
        r = (sp - bp) / bp * 100 if bp else 0
        p["returnPct"] = round(r, 2)
        p["pnl"] = round((sp - bp) * qty, 2)
        p["heldDays"] = days_between(p["buy"]["date"], p["sell"]["date"])
        rets.append(r); pnl += p["pnl"]; wins += 1 if r > 0 else 0
    n = len(closed)
    best = max(closed, key=lambda p: p["returnPct"], default=None)
    worst = min(closed, key=lambda p: p["returnPct"], default=None)
    pf["stats"] = {
        "openCount": sum(1 for p in pf["positions"] if p.get("status") == "open"),
        "closedCount": n,
        "wins": wins, "losses": n - wins,
        "winRate": round(wins / n * 100, 1) if n else None,
        "avgReturnPct": round(sum(rets) / n, 2) if n else None,
        "realizedPnl": round(pnl, 2),
        "best": {"name": best["name"], "returnPct": best["returnPct"]} if best else None,
        "worst": {"name": worst["name"], "returnPct": worst["returnPct"]} if worst else None,
    }
    pf["updatedAt"] = datetime.now(KST).isoformat(timespec="seconds")
    return pf

def save(pf):
    os.makedirs(DATA, exist_ok=True)
    json.dump(recompute(pf), open(FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def next_id(pf):
    n = 0
    for p in pf["positions"]:
        try: n = max(n, int(str(p["id"]).lstrip("p")))
        except Exception: pass
    return f"p{n + 1}"

def cmd_buy(a):
    pf = load()
    pid = next_id(pf)
    pf["positions"].append({
        "id": pid, "name": a.name, "market": a.market, "theme": a.theme or "",
        "status": "open", "sell": None,
        "buy": {"date": a.date or today(), "price": a.price, "qty": a.qty,
                "reason": a.reason or "", "source": a.source or ""},
    })
    save(pf)
    print(f"[buy] {pid} {a.name} @ {a.price} x{a.qty} ({a.date or today()}) 기록 완료")

def cmd_sell(a):
    pf = load()
    target = None
    if a.id:
        target = next((p for p in pf["positions"] if p["id"] == a.id and p["status"] == "open"), None)
    elif a.name:
        opens = [p for p in pf["positions"] if p["name"] == a.name and p["status"] == "open"]
        target = opens[0] if opens else None
    if not target:
        print(f"[sell] 매칭되는 보유 포지션 없음 (id={a.id} name={a.name})"); sys.exit(1)
    target["sell"] = {"date": a.date or today(), "price": a.price, "reason": a.reason or ""}
    target["status"] = "closed"
    save(pf)
    bp = target["buy"]["price"]; r = (a.price - bp) / bp * 100 if bp else 0
    print(f"[sell] {target['id']} {target['name']} @ {a.price} 청산 — 수익률 {r:+.2f}%")

def cmd_recompute(a):
    pf = load(); save(pf)
    print(f"[stats] {json.dumps(pf['stats'], ensure_ascii=False)}")

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("buy");  b.set_defaults(fn=cmd_buy)
    b.add_argument("--name", required=True); b.add_argument("--price", type=float, required=True)
    b.add_argument("--qty", type=float, default=0); b.add_argument("--date")
    b.add_argument("--market", default="韓"); b.add_argument("--theme")
    b.add_argument("--reason"); b.add_argument("--source")
    s = sub.add_parser("sell"); s.set_defaults(fn=cmd_sell)
    s.add_argument("--id"); s.add_argument("--name"); s.add_argument("--price", type=float, required=True)
    s.add_argument("--date"); s.add_argument("--reason")
    r = sub.add_parser("recompute"); r.set_defaults(fn=cmd_recompute)
    a = ap.parse_args(); a.fn(a)

if __name__ == "__main__":
    main()
