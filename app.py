import os, io, re, random, sqlite3
from datetime import datetime, date, timedelta, timezone
from flask import Flask, request, render_template, redirect, jsonify
from jinja2 import DictLoader
from werkzeug.exceptions import BadRequest
from PIL import Image
import pytesseract
from core import analyse

WIN = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(WIN): pytesseract.pytesseract.tesseract_cmd = WIN

IST = timezone(timedelta(hours=5, minutes=30))
def today(): return datetime.now(IST).date()
SLOTS = [("Morning", "8:00", 8), ("Afternoon", "14:00", 14), ("Night", "21:00", 21)]
SAMPLE = "Tab Dolo 650 1-0-1 x 5 days\nTab Azitral 500 OD x 3 days\nTab Pan 40 1-0-0 x 14 days\nTab Brufen 400 1-0-1 x 5 days\nTab Voveran 50 BD x 5 days\nTab Thyronorm 50 mcg 1-0-0 x 30 days"

# Keep only lines that look like medicines (skips clinic name, doctor, patient and date lines read by OCR)
MED = re.compile(r"^\s*(tab|tablet|cap|capsule|syp|syrup|inj)\b|\b[01]\s*-\s*[01]\s*-\s*[01]\b|\b(od|bd|bid|tds|tid|qid)\b|\d\s*(days?|weeks?|wks?)\b", re.I)
def medicine_lines(text):
    keep = [l for l in text.splitlines() if l.strip() and MED.search(l)]
    return "\n".join(keep) if keep else text

# ---------------- database (stores medicine names, costs and dose logs only; never images or personal details) ----------------
DB = os.environ.get("PP_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "pillpilot.db"))
try:
    open(DB, "a").close()
except OSError:
    DB = "/tmp/pillpilot.db"
def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c
with db() as _c:
    _c.executescript("""
    CREATE TABLE IF NOT EXISTS rx(id INTEGER PRIMARY KEY, created TEXT, prescribed REAL, cheapest REAL, n_exact INT, n_confirm INT, n_unrec INT, n_alerts INT);
    CREATE TABLE IF NOT EXISTS med(id INTEGER PRIMARY KEY, rx_id INT, brand TEXT, salt TEXT, qty INT, f0 INT, f1 INT, f2 INT, days INT, cheap_brand TEXT, cheap_price REAL, start TEXT, active INT DEFAULT 1);
    CREATE TABLE IF NOT EXISTS dose(med_id INT, day TEXT, slot INT, status TEXT, PRIMARY KEY(med_id, day, slot));
    CREATE TABLE IF NOT EXISTS alert(rx_id INT, kind TEXT, msg TEXT);""")

def save_rx(res, day=None):
    ok = [i for i in res["items"] if i["row"]]
    if not ok: return None
    day = day or today(); n_exact = sum(1 for i in ok if not i["dist"])
    with db() as c:
        c.execute("UPDATE med SET active=0")
        rid = c.execute("INSERT INTO rx(created,prescribed,cheapest,n_exact,n_confirm,n_unrec,n_alerts) VALUES(?,?,?,?,?,?,?)",
                        (day.isoformat(), res["prescribed"], res["cheapest"], n_exact, len(ok) - n_exact, len(res["items"]) - len(ok), len(res["alerts"]))).lastrowid
        for i in ok:
            f = i["parse"]["freq"]; a = i["alts"][0]
            c.execute("INSERT INTO med(rx_id,brand,salt,qty,f0,f1,f2,days,cheap_brand,cheap_price,start,active) VALUES(?,?,?,?,?,?,?,?,?,?,?,1)",
                      (rid, i["row"]["brand"], i["row"]["salt"], i["qty"], f[0], f[1], f[2], i["parse"]["days"], a["brand"], a["price"], day.isoformat()))
        for k, m in res["alerts"]: c.execute("INSERT INTO alert VALUES(?,?,?)", (rid, k, m))
    return rid

def load_all():
    with db() as c:
        meds = c.execute("SELECT * FROM med").fetchall()
        dmap = {(d["med_id"], d["day"], d["slot"]): d["status"] for d in c.execute("SELECT * FROM dose")}
    return meds, dmap
def span(m):
    st = date.fromisoformat(m["start"]); return st, st + timedelta(days=m["days"] - 1)
def day_stats(meds, dmap, d):
    s = t = 0
    for m in meds:
        st, en = span(m)
        if st <= d <= en:
            for k in range(3):
                if m["f%d" % k]:
                    stt = dmap.get((m["id"], d.isoformat(), k))
                    if d == today() and stt is None: continue  # today's doses not yet logged do not count against you
                    s += 1; t += stt == "taken"
    return s, t
def adherence(meds, dmap, n):
    td = today(); return [(td - timedelta(days=k), *day_stats(meds, dmap, td - timedelta(days=k))) for k in range(n - 1, -1, -1)]
def streak_of(days):
    td, st = today(), 0
    for d, s, t in reversed(days):
        if s == 0: continue
        if t / s >= .8: st += 1
        elif d == td: continue
        else: break
    return st

# ---------------- tiny SVG charts (no external libraries) ----------------
def svg_grouped(rows):
    if not rows: return ""
    W, H = 640, 230; mx = max(max(a, b) for _, a, b in rows) or 1; n = len(rows); gw = (W - 20) / n; bw = min(34, gw * .34)
    s = '<svg viewBox="0 0 %d %d" class="chart" role="img" aria-label="Prescribed against cheapest course cost for each prescription">' % (W, H)
    for i, (l, a, b) in enumerate(rows):
        x = 10 + i * gw + gw / 2; ha = (H - 60) * a / mx; hb = (H - 60) * b / mx
        s += '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="4" class="b1"/><rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="4" class="b2"/>' % (x - bw - 2, H - 30 - ha, bw, ha, x + 2, H - 30 - hb, bw, hb)
        s += '<text x="%.1f" y="%.1f" text-anchor="middle">₹%d</text><text x="%.1f" y="%.1f" text-anchor="middle">%s</text>' % (x + 2 + bw / 2, H - 34 - hb, round(b), x, H - 10, l)
    return s + "</svg>"
def svg_adh(days):
    W, H = 640, 200; n = len(days); gw = (W - 20) / n; s = '<svg viewBox="0 0 %d %d" class="chart" role="img" aria-label="Daily adherence">' % (W, H)
    for i, (d, sc, t) in enumerate(days):
        pct = t / sc * 100 if sc else 0; h = (H - 55) * pct / 100; x = 10 + i * gw + gw * .15
        s += '<rect x="%.1f" y="25" width="%.1f" height="%d" rx="4" class="bg"/>' % (x, gw * .7, H - 55)
        if sc: s += '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="4" class="b2"/>' % (x, H - 30 - h, gw * .7, h)
        s += '<text x="%.1f" y="%d" text-anchor="middle">%s</text><text x="%.1f" y="16" text-anchor="middle">%s</text>' % (x + gw * .35, H - 10, d.strftime("%d/%m"), x + gw * .35, ("%d%%" % pct) if sc else "-")
    return s + "</svg>"

# ---------------- demo data so the dashboard is never empty ----------------
DEMO = [(12, "Tab Dolo 650 1-0-1 x 5 days\nTab Cetzine 10 1-0-0 x 5 days"), (8, "Tab Azithral 500 OD x 3 days\nTab Pan 40 1-0-0 x 7 days"),
        (5, "Tab Brufen 400 1-0-1 x 5 days\nTab Voveran 50 BD x 5 days"), (2, SAMPLE)]
def clear():
    with db() as c: c.executescript("DELETE FROM rx; DELETE FROM med; DELETE FROM dose; DELETE FROM alert;")
def seed():
    clear(); rnd = random.Random(3); td = today()
    for ago, text in DEMO:
        day = td - timedelta(days=ago); save_rx(analyse(text), day)
    meds, _ = load_all()
    with db() as c:
        for m in meds:
            st, en = span(m); d = st
            while d <= min(en, td - timedelta(days=1)):
                for k in range(3):
                    if m["f%d" % k]: c.execute("INSERT OR REPLACE INTO dose VALUES(?,?,?,?)", (m["id"], d.isoformat(), k, "taken" if rnd.random() < .86 else "skipped"))
                d += timedelta(days=1)

# ---------------- templates ----------------
CSS = """:root{--bg:#f1f5f9;--card:#fff;--ink:#0f1b33;--mute:#5a6a82;--line:#dbe3ec;--teal:#0f766e;--tealbg:#d5f0eb;--amb:#8a5200;--ambbg:#fdeccd;--red:#b42318;--redbg:#fde4e1;--h1:#0f766e;--h2:#115e8a}
@media (prefers-color-scheme:dark){:root{--bg:#0b1220;--card:#141e30;--ink:#e8eef7;--mute:#9aabc2;--line:#28384e;--teal:#4fd1c0;--tealbg:#123a39;--amb:#f3c26b;--ambbg:#3a2c10;--red:#ff9b8f;--redbg:#3d1a17;--h1:#0b4f4a;--h2:#0c3f5e}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:0 16px}.hero{background:linear-gradient(120deg,var(--h1),var(--h2));color:#fff;padding:18px 0 74px}.hero .wrap{padding:0 16px}
.top{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px}.brand{display:flex;align-items:center;gap:10px;font-weight:800;font-size:1.4rem}
.logo{width:32px;height:17px;border-radius:9px;background:linear-gradient(90deg,#fff 50%,#9be7dc 50%);transform:rotate(-30deg)}
nav{display:flex;gap:6px;background:rgba(255,255,255,.14);border-radius:999px;padding:4px}nav a{color:#fff;text-decoration:none;padding:6px 16px;border-radius:999px;font-weight:600;font-size:.95rem}nav a.on{background:#fff;color:#0f766e}
.hero h1{margin:20px 0 2px;font-size:1.9rem}.hero p{margin:0;opacity:.92;max-width:60ch}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px;margin-bottom:14px;box-shadow:0 1px 2px rgba(15,27,51,.05)}.pull{margin-top:-52px}
h2{font-size:1.15rem;margin:26px 0 10px}h3{margin:0 0 8px;font-size:1.02rem}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(170px,1fr))}.stat{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}.stat b{display:block;font-size:1.8rem;font-weight:800;line-height:1.1}.stat span{color:var(--mute);font-size:.84rem}.stat.win{background:var(--tealbg);border-color:var(--teal)}.stat.win b{color:var(--teal)}
.two{display:grid;gap:14px;grid-template-columns:1fr 1fr}@media(max-width:760px){.two{grid-template-columns:1fr}}
.btn{background:var(--teal);color:var(--card);border:0;border-radius:12px;padding:10px 16px;font:inherit;font-weight:700;cursor:pointer;text-decoration:none;display:inline-block}.btn.alt{background:transparent;color:var(--teal);border:1px solid var(--teal)}.btn.sm{padding:6px 12px;font-size:.88rem;border-radius:10px}
.note{font-size:.84rem;color:var(--amb);background:var(--ambbg);border-radius:10px;padding:8px 12px;margin:10px 0}
.badge{font-size:.76rem;border-radius:999px;padding:2px 10px;background:var(--tealbg);color:var(--teal);font-weight:600}.badge.warn{background:var(--ambbg);color:var(--amb)}.badge.bad{background:var(--redbg);color:var(--red)}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}.chip{font-size:.8rem;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:2px 9px;color:var(--mute)}.mute{color:var(--mute);font-size:.88rem}
.drop{display:block;border:2px dashed var(--line);border-radius:14px;padding:26px 14px;text-align:center;cursor:pointer}.drop:hover,.drop.over{border-color:var(--teal);background:var(--tealbg)}.drop input{display:none}#prev{max-height:130px;border-radius:8px;margin-top:10px;display:none}
textarea{width:100%;min-height:120px;border:1px solid var(--line);border-radius:12px;padding:10px;background:var(--bg);color:var(--ink);font:14px/1.5 ui-monospace,Menlo,Consolas,monospace}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:420px;font-size:.92rem}th{font-size:.76rem;text-transform:uppercase;letter-spacing:.04em;color:var(--mute)}th,td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left}tr.best td{background:var(--tealbg);font-weight:600}
.alert{border-radius:12px;padding:10px 14px;margin-bottom:8px;font-size:.93rem}.alert.warn{background:var(--ambbg);color:var(--amb)}.alert.danger{background:var(--redbg);color:var(--red)}.alert.ok{background:var(--tealbg);color:var(--teal)}
.chart{width:100%;height:auto}.chart text{fill:var(--mute);font-size:11px}.b1{fill:var(--amb);opacity:.75}.b2{fill:var(--teal)}.bg{fill:var(--line);opacity:.5}
.legend{display:flex;gap:14px;font-size:.82rem;color:var(--mute);margin-top:4px}.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px}
.hb{margin:8px 0}.hb div{height:10px;border-radius:6px;background:var(--teal)}.hb span{font-size:.88rem}
.ringwrap{display:flex;align-items:center;gap:18px;flex-wrap:wrap}.ring{width:120px;height:120px}.ring circle{fill:none;stroke-width:11}.ring .t{stroke:var(--line)}.ring .p{stroke:var(--teal);stroke-linecap:round;transform:rotate(-90deg);transform-origin:50% 50%}.ring text{fill:var(--ink);font-weight:800;font-size:26px}
.week{display:flex;gap:8px;flex-wrap:wrap}.day{width:52px;text-align:center;border-radius:12px;padding:6px 0;background:var(--bg);border:1px solid var(--line);font-size:.78rem;color:var(--mute)}.day b{display:block;font-size:.95rem;color:var(--ink)}.day.full{background:var(--tealbg);border-color:var(--teal)}.day.part{background:var(--ambbg)}.day.none{opacity:.5}
.dose{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;padding:10px 0;border-bottom:1px solid var(--line)}.dose:last-child{border-bottom:0}
.dose.taken .nm{text-decoration:line-through;opacity:.6}.dose.skipped .nm{color:var(--red)}.act{display:flex;gap:6px}.act button{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:10px;padding:6px 14px;font:inherit;font-size:.88rem;cursor:pointer}
.dose.taken .act .tk{background:var(--teal);color:var(--card);border-color:var(--teal)}.dose.skipped .act .sk{background:var(--red);color:var(--card);border-color:var(--red)}
.bar{height:10px;border-radius:6px;background:var(--line);overflow:hidden}.bar div{height:100%;background:var(--teal)}
:focus-visible{outline:3px solid var(--teal);outline-offset:2px}footer{color:var(--mute);font-size:.8rem;text-align:center;padding:26px 16px 40px}
/* ===== Pastel Capsule theme ===== */
:root{--bg:#faf8ff;--card:#fff;--ink:#2a2540;--mute:#6b6585;--line:#e6e0f5;--teal:#4f3fb0;--tealbg:#ece6ff;--amb:#6b4e00;--ambbg:#fff2b3;--red:#a3203a;--redbg:#ffd9de;--mint:#bff0dc;--mintink:#14634a;--butter:#f5c842;--h1:#c9b8ff;--h2:#bff0dc;--heroink:#2a2540}
@media (prefers-color-scheme:dark){:root{--bg:#1a1630;--card:#252040;--ink:#efeaff;--mute:#a9a2c9;--line:#3a3360;--teal:#c9b8ff;--tealbg:#372f66;--amb:#ffe58a;--ambbg:#4a4018;--red:#ff9fb0;--redbg:#4a1f2c;--mint:#1f4a40;--mintink:#bff0dc;--h1:#40307a;--h2:#1f4a40;--heroink:#efeaff}}
body{font-family:"Nunito",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
h1,h2,h3,.brand,.stat b{font-weight:800}
.hero{color:var(--heroink)}.hero p{opacity:1}
.logo{width:36px;height:17px;border-radius:999px;background:linear-gradient(90deg,var(--teal) 50%,var(--card) 50%);box-shadow:inset 0 0 0 2px var(--ink);transform:rotate(-30deg)}
nav{background:rgba(255,255,255,.55)}nav a{color:var(--heroink)}nav a.on{background:var(--ink);color:var(--card)}
@media (prefers-color-scheme:dark){nav{background:rgba(255,255,255,.12)}nav a.on{background:var(--teal);color:#1a1630}}
.card{border-radius:24px;box-shadow:0 6px 20px rgba(79,63,176,.08)}.stat{border-radius:22px}.alert{border-radius:18px}.note{border-radius:16px}
textarea{border-radius:20px}.drop{border-radius:24px;border-color:var(--teal)}.drop:hover,.drop.over{background:var(--tealbg)}.drop b{display:block;margin-bottom:4px}
.btn{border-radius:999px;padding:11px 22px}.btn.sm{padding:7px 16px}
.chip{border-radius:999px;background:var(--tealbg);border-color:transparent;color:var(--ink)}
.badge{background:var(--mint);color:var(--mintink)}.badge.warn{background:var(--ambbg);color:var(--amb)}.badge.bad{background:var(--redbg);color:var(--red)}
.stat.win,.day.full{background:var(--mint);border-color:transparent}.stat.win b,.stat.win span,.day.full{color:var(--mintink)}
.alert.ok{background:var(--mint);color:var(--mintink)}
tr.best td{background:var(--mint);color:var(--mintink)}
th{text-transform:none;letter-spacing:0;font-size:.82rem}
.b1{fill:var(--butter);opacity:1}.b2{fill:var(--teal)}.bar,.bar div,.hb div,.bg{border-radius:999px}
/* ===== Pill-pop tracker ===== */
.dose{border-bottom:0;padding:5px 0;flex-wrap:nowrap}
.pill{flex:1;min-width:0;display:flex;align-items:center;gap:14px;text-align:left;border:2px solid var(--line);background:var(--card);color:var(--ink);border-radius:999px;padding:9px 18px 9px 12px;font:inherit;cursor:pointer;transition:background .25s,border-color .25s,transform .1s}
.pill:active{transform:scale(.97)}
.cap{flex:none;position:relative;width:48px;height:22px;transform:rotate(-25deg);transition:transform .35s}
.cap::before,.cap::after{content:"";position:absolute;top:0;width:50%;height:100%;box-shadow:inset 0 0 0 2px var(--ink);transition:transform .35s}
.cap::before{left:0;border-radius:999px 0 0 999px;background:var(--teal)}.cap::after{right:0;border-radius:0 999px 999px 0;background:var(--butter)}
.pill .nm{display:block;line-height:1.25}.pill .nm small{display:block;color:var(--mute);font-size:.8rem;font-weight:600}
.pill .st{margin-left:auto;font-size:.82rem;font-weight:700;color:var(--mute);white-space:nowrap}
.dose.taken .nm{text-decoration:none;opacity:1}
.dose.taken .pill{background:var(--mint);border-color:var(--mintink);color:var(--mintink)}.dose.taken .pill .st,.dose.taken .pill small{color:var(--mintink)}
.dose.taken .cap{transform:rotate(0)}.dose.taken .cap::before{transform:translateX(-7px) rotate(-14deg)}.dose.taken .cap::after{transform:translateX(7px) rotate(14deg)}
.dose.skipped .pill{background:var(--redbg);border-color:var(--red);color:var(--red)}.dose.skipped .nm{color:var(--red)}.dose.skipped .pill .st,.dose.skipped .pill small{color:var(--red)}.dose.skipped .cap{opacity:.45}
.dose.pop .pill{animation:pop .45s}
@keyframes pop{0%{transform:scale(1)}35%{transform:scale(1.07)}100%{transform:scale(1)}}
.skip{flex:none;border:0;background:none;color:var(--mute);font:inherit;font-size:.85rem;text-decoration:underline;cursor:pointer;padding:10px 6px}.skip[aria-pressed=true]{color:var(--red);font-weight:700}
.toast{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);background:var(--ink);color:var(--card);border-radius:999px;padding:10px 20px;font-size:.9rem;z-index:9}
.fx{position:fixed;width:22px;height:10px;border-radius:999px;pointer-events:none;z-index:9}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""
BASE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&display=swap" rel="stylesheet"><title>PillPilot</title><style>""" + CSS + """</style></head><body>
<header class="hero"><div class="wrap"><div class="top"><div class="brand"><span class="logo"></span>PillPilot</div>
<nav>{% for h,l in [("/","Analyse"),("/tracker","Tracker"),("/dashboard","Dashboard")] %}<a href="{{ h }}" class="{{ 'on' if request.path==h }}">{{ l }}</a>{% endfor %}</nav></div>
{% block hero %}{% endblock %}</div></header><main class="wrap">{% block content %}{% endblock %}</main>
<footer>PillPilot · decision support only · does not sell or dispense medicines · stores only medicine names, costs and dose logs</footer>{% block script %}{% endblock %}</body></html>"""
HOME = """{% extends "base.html" %}{% block hero %}<h1>Dose it right, from price to pill.</h1><p>Your prescription, made simple. See cheaper options, spot anything risky and tap through your doses as you go.</p>{% endblock %}
{% block content %}
<form class="card pull" method="post" enctype="multipart/form-data" id="f">
<label class="drop" id="drop"><input type="file" name="image" id="file" accept="image/*"><b>Drop a prescription image here, or click to choose</b><span class="mute">PNG or JPG, printed or typed prescriptions only</span><br><img id="prev" alt="Preview of the chosen prescription"></label>
<p class="mute" style="text-align:center;margin:12px 0">or paste the text, one medicine per line</p>
<textarea name="text" aria-label="Prescription text">{{ text }}</textarea>
<label class="mute" style="display:block;margin:10px 0"><input type="checkbox" name="save" checked> Send to my tracker and dashboard</label>
<button class="btn" id="btn" style="width:100%">Analyse prescription</button>
<div class="note">Demo data: prices and interactions are illustrative samples, not medical advice. Confirm every change with your doctor or pharmacist.</div></form>
{% if err %}<div class="alert danger">{{ err }}</div>{% endif %}
{% if r %}{% if saved %}<div class="alert ok">Saved. <a href="/tracker">Open your medicine tracker</a> or see the <a href="/dashboard">dashboard</a>.</div>{% endif %}
{% if ocr %}<div class="card"><b>Text read from the image</b><pre style="white-space:pre-wrap;margin:6px 0 0">{{ ocr }}</pre></div>{% endif %}
{% if r.found %}<h2>Course cost</h2><div class="grid"><div class="stat"><b>₹{{ '%.0f'|format(r.prescribed) }}</b><span>As prescribed</span></div><div class="stat win"><b>₹{{ '%.0f'|format(r.cheapest) }}</b><span>Cheapest valid combination</span></div>
<div class="stat"><b>₹{{ '%.0f'|format(r.prescribed-r.cheapest) }}</b><span>Possible saving{% if r.prescribed %} ({{ '%.0f'|format((r.prescribed-r.cheapest)/r.prescribed*100) }}%){% endif %}</span></div></div>
{% endif %}<h2>Medicines</h2>
{% for i in r['items'] %}<div class="card">{% if not i.row %}<b>{{ i.line }}</b> <span class="badge bad">Not recognised</span><p class="mute">No close match in the dataset. Check the spelling or ask your pharmacist.</p>
{% else %}<b style="font-size:1.1rem">{{ i.row.brand }}</b> {% if i.dist %}<span class="badge warn">Please confirm (edit distance {{ i.dist }})</span>{% else %}<span class="badge">Exact match</span>{% endif %}
<div class="chips"><span class="chip">{{ i.row.salt }}</span><span class="chip">{{ i.row.strength }}</span><span class="chip">{{ i.row.form }}</span><span class="chip">{{ i.qty }} units</span><span class="chip">{{ i.parse.freq|join('-') }} for {{ i.parse.days }} days</span>{% if i.parse.assumed %}<span class="chip">days missing, 5 assumed</span>{% endif %}<span class="chip">{{ i.sched|join(' · ') }}</span></div>
<p class="mute">Why these match: same salt, same strength and same form as the prescribed medicine.</p>
<div class="scroll"><table><tr><th>Option</th><th>Type</th><th>Per unit</th><th>Course</th></tr>{% for a in i.alts %}<tr class="{{ 'best' if loop.first }}"><td>{{ a.brand }}{% if loop.first %} · cheapest{% endif %}</td><td>{{ a.type }}</td><td>₹{{ a.price }}</td><td>₹{{ '%.0f'|format(a.price*i.qty) }}</td></tr>{% endfor %}</table></div>{% endif %}</div>{% endfor %}
<h2>Safety checks</h2>{% for c,t in r.alerts %}<div class="alert {{ c }}">{{ t }}</div>{% else %}{% if r.found %}<div class="alert ok">No duplicate salts or known interactions found in the sample list.</div>{% else %}<div class="alert warn">No medicines were recognised, so no safety checks were run. Check the spelling or paste the text again.</div>{% endif %}{% endfor %}{% endif %}{% endblock %}
{% block script %}<script>
const drop=document.getElementById("drop"),file=document.getElementById("file"),prev=document.getElementById("prev");
function show(){const f=file.files[0];if(!f)return;prev.src=URL.createObjectURL(f);prev.style.display="inline-block";drop.querySelector("b").textContent=f.name}
file.addEventListener("change",show);["dragenter","dragover"].forEach(e=>drop.addEventListener(e,v=>{v.preventDefault();drop.classList.add("over")}));
["dragleave","drop"].forEach(e=>drop.addEventListener(e,v=>{v.preventDefault();drop.classList.remove("over")}));
drop.addEventListener("drop",v=>{if(v.dataTransfer.files.length){file.files=v.dataTransfer.files;show()}});
document.getElementById("f").addEventListener("submit",()=>{const b=document.getElementById("btn");b.disabled=true;b.textContent="Reading prescription..."});
</script>{% endblock %}"""
TRACKER = """{% extends "base.html" %}{% block hero %}<h1>Medicine tracker</h1><p>{{ today.strftime('%A, %d %B %Y') }} · mark each dose as taken or skipped.</p>{% endblock %}
{% block content %}
{% if not active %}<div class="card pull"><h3>No active medicines</h3><p class="mute">{% if done %}Your last course has finished.{% else %}Analyse a prescription and choose “Send to my tracker”, or load demo data.{% endif %}</p>
<a class="btn" href="/">Analyse a prescription</a> <form method="post" action="/demo" style="display:inline"><button class="btn alt">Load demo data</button></form></div>
{% else %}
<div class="card pull"><div class="ringwrap"><svg class="ring" viewBox="0 0 120 120" role="img" aria-label="{{ tk }} of {{ tot }} doses taken today"><circle class="t" cx="60" cy="60" r="52"/><circle class="p" cx="60" cy="60" r="52" stroke-dasharray="326.7" stroke-dashoffset="{{ 326.7*(1-(tk/tot if tot else 0)) }}"/><text x="60" y="68" text-anchor="middle">{{ tk }}/{{ tot }}</text></svg>
<div><h3>Today’s doses</h3><p class="mute" style="margin:0">{{ tk }} taken · {{ sk }} skipped · {{ tot-tk-sk }} pending</p></div>
<div class="grid" style="flex:1;min-width:240px"><div class="stat"><b>{{ streak }}</b><span>Day streak (80%+ taken)</span></div><div class="stat"><b>{{ week_pct }}%</b><span>Last 7 days adherence</span></div></div></div></div>
<h2>This week</h2><div class="week">{% for d,s,t in week %}<div class="day {{ 'none' if s==0 else 'full' if t==s else 'part' }}">{{ d.strftime('%a') }}<b>{{ d.day }}</b>{% if s %}{{ t }}/{{ s }}{% else %}-{% endif %}</div>{% endfor %}</div>
<h2>Today’s schedule</h2>
{% for sl in slots %}{% if sl['items'] %}<div class="card" data-hour="{{ sl.hour }}"><h3>{{ sl.name }} · {{ sl.time }} <span class="badge slot-state"></span></h3>
{% for it in sl['items'] %}<div class="dose {{ it.status }}" data-med="{{ it.m.id }}" data-slot="{{ sl.k }}"><button class="pill" data-act="taken" aria-pressed="{{ 'true' if it.status=='taken' else 'false' }}"><span class="cap" aria-hidden="true"></span><span class="nm"><b>{{ it.m.brand }}</b><small>{{ it.m.salt }}</small></span><span class="st">{{ 'Taken' if it.status=='taken' else 'Skipped' if it.status=='skipped' else 'Tap to take' }}</span></button><button class="skip" data-act="skipped" aria-pressed="{{ 'true' if it.status=='skipped' else 'false' }}">Skip</button></div>{% endfor %}</div>{% endif %}{% endfor %}
<h2>Course progress</h2>
{% for a in active %}<div class="card"><div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap"><b>{{ a.m.brand }}</b><span class="mute">{{ a.left }} of {{ a.m.qty }} units left · {{ a.days_left }} day{{ '' if a.days_left==1 else 's' }} left</span></div>
<div class="bar" style="margin:8px 0"><div style="width:{{ a.pct }}%"></div></div>
{% if a.left <= a.per*2 %}<div class="alert warn" style="margin:0">Refill soon. Cheapest valid option: {{ a.m.cheap_brand }} at ₹{{ a.m.cheap_price }} per unit.</div>{% endif %}</div>{% endfor %}
{% endif %}
{% if done %}<h2>Finished courses</h2><div class="card">{% for a in done %}<span class="chip">{{ a.m.brand }} · ended {{ a.end.strftime('%d %b') }}</span> {% endfor %}</div>{% endif %}
{% endblock %}
{% block script %}<script>
const ring=document.querySelector(".ring .p"),rt=document.querySelector(".ring text"),sum=document.querySelector(".ringwrap p"),reduce=matchMedia("(prefers-reduced-motion:reduce)").matches;
const rows=()=>[...document.querySelectorAll(".dose")];
const state=r=>r.classList.contains("taken")?"taken":r.classList.contains("skipped")?"skipped":"pending";
const label={taken:"Taken",skipped:"Skipped",pending:"Tap to take"};
function badges(){const h={{ hour }};document.querySelectorAll("[data-hour]").forEach(c=>{const hr=+c.dataset.hour,pend=c.querySelectorAll(".dose:not(.taken):not(.skipped)").length,b=c.querySelector(".slot-state");
 if(!pend){b.textContent="Done";b.className="badge slot-state";return}if(h>=hr+2){b.textContent="Overdue";b.className="badge bad slot-state"}else if(h>=hr){b.textContent="Due now";b.className="badge warn slot-state"}else{b.textContent="Upcoming";b.className="badge slot-state"}})}
function refresh(){const R=rows(),tk=R.filter(r=>state(r)=="taken").length,sk=R.filter(r=>state(r)=="skipped").length,t=R.length;
 if(ring){ring.style.strokeDashoffset=326.7*(1-(t?tk/t:0));rt.textContent=tk+"/"+t;sum.textContent=tk+" taken · "+sk+" skipped · "+(t-tk-sk)+" pending"}
 R.forEach(r=>{const s=state(r);r.querySelector(".pill").setAttribute("aria-pressed",s=="taken");r.querySelector(".skip").setAttribute("aria-pressed",s=="skipped");r.querySelector(".st").textContent=label[s]});
 badges();return t>0&&tk==t}
function toast(m){const e=document.createElement("div");e.className="toast";e.setAttribute("role","status");e.textContent=m;document.body.appendChild(e);setTimeout(()=>e.remove(),2600)}
function celebrate(){if(reduce)return;const box=(document.querySelector(".ring")||document.body).getBoundingClientRect(),cols=["#c9b8ff","#bff0dc","#fff2b3","#f5c842"];
 for(let i=0;i<16;i++){const e=document.createElement("i");e.className="fx";e.style.background=cols[i%4];e.style.left=(box.left+box.width/2)+"px";e.style.top=(box.top+box.height/2)+"px";document.body.appendChild(e);
 const a=Math.random()*6.28,d=70+Math.random()*90;e.animate([{transform:"translate(0,0) rotate(0)",opacity:1},{transform:"translate("+Math.cos(a)*d+"px,"+(Math.sin(a)*d+40)+"px) rotate("+(Math.random()*540)+"deg)",opacity:0}],{duration:900,easing:"ease-out"}).onfinish=()=>e.remove()}}
document.querySelectorAll(".dose button").forEach(b=>b.addEventListener("click",()=>{
 const row=b.closest(".dose"),prev=state(row),act=b.dataset.act,next=prev==act?"pending":act;
 row.classList.remove("taken","skipped");if(next!="pending")row.classList.add(next);
 if(next=="taken"){row.classList.add("pop");setTimeout(()=>row.classList.remove("pop"),500)}
 const all=refresh();if(next=="taken"&&all){celebrate();toast("All doses taken for today")}
 fetch("/api/dose",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({med:+row.dataset.med,slot:+row.dataset.slot,status:next})})
  .then(r=>{if(!r.ok)throw 0}).catch(()=>{row.classList.remove("taken","skipped");if(prev!="pending")row.classList.add(prev);refresh();toast("Could not save. Try again.")})}));
refresh();
</script>{% endblock %}"""
DASH = """{% extends "base.html" %}{% block hero %}<h1>Dashboard</h1><p>Savings, adherence, safety and match quality across your prescriptions.</p>{% endblock %}
{% block content %}
{% if not n %}<div class="card pull"><h3>No data yet</h3><p class="mute">Analyse a prescription with “Send to my tracker” ticked, or load demo data to preview the dashboard.</p><a class="btn" href="/">Analyse a prescription</a> <form method="post" action="/demo" style="display:inline"><button class="btn alt">Load demo data</button></form></div>
{% else %}
<div class="grid pull"><div class="stat win"><b>₹{{ '%.0f'|format(saved) }}</b><span>Total possible saving</span></div><div class="stat"><b>{{ avg }}%</b><span>Average saving per prescription</span></div><div class="stat"><b>{{ n }}</b><span>Prescriptions analysed</span></div><div class="stat"><b>{{ adh7 }}%</b><span>Adherence, last 7 days</span></div><div class="stat"><b>{{ streak }}</b><span>Day streak (80%+ taken)</span></div><div class="stat"><b>{{ alerts }}</b><span>Safety alerts raised</span></div></div>
<div class="two"><div class="card"><h3>Course cost: prescribed against cheapest</h3>{{ cost_svg|safe }}<div class="legend"><span><i style="background:var(--butter)"></i>As prescribed</span><span><i style="background:var(--teal)"></i>Cheapest valid</span></div></div>
<div class="card"><h3>Daily adherence, last 14 days</h3>{{ adh_svg|safe }}<div class="legend"><span><i style="background:var(--teal)"></i>Doses taken (share of scheduled)</span></div></div></div>
<div class="two"><div class="card"><h3>Most common salts</h3>{% for s,c in salts %}<div class="hb"><span>{{ s }} · {{ c }}</span><div style="width:{{ c/salts[0][1]*100 }}%"></div></div>{% endfor %}</div>
<div class="card"><h3>Match quality</h3><div class="grid" style="grid-template-columns:repeat(3,1fr)"><div class="stat"><b>{{ q[0] }}</b><span>Exact</span></div><div class="stat"><b>{{ q[1] }}</b><span>Confirm</span></div><div class="stat"><b>{{ q[2] }}</b><span>Not recognised</span></div></div>
<h3 style="margin-top:14px">Most common safety alerts</h3>{% for k,m,c in top_alerts %}<div class="alert {{ k }}">{{ m }} <b>(×{{ c }})</b></div>{% else %}<div class="alert ok">No alerts so far.</div>{% endfor %}</div></div>
<h2>History</h2><div class="card scroll"><table><tr><th>Date</th><th>Medicines</th><th>Prescribed</th><th>Cheapest</th><th>Saved</th></tr>{% for h in hist %}<tr><td>{{ h.created }}</td><td>{{ h.nm }}</td><td>₹{{ '%.0f'|format(h.prescribed) }}</td><td>₹{{ '%.0f'|format(h.cheapest) }}</td><td>₹{{ '%.0f'|format(h.prescribed-h.cheapest) }}</td></tr>{% endfor %}</table></div>
<form method="post" action="/reset" onsubmit="return confirm('Delete all saved prescriptions and dose logs?')"><button class="btn alt sm">Clear all data</button> <span class="mute">Demo data is only for previews and screenshots.</span></form>
{% endif %}{% endblock %}"""

app = Flask(__name__); app.jinja_loader = DictLoader({"base.html": BASE, "home.html": HOME, "tracker.html": TRACKER, "dashboard.html": DASH})
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
@app.errorhandler(413)
def too_big(e): return render_template("home.html", text=SAMPLE, r=None, ocr=None, err="That file is too large. Please upload an image under 8 MB.", saved=False), 413

@app.route("/", methods=["GET", "POST"])
def index():
    text, r, ocr, err, saved = SAMPLE, None, None, None, False
    if request.method == "POST":
        f = request.files.get("image")
        if f and f.filename:
            try: ocr = pytesseract.image_to_string(Image.open(io.BytesIO(f.read())))
            except pytesseract.TesseractNotFoundError: err = "Text reading (OCR) is not installed on this server. Paste the prescription text instead."
            except Exception: err = "Could not read that file. Please upload a PNG or JPG image."
            else:
                text = medicine_lines(ocr)
                if not ocr.strip(): err = "No text found in that image. Try a clearer, straight-on photo or paste the text."
        else: text = request.form.get("text", "")
        if not err:
            r = analyse(text); r["found"] = any(i["row"] for i in r["items"])
            for i in r["items"]:
                if i["row"]: i["sched"] = [f"{SLOTS[k][0]} {SLOTS[k][1]}" for k, v in enumerate(i["parse"]["freq"]) if v]
            if request.form.get("save"): saved = save_rx(r) is not None
    return render_template("home.html", text=text, r=r, ocr=ocr, err=err, saved=saved)

@app.route("/tracker")
def tracker():
    meds, dmap = load_all(); td = today(); active, done = [], []
    for m in meds:
        st, en = span(m); taken = sum(1 for k, v in dmap.items() if k[0] == m["id"] and v == "taken"); per = m["f0"] + m["f1"] + m["f2"]
        info = dict(m=m, per=per, left=max(0, m["qty"] - taken), end=en, days_left=(en - td).days + 1, pct=round(taken / m["qty"] * 100) if m["qty"] else 0)
        if m["active"]:
            (active if st <= td <= en else done).append(info)
    slots = []
    for k, (name, tm, hr) in enumerate(SLOTS):
        items = [dict(m=a["m"], status=dmap.get((a["m"]["id"], td.isoformat(), k), "pending")) for a in active if a["m"]["f%d" % k]]
        slots.append(dict(k=k, name=name, time=tm, hour=hr, items=items))
    allit = [i for s in slots for i in s["items"]]; tk = sum(i["status"] == "taken" for i in allit); sk = sum(i["status"] == "skipped" for i in allit)
    week = adherence(meds, dmap, 7); s7 = sum(s for _, s, _ in week); t7 = sum(t for _, _, t in week)
    return render_template("tracker.html", hour=datetime.now(IST).hour, today=td, active=active, done=done, slots=slots, tk=tk, sk=sk, tot=len(allit), week=week,
                           week_pct=round(t7 / s7 * 100) if s7 else 0, streak=streak_of(adherence(meds, dmap, 60)))

@app.route("/dashboard")
def dashboard():
    meds, dmap = load_all()
    with db() as c:
        rxs = c.execute("SELECT * FROM rx ORDER BY id").fetchall()
        salts = [(r[0], r[1]) for r in c.execute("SELECT salt, COUNT(*) FROM med GROUP BY salt ORDER BY 2 DESC, 1 LIMIT 6")]
        top = [(r[0], r[1], r[2]) for r in c.execute("SELECT kind, msg, COUNT(*) FROM alert GROUP BY kind, msg ORDER BY 3 DESC LIMIT 4")]
        names = {r[0]: ", ".join(x[0] for x in c.execute("SELECT brand FROM med WHERE rx_id=?", (r[0],))) for r in rxs}
    hist = [dict(created=r["created"], nm=names[r["id"]], prescribed=r["prescribed"], cheapest=r["cheapest"]) for r in reversed(rxs)]
    rows = [(date.fromisoformat(r["created"]).strftime("%d %b"), r["prescribed"], r["cheapest"]) for r in rxs[-6:]]
    week = adherence(meds, dmap, 7); s7 = sum(s for _, s, _ in week); t7 = sum(t for _, _, t in week)
    pcts = [(r["prescribed"] - r["cheapest"]) / r["prescribed"] * 100 for r in rxs if r["prescribed"]]
    return render_template("dashboard.html", n=len(rxs), saved=sum(r["prescribed"] - r["cheapest"] for r in rxs), avg=round(sum(pcts) / len(pcts)) if pcts else 0,
        adh7=round(t7 / s7 * 100) if s7 else 0, streak=streak_of(adherence(meds, dmap, 60)), alerts=sum(r["n_alerts"] for r in rxs),
        cost_svg=svg_grouped(rows), adh_svg=svg_adh(adherence(meds, dmap, 14)), salts=salts, top_alerts=top, hist=hist,
        q=(sum(r["n_exact"] for r in rxs), sum(r["n_confirm"] for r in rxs), sum(r["n_unrec"] for r in rxs)))

@app.route("/api/dose", methods=["POST"])
def api_dose():
    try: j = request.get_json(force=True); m, s, st = int(j["med"]), int(j["slot"]), j["status"]
    except (TypeError, ValueError, KeyError, AttributeError, BadRequest): return jsonify(ok=False), 400
    if st not in ("taken", "skipped", "pending") or s not in (0, 1, 2): return jsonify(ok=False), 400
    with db() as c:
        if not c.execute("SELECT 1 FROM med WHERE id=?", (m,)).fetchone(): return jsonify(ok=False), 404
        if st == "pending": c.execute("DELETE FROM dose WHERE med_id=? AND day=? AND slot=?", (m, today().isoformat(), s))
        else: c.execute("INSERT OR REPLACE INTO dose VALUES(?,?,?,?)", (m, today().isoformat(), s, st))
    return jsonify(ok=True)

@app.route("/demo", methods=["POST"])
def demo(): seed(); return redirect("/dashboard")
@app.route("/reset", methods=["POST"])
def reset(): clear(); return redirect("/dashboard")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
