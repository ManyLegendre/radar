"""Analyse d'actions : indicateurs, score, alertes ntfy, génération de docs/data.json."""
import datetime as dt, hashlib, json, math, os, statistics, sys
import requests, yaml, yfinance as yf

ROOT = os.path.dirname(os.path.abspath(__file__))
CFG = yaml.safe_load(open(os.path.join(ROOT, "config.yaml"), encoding="utf-8"))
TH = CFG["thresholds"]
STATE_F, OUT_F = os.path.join(ROOT, "state.json"), os.path.join(ROOT, "docs", "data.json")
STATE = json.load(open(STATE_F)) if os.path.exists(STATE_F) else {}
TODAY = dt.date.today().isoformat()
POS = ["hausse", "bondit", "record", "relève", "dépasse", "upgrade", "beat", "surge", "jumps", "raises", "strong", "contrat", "wins"]
NEG = ["baisse", "chute", "recule", "avertissement", "abaisse", "downgrade", "miss", "plunge", "falls", "cuts", "warning", "lawsuit", "enquête", "amende", "probe", "fraud"]

def num(x):
    try:
        x = float(x)
        return None if math.isnan(x) or math.isinf(x) else round(x, 4)
    except (TypeError, ValueError):
        return None

def clamp(x):
    return max(0, min(100, x))

def notify(key, title, msg, prio=3, tags=None, click=None):
    sent = STATE.setdefault("sent", [])
    if key in sent:
        return
    sent.append(key)
    del sent[:-500]
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print("NTFY_TOPIC absent, alerte non envoyée :", title)
        return
    body = {"topic": topic, "title": title, "message": msg, "priority": prio, "tags": tags or []}
    if click:
        body["click"] = click
    try:
        requests.post("https://ntfy.sh/", json=body, timeout=15)
    except Exception as e:
        print("ntfy KO :", e)

def rsi(c, n=14):
    d = c.diff()
    up, dn = d.clip(lower=0).rolling(n).mean().iloc[-1], (-d.clip(upper=0)).rolling(n).mean().iloc[-1]
    return 100.0 if not dn else float(100 - 100 / (1 + up / dn))

def sentiment(title):
    t = title.lower()
    p, n = sum(w in t for w in POS), sum(w in t for w in NEG)
    return (p > n) - (n > p)

def get_news(t):
    try:
        items = t.news or []
    except Exception:
        items = []
    out = []
    for n in items[:8]:
        c = n.get("content", n)
        if not c.get("title"):
            continue
        out.append({
            "title": c["title"],
            "url": (c.get("canonicalUrl") or {}).get("url") or c.get("link"),
            "source": (c.get("provider") or {}).get("displayName") or c.get("publisher"),
            "date": str(c.get("pubDate") or "")[:10],
            "sentiment": sentiment(c["title"]),
        })
    return out

def peer(sym):
    try:
        t = yf.Ticker(sym)
        i, h = t.info or {}, t.history(period="6mo")["Close"]
        return {"symbol": sym, "name": i.get("shortName", sym), "pe": num(i.get("trailingPE")),
                "margin": num(i.get("profitMargins")), "growth": num(i.get("revenueGrowth")),
                "perf6m": num(h.iloc[-1] / h.iloc[0] - 1) if len(h) > 1 else None}
    except Exception as e:
        print("concurrent KO", sym, e)
        return {"symbol": sym, "name": sym}

def score(i, price, ma200, rsi_v, med_pe):
    comp, pe = {}, i.get("trailingPE")
    if pe and pe > 0 and med_pe:
        comp["Valorisation"] = clamp(50 + (1 - pe / med_pe) * 100)
    if i.get("revenueGrowth") is not None:
        comp["Croissance"] = clamp(50 + i["revenueGrowth"] * 250)
    if i.get("profitMargins") is not None:
        comp["Rentabilité"] = clamp(i["profitMargins"] * 400)
    if i.get("debtToEquity") is not None:
        comp["Bilan"] = clamp(100 - i["debtToEquity"] / 2)
    if ma200:
        comp["Tendance"] = clamp(50 + (price / ma200 - 1) * 200 - (15 if rsi_v > 70 else 0))
    if i.get("targetMeanPrice"):
        comp["Consensus analystes"] = clamp(50 + (i["targetMeanPrice"] / price - 1) * 250)
    comp = {k: round(v) for k, v in comp.items()}
    return (round(sum(comp.values()) / len(comp)) if comp else None), comp

def analyze(entry):
    sym = entry["symbol"]
    t = yf.Ticker(sym)
    h = t.history(period="1y", auto_adjust=True)
    if len(h) < 30:
        print("pas de données pour", sym)
        return None
    c, v, i = h["Close"], h["Volume"], (t.info or {})
    price, prev = float(c.iloc[-1]), float(c.iloc[-2])
    chg = price / prev - 1
    ma50s, ma200s = c.rolling(50).mean(), c.rolling(200).mean()
    ma200, rsi_v = num(ma200s.iloc[-1]), rsi(c)
    avg_v = v.iloc[-21:-1].mean()
    vol_ratio = num(v.iloc[-1] / avg_v) if avg_v else None
    peers = [peer(p) for p in entry.get("peers", [])]
    pes = [p["pe"] for p in peers if p.get("pe") and p["pe"] > 0]
    med_pe = statistics.median(pes) if pes else None
    sc, comp = score(i, price, ma200, rsi_v, med_pe)
    earn = None
    try:
        e = t.calendar.get("Earnings Date")
        earn = str(e[0]) if e else None
    except Exception:
        pass
    news, name, flags = get_news(t), i.get("shortName", sym), []

    def alert(kind, title, msg, prio=3, tags=None, suffix=TODAY, click=None):
        flags.append(title)
        notify(f"{sym}:{kind}:{suffix}", f"{name} ({sym}) : {title}", msg, prio, tags, click)

    if abs(chg) >= TH["move_pct"] / 100:
        alert("move+" if chg > 0 else "move-", f"{chg * 100:+.1f} % aujourd'hui",
              f"Cours {price:.2f}, variation vs clôture précédente {chg * 100:+.1f} %.", 4,
              ["chart_with_upwards_trend" if chg > 0 else "chart_with_downwards_trend"])
    if vol_ratio and vol_ratio >= TH["volume_ratio"]:
        alert("vol", f"Volume x{vol_ratio:.1f}", "Volume anormalement élevé par rapport à la moyenne 20 jours.")
    if rsi_v >= TH["rsi_high"]:
        alert("rsi+", f"RSI {rsi_v:.0f} (surachat)", "Le titre a beaucoup monté à court terme.")
    elif rsi_v <= TH["rsi_low"]:
        alert("rsi-", f"RSI {rsi_v:.0f} (survente)", "Le titre a beaucoup baissé à court terme.")
    past = c.iloc[-253:-1]
    if price >= past.max():
        alert("hi", "Plus haut 52 semaines", f"Nouveau sommet à {price:.2f}.", 4)
    elif price <= past.min():
        alert("lo", "Plus bas 52 semaines", f"Nouveau plancher à {price:.2f}.", 4)
    d = (ma50s - ma200s).dropna()
    if len(d) > 1 and d.iloc[-1] * d.iloc[-2] < 0:
        alert("cross", "Golden cross" if d.iloc[-1] > 0 else "Death cross", "La moyenne mobile 50 jours croise la 200 jours.", 4)
    if earn:
        days = (dt.date.fromisoformat(earn[:10]) - dt.date.today()).days
        if 0 <= days <= TH["earnings_days"]:
            alert("earn", f"Résultats dans {days} j", f"Publication prévue le {earn[:10]}.", 4, suffix=earn[:10])
    seen = STATE.setdefault("news", {})
    known, first = set(seen.get(sym, [])), sym not in seen
    for n in news:
        if n["title"] not in known and not first and n["sentiment"] != 0:
            alert("news", "Actualité " + ("positive" if n["sentiment"] > 0 else "négative"), n["title"], 3,
                  ["newspaper"], suffix=hashlib.md5(n["title"].encode()).hexdigest()[:10], click=n["url"])
    seen[sym] = list(dict.fromkeys([n["title"] for n in news] + list(known)))[:50]

    keys = ["marketCap", "trailingPE", "forwardPE", "priceToBook", "revenueGrowth", "profitMargins",
            "operatingMargins", "returnOnEquity", "debtToEquity", "freeCashflow", "beta", "targetMeanPrice"]
    return {"symbol": sym, "name": name, "sector": i.get("sector"), "currency": i.get("currency"),
            "price": num(price), "change": num(chg), "score": sc, "components": comp, "rsi": num(rsi_v),
            "ma50": num(ma50s.iloc[-1]), "ma200": ma200, "volume_ratio": vol_ratio,
            "high52": num(c.max()), "low52": num(c.min()), "earnings": earn,
            "metrics": {k: num(i.get(k)) for k in keys}, "recommendation": i.get("recommendationKey"),
            "peers": peers, "median_peer_pe": num(med_pe), "news": news, "flags": flags,
            "spark": [round(float(x), 2) for x in c.iloc[-120:]]}

def main():
    if "--test" in sys.argv:
        notify("test:" + dt.datetime.now().isoformat(), "Test Radar actions", "Les notifications fonctionnent.")
        return
    res = []
    for e in CFG["watchlist"]:
        try:
            r = analyze(e)
            if r:
                res.append(r)
        except Exception as ex:
            print("ERREUR", e["symbol"], ex)
    if not res:
        sys.exit("Aucune donnée récupérée : données précédentes conservées.")
    os.makedirs(os.path.dirname(OUT_F), exist_ok=True)
    json.dump({"updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "tickers": res},
              open(OUT_F, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(STATE, open(STATE_F, "w", encoding="utf-8"), ensure_ascii=False)

if __name__ == "__main__":
    main()
