"""Étude v2 : rendement après chaque signal d'entrée, avec filtres de robustesse. Génère docs/etude.html."""
import datetime as dt, html, math, os, sys
import numpy as np, pandas as pd, yaml, yfinance as yf

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "docs", "etude.html")
HORIZONS = {20: "1 mois", 60: "3 mois", 125: "6 mois", 250: "12 mois"}
YEARS_BACK = 15
COVID = (pd.Timestamp("2020-02-15"), pd.Timestamp("2020-06-30"))
INDICES = {"^FCHI": "CAC 40", "^GSPC": "S&P 500"}

def rsi_series(c, n=14):
    d = c.diff()
    up, dn = d.clip(lower=0).rolling(n).mean(), (-d.clip(upper=0)).rolling(n).mean()
    return 100 - 100 / (1 + up / dn)

def cross(s):
    """Premier jour de chaque épisode où la condition est vraie."""
    return s & ~s.shift(1, fill_value=False)

def dedupe(pos, gap):
    """Garde des entrées espacées d'au moins `gap` séances : les rendements ne se chevauchent plus."""
    out, last = [], -10**9
    for i in pos:
        if i - last >= gap:
            out.append(int(i))
            last = i
    return out

def signals(c, earn):
    ma200, hi = c.rolling(200).mean(), c.rolling(252).max()
    dd = c / hi - 1
    pos = lambda s: [int(i) for i in np.flatnonzero(s.to_numpy())]
    sig = {
        "Survente (RSI < 30)": pos(cross(rsi_series(c) < 30)),
        "Repli ≥ 20 % sous le plus haut annuel": pos(cross(dd <= -0.20)),
        "Repli ≥ 30 % sous le plus haut annuel": pos(cross(dd <= -0.30)),
        "Chute ≥ 5 % en une séance": pos(cross(c.pct_change() <= -0.05)),
        "Cassure à la baisse de la MM200": pos((c < ma200) & (c.shift() >= ma200.shift())),
        "Nouveau plus haut annuel": pos(cross(c >= hi)),
    }
    pe = [p for p in (int(c.index.searchsorted(d)) for d in earn) if 6 <= p < len(c) - 1]
    react = {p: c.iloc[p + 1] / c.iloc[p - 1] - 1 for p in pe}
    sig["5 jours avant les résultats"] = [p - 5 for p in pe]
    sig["Après les résultats (toutes publications)"] = [p + 1 for p in pe]
    sig["Après les résultats, réaction ≤ -4 %"] = [p + 1 for p in pe if react[p] <= -0.04]
    sig["Après les résultats, réaction ≥ +4 %"] = [p + 1 for p in pe if react[p] >= 0.04]
    return sig

def run(data):
    """data = {nom: (clôtures, dates de résultats)} -> {(signal, horizon): [événements]}"""
    ev = {}
    for sym, (c, earn) in data.items():
        sg = signals(c, earn)
        for h in HORIZONS:
            fw = c.shift(-h) / c - 1
            fmin = c.iloc[::-1].rolling(h + 1).min().iloc[::-1] / c - 1   # pire niveau atteint pendant l'horizon
            ok = fw.dropna()
            if ok.empty:
                continue
            bm, bh, bmae = ok.mean(), (ok > 0).mean(), fmin.loc[ok.index].median()
            for name, pos in sg.items():
                for i in dedupe(pos, h):
                    r = fw.iloc[i]
                    if pd.notna(r):
                        d = c.index[i]
                        ev.setdefault((name, h), []).append(dict(
                            r=r, ex=r - bm, bh=bh, mae=fmin.iloc[i], bmae=bmae, ym=(d.year, d.month),
                            sym=sym, covid=bool(COVID[0] <= d <= COVID[1])))
    return ev

def stats(rows, no_covid=False):
    rows = [x for x in rows if not (no_covid and x["covid"])]
    if not rows:
        return None
    ex, r = np.array([x["ex"] for x in rows]), np.array([x["r"] for x in rows])
    g, per = {}, {}
    for x in rows:
        g.setdefault(x["ym"], []).append(x["ex"])      # un mois = une observation (les actions chutent ensemble)
        per.setdefault(x["sym"], []).append(x["ex"])
    gm = np.array([np.mean(v) for v in g.values()])
    sd = gm.std(ddof=1) if len(gm) > 2 else 0
    t = gm.mean() / (sd / math.sqrt(len(gm))) if sd > 0 else 0
    per = [np.mean(v) for v in per.values() if len(v) >= 3]
    return dict(n=len(rows), months=len(gm), years=len({k[0] for k in g}), mean=r.mean(), ex=ex.mean(), t=t,
                hit=(r > 0).mean(), bhit=np.mean([x["bh"] for x in rows]), pos=sum(v > 0 for v in per), tot=len(per),
                mae=float(np.median([x["mae"] for x in rows])), bmae=float(np.mean([x["bmae"] for x in rows])))

def verdict(rows):
    s, sc = stats(rows), stats(rows, True)
    if not s or s["months"] < 15 or s["years"] < 5:
        return "Trop peu de données", "na"
    if s["ex"] < 0 and s["t"] < -2:
        return "Défavorable", "bad"
    if s["ex"] > 0 and s["t"] > 2:
        solid = sc and sc["ex"] > 0 and sc["t"] > 1.5 and s["tot"] and s["pos"] / s["tot"] >= 0.6
        return ("Indice solide", "ok") if solid else ("Fragile", "warn")
    return "Pas d'avantage net", "na"

CSS = """:root{--bg:#f3f4f7;--panel:#fff;--tx:#121826;--mut:#667085;--ln:#dde1e8;--ok:#0f7b57;--bad:#c23b32;--wa:#a86a00}
@media(prefers-color-scheme:dark){:root{--bg:#10131a;--panel:#171b24;--tx:#e6e9f0;--mut:#8b94a7;--ln:#272d3a;--ok:#4cc79b;--bad:#ff7a70;--wa:#e8b04a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:15px/1.5 "Avenir Next","Segoe UI",system-ui,sans-serif;padding:20px;max-width:1040px;margin-inline:auto}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 8px}.mut{color:var(--mut)}
.wrap{overflow-x:auto;background:var(--panel);border:1px solid var(--ln);border-radius:6px}
table{width:100%;border-collapse:collapse;min-width:820px}td,th{padding:8px 10px;border-bottom:1px solid var(--ln);text-align:right;font-variant-numeric:tabular-nums}
td:first-child,th:first-child{text-align:left}th{color:var(--mut);font-weight:400;font-size:13px}
.ok{color:var(--ok);font-weight:600}.bad{color:var(--bad);font-weight:600}.warn{color:var(--wa);font-weight:600}.na{color:var(--mut)}
.box{background:var(--panel);border:1px solid var(--ln);border-radius:6px;padding:12px 16px;margin:14px 0}
details{margin-top:10px}summary{cursor:pointer;color:var(--mut)}ul{padding-left:18px}li{margin-bottom:4px}"""

def table(ev, names, h):
    pc = lambda x: f"{x * 100:+.1f} %"
    out = ["<div class='wrap'><table><tr><th>Signal</th><th>Entrées</th><th>Rendement moyen</th><th>Écart vs hasard</th><th>Écart hors Covid</th>"
           "<th>Titres &gt; 0</th><th>% positifs (hasard)</th><th>Pire baisse médiane (hasard)</th><th>Verdict</th></tr>"]
    for n in names:
        rows = ev.get((n, h))
        if not rows:
            out.append(f"<tr><td>{html.escape(n)}</td><td colspan='8' class='na'>Aucun événement</td></tr>")
            continue
        s, sc = stats(rows), stats(rows, True)
        v = verdict(rows)
        out.append(f"<tr><td>{html.escape(n)}</td><td>{s['n']}</td><td>{pc(s['mean'])}</td><td>{pc(s['ex'])}</td>"
                   f"<td>{pc(sc['ex']) if sc else '–'}</td><td>{s['pos']}/{s['tot']}</td>"
                   f"<td>{s['hit'] * 100:.0f} % ({s['bhit'] * 100:.0f} %)</td><td>{pc(s['mae'])} ({pc(s['bmae'])})</td>"
                   f"<td class='{v[1]}'>{v[0]}</td></tr>")
    out.append("</table></div>")
    return "".join(out)

def render(ev, ev_idx, meta):
    names = list(dict.fromkeys(k[0] for k in ev))
    idx_names = [n for n in names if "résultats" not in n]
    solid = {}
    for (n, h), rows in ev.items():
        if verdict(rows)[1] == "ok":
            solid.setdefault(n, []).append(HORIZONS[h])
    if solid:
        li = "".join(f"<li><b>{html.escape(n)}</b> : {', '.join(hs)}"
                     f"{' (cohérent sur plusieurs horizons)' if len(hs) > 1 else ' (un seul horizon : prudence)'}</li>" for n, hs in solid.items())
        brief = f"<p>Signaux qui passent tous les filtres :</p><ul>{li}</ul>"
    else:
        brief = "<p><b>Aucun signal ne passe tous les filtres.</b> Il n'y a pas d'avantage assez solide pour bâtir une règle d'entrée.</p>"
    out = [f"<!doctype html><html lang='fr'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Étude des signaux d'entrée v2</title><style>{CSS}</style></head><body>",
           "<h1>Étude des signaux d'entrée (v2)</h1>", f"<p class='mut'>{html.escape(meta)}</p>",
           f"<div class='box'><b>En bref</b>{brief}</div>",
           "<h2>Ce que la v2 corrige</h2><ul>",
           "<li><b>Entrées non chevauchantes</b> : deux entrées d'une même action sont espacées d'au moins la durée de l'horizon, donc on ne compte plus 20 fois le même épisode.</li>",
           "<li><b>Un mois = une observation</b> pour le test statistique, car tes actions chutent et rebondissent ensemble.</li>",
           "<li><b>Écart hors Covid</b> : même calcul sans les entrées du 15/02/2020 au 30/06/2020.</li>",
           "<li><b>Titres &gt; 0</b> : nombre d'actions pour lesquelles le signal bat le hasard (au moins 3 entrées chacune).</li>",
           "<li><b>Pire baisse médiane</b> : niveau le plus bas atteint après l'entrée pendant l'horizon, comparé à une entrée un jour quelconque.</li>",
           "<li><b>Verdict « Indice solide »</b> : test positif, toujours positif hors Covid, et au moins 60 % des titres en avance. « Fragile » : test positif mais l'un de ces filtres échoue.</li></ul>",
           "<p class='mut'>Limites qui restent : biais de survie (tes actions sont celles qui ont réussi), tests multiples (une trentaine de combinaisons, quelques succès par hasard), rendements bruts hors frais et impôts. Rien ici n'est un conseil en investissement.</p>"]
    for h, lab in HORIZONS.items():
        out.append(f"<h2>Horizon {lab}</h2>{table(ev, names, h)}")
        if ev_idx:
            out.append(f"<details><summary>Contrôle sur indices ({', '.join(INDICES.values())})</summary>{table(ev_idx, idx_names, h)}</details>")
    out.append("</body></html>")
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

def load(sym, start):
    t = yf.Ticker(sym)
    c = t.history(start=start, auto_adjust=True)["Close"].dropna()
    c.index = (c.index.tz_localize(None) if c.index.tz is not None else c.index).normalize()
    return t, c

def main():
    cfg = yaml.safe_load(open(os.path.join(ROOT, "config.yaml"), encoding="utf-8"))
    start = (dt.date.today() - dt.timedelta(days=365 * YEARS_BACK)).isoformat()
    data, idx = {}, {}
    for e in cfg["watchlist"]:
        try:
            t, c = load(e["symbol"], start)
            if len(c) < 500:
                print("historique trop court :", e["symbol"])
                continue
            data[e["symbol"]] = (c, earnings_dates(t))
            print(e["symbol"], len(c), "séances,", len(data[e["symbol"]][1]), "dates de résultats")
        except Exception as ex:
            print("ERREUR", e["symbol"], ex)
    for sym, name in INDICES.items():
        try:
            _, c = load(sym, start)
            if len(c) >= 500:
                idx[name] = (c, [])
        except Exception as ex:
            print("ERREUR indice", sym, ex)
    if not data:
        sys.exit("Aucune donnée récupérée.")
    meta = f"{len(data)} actions ({', '.join(data)}), {YEARS_BACK} ans d'historique maximum, généré le {dt.date.today().strftime('%d/%m/%Y')}."
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(render(run(data), run(idx) if idx else {}, meta))
    print("Étude écrite dans", OUT)

if __name__ == "__main__":
    main()
