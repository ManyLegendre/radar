"""Étude d'entrée en position : que se passe-t-il ensuite selon le signal d'entrée ? Génère docs/etude.html."""
import datetime as dt, html, math, os, sys
import numpy as np, pandas as pd, yaml, yfinance as yf

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "docs", "etude.html")
HORIZONS = {20: "1 mois", 60: "3 mois", 125: "6 mois", 250: "12 mois"}
YEARS_BACK = 15

def rsi_series(c, n=14):
    d = c.diff()
    up, dn = d.clip(lower=0).rolling(n).mean(), (-d.clip(upper=0)).rolling(n).mean()
    return 100 - 100 / (1 + up / dn)

def dedupe(pos, gap=20):
    """Garde le premier signal de chaque série (évite de compter 20 fois le même épisode)."""
    out, last = [], -10**9
    for i in pos:
        if i - last >= gap:
            out.append(int(i))
            last = i
    return out

def signals(c, earn):
    """{nom du signal: [positions d'entrée]} pour une action."""
    ma200, hi = c.rolling(200).mean(), c.rolling(252).max()
    dd = c / hi - 1
    b = lambda s: np.flatnonzero(s.to_numpy())
    sig = {
        "Survente (RSI < 30)": dedupe(b(rsi_series(c) < 30)),
        "Repli ≥ 20 % sous le plus haut annuel": dedupe(b(dd <= -0.20)),
        "Repli ≥ 30 % sous le plus haut annuel": dedupe(b(dd <= -0.30)),
        "Chute ≥ 5 % en une séance": dedupe(b(c.pct_change() <= -0.05)),
        "Cassure à la baisse de la MM200": dedupe(b((c < ma200) & (c.shift() >= ma200.shift()))),
        "Nouveau plus haut annuel": dedupe(b(c >= hi)),
    }
    pe = [(int(c.index.searchsorted(d))) for d in earn]
    pe = [p for p in pe if 6 <= p < len(c) - 1]
    react = {p: c.iloc[p + 1] / c.iloc[p - 1] - 1 for p in pe}
    sig["5 jours avant les résultats"] = [p - 5 for p in pe]
    sig["Après les résultats (toutes publications)"] = [p + 1 for p in pe]
    sig["Après les résultats, réaction ≤ -4 %"] = [p + 1 for p in pe if react[p] <= -0.04]
    sig["Après les résultats, réaction ≥ +4 %"] = [p + 1 for p in pe if react[p] >= 0.04]
    return sig

def run(data):
    """data = {symbole: (série de clôtures, dates de résultats)} -> {(signal, horizon): [événements]}"""
    ev = {}
    for sym, (c, earn) in data.items():
        fw = {h: c.shift(-h) / c - 1 for h in HORIZONS}
        base = {h: (fw[h].dropna().mean(), (fw[h].dropna() > 0).mean()) for h in HORIZONS}
        for name, pos in signals(c, earn).items():
            for h in HORIZONS:
                for i in pos:
                    r = fw[h].iloc[i]
                    if pd.notna(r):
                        ev.setdefault((name, h), []).append((r, r - base[h][0], base[h][1], int(c.index[i].year), sym))
    return ev

def stats(rows):
    r, ex = np.array([x[0] for x in rows]), np.array([x[1] for x in rows])
    n, sd = len(r), ex.std(ddof=1) if len(r) > 1 else 0
    t = ex.mean() / (sd / math.sqrt(n)) if sd > 0 else 0
    yrs = len({x[3] for x in rows})
    if n < 30 or yrs < 5:
        verdict = ("Trop peu de données", "na")
    elif ex.mean() > 0 and t > 2:
        verdict = ("Indice à creuser", "ok")
    elif ex.mean() < 0 and t < -2:
        verdict = ("Défavorable", "bad")
    else:
        verdict = ("Pas d'avantage net", "na")
    return dict(n=n, yrs=yrs, mean=r.mean(), med=float(np.median(r)), hit=(r > 0).mean(),
                base_hit=np.mean([x[2] for x in rows]), ex=ex.mean(), verdict=verdict)

CSS = """:root{--bg:#f3f4f7;--panel:#fff;--tx:#121826;--mut:#667085;--ln:#dde1e8;--ok:#0f7b57;--bad:#c23b32;--ac:#33498a}
@media(prefers-color-scheme:dark){:root{--bg:#10131a;--panel:#171b24;--tx:#e6e9f0;--mut:#8b94a7;--ln:#272d3a;--ok:#4cc79b;--bad:#ff7a70;--ac:#8fa6f0}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:15px/1.5 "Avenir Next","Segoe UI",system-ui,sans-serif;padding:20px;max-width:980px;margin-inline:auto}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 8px}.mut{color:var(--mut)}
.wrap{overflow-x:auto;background:var(--panel);border:1px solid var(--ln);border-radius:6px}
table{width:100%;border-collapse:collapse;min-width:640px}td,th{padding:8px 10px;border-bottom:1px solid var(--ln);text-align:right;font-variant-numeric:tabular-nums}
td:first-child,th:first-child{text-align:left}th{color:var(--mut);font-weight:400;font-size:13px}
.ok{color:var(--ok);font-weight:600}.bad{color:var(--bad);font-weight:600}.na{color:var(--mut)}
ul{padding-left:18px}li{margin-bottom:4px}"""

def render(ev, meta):
    pc = lambda x: f"{x * 100:+.1f} %"
    names = list(dict.fromkeys(k[0] for k in ev))
    out = [f"<!doctype html><html lang='fr'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Étude des signaux d'entrée</title><style>{CSS}</style></head><body>",
           "<h1>Étude des signaux d'entrée</h1>",
           f"<p class='mut'>Si j'avais acheté au moment de chaque signal, que serait-il arrivé ensuite ? {html.escape(meta)}</p>",
           "<h2>Comment lire</h2><ul>",
           "<li><b>Écart vs hasard</b> : rendement du signal moins le rendement moyen d'un achat n'importe quel jour de la même action. C'est la seule colonne qui compte : une action qui monte en moyenne rend tous les signaux positifs.</li>",
           "<li><b>Années</b> : nombre d'années distinctes où le signal s'est produit. Peu d'années signifie que tout vient de une ou deux crises (2020, 2022).</li>",
           "<li><b>Biais de survie</b> : ces actions sont celles qui ont réussi jusqu'à aujourd'hui. Acheter les baisses d'entreprises qui se sont redressées paraît donc meilleur qu'en réalité.</li>",
           "<li><b>Tests multiples</b> : avec une trentaine de combinaisons, quelques « indices » apparaissent par pur hasard. Un indice n'est une piste qu'à condition d'être cohérent d'un horizon à l'autre.</li>",
           "<li>Rendements bruts, hors frais et impôts, sans effet de levier.</li></ul>"]
    for h, lab in HORIZONS.items():
        out.append(f"<h2>Horizon {lab}</h2><div class='wrap'><table><tr><th>Signal</th><th>Événements</th><th>Années</th><th>Rendement moyen</th><th>Médian</th><th>% positifs (hasard)</th><th>Écart vs hasard</th><th>Verdict</th></tr>")
        for n in names:
            rows = ev.get((n, h))
            if not rows:
                out.append(f"<tr><td>{html.escape(n)}</td><td colspan='7' class='na'>Aucun événement</td></tr>")
                continue
            s = stats(rows)
            out.append(f"<tr><td>{html.escape(n)}</td><td>{s['n']}</td><td>{s['yrs']}</td><td>{pc(s['mean'])}</td><td>{pc(s['med'])}</td>"
                       f"<td>{s['hit'] * 100:.0f} % ({s['base_hit'] * 100:.0f} %)</td><td>{pc(s['ex'])}</td><td class='{s['verdict'][1]}'>{s['verdict'][0]}</td></tr>")
        out.append("</table></div>")
    out.append("<p class='mut'>Aucune de ces lignes n'est un conseil en investissement.</p></body></html>")
    return "".join(out)

def earnings_dates(t):
    for lim in (100, 40, 12):
        try:
            idx = pd.to_datetime(t.get_earnings_dates(limit=lim).index)
            idx = idx.tz_localize(None) if idx.tz is not None else idx
            today = pd.Timestamp.today().normalize()
            return sorted({d for d in idx.normalize() if d < today})
        except Exception:
            continue
    return []

def main():
    cfg = yaml.safe_load(open(os.path.join(ROOT, "config.yaml"), encoding="utf-8"))
    start = (dt.date.today() - dt.timedelta(days=365 * YEARS_BACK)).isoformat()
    data = {}
    for e in cfg["watchlist"]:
        sym = e["symbol"]
        try:
            t = yf.Ticker(sym)
            c = t.history(start=start, auto_adjust=True)["Close"].dropna()
            c.index = (c.index.tz_localize(None) if c.index.tz is not None else c.index).normalize()
            if len(c) < 500:
                print("historique trop court :", sym)
                continue
            data[sym] = (c, earnings_dates(t))
            print(sym, len(c), "séances,", len(data[sym][1]), "dates de résultats")
        except Exception as ex:
            print("ERREUR", sym, ex)
    if not data:
        sys.exit("Aucune donnée récupérée.")
    meta = f"{len(data)} actions ({', '.join(data)}), {YEARS_BACK} ans d'historique maximum, généré le {dt.date.today().strftime('%d/%m/%Y')}."
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(render(run(data), meta))
    print("Étude écrite dans", OUT)

if __name__ == "__main__":
    main()
