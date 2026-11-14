import os, io
from flask import Flask, request, render_template_string
from PIL import Image
import pytesseract
from core import analyse

WIN = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(WIN): pytesseract.pytesseract.tesseract_cmd = WIN

app = Flask(__name__)
SAMPLE = "Tab Dolo 650 1-0-1 x 5 days\nTab Azitral 500 OD x 3 days\nTab Pan 40 1-0-0 x 14 days\nTab Brufen 400 1-0-1 x 5 days\nTab Voveran 50 BD x 5 days\nTab Thyronorm 50 mcg 1-0-0 x 30 days"

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PillPilot</title><style>
:root{--bg:#f1f5f9;--card:#fff;--ink:#0f1b33;--mute:#5a6a82;--line:#dbe3ec;--teal:#0f766e;--tealbg:#d5f0eb;--amb:#8a5200;--ambbg:#fdeccd;--red:#b42318;--redbg:#fde4e1;--hero1:#0f766e;--hero2:#115e8a}
@media (prefers-color-scheme:dark){:root{--bg:#0b1220;--card:#141e30;--ink:#e8eef7;--mute:#9aabc2;--line:#28384e;--teal:#4fd1c0;--tealbg:#123a39;--amb:#f3c26b;--ambbg:#3a2c10;--red:#ff9b8f;--redbg:#3d1a17;--hero1:#0b4f4a;--hero2:#0c3f5e}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.hero{background:linear-gradient(120deg,var(--hero1),var(--hero2));color:#fff;padding:28px 16px 70px}
.wrap{max-width:900px;margin:0 auto;padding:0 16px}.hero .wrap{padding:0}
.brand{display:flex;align-items:center;gap:10px;font-weight:800;font-size:1.5rem;letter-spacing:-.01em}
.logo{width:34px;height:18px;border-radius:9px;background:linear-gradient(90deg,#fff 50%,#9be7dc 50%);transform:rotate(-30deg);box-shadow:0 0 0 2px rgba(255,255,255,.4)}
.hero p{margin:8px 0 0;max-width:56ch;opacity:.92}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px;margin-bottom:14px;box-shadow:0 1px 2px rgba(15,27,51,.05)}
.up{margin-top:-48px}
.drop{display:block;border:2px dashed var(--line);border-radius:14px;padding:26px 14px;text-align:center;cursor:pointer;transition:.15s}
.drop:hover,.drop.over{border-color:var(--teal);background:var(--tealbg)}
.drop b{display:block;font-size:1.05rem}.drop span{color:var(--mute);font-size:.9rem}
.drop input{display:none}#prev{max-height:130px;border-radius:8px;margin-top:10px;display:none}
.or{text-align:center;color:var(--mute);font-size:.85rem;margin:12px 0}
textarea{width:100%;min-height:120px;border:1px solid var(--line);border-radius:12px;padding:10px;background:var(--bg);color:var(--ink);font:14px/1.5 ui-monospace,Menlo,Consolas,monospace}
button,.btn{font:inherit;cursor:pointer}
.go{width:100%;margin-top:12px;background:var(--teal);color:var(--card);border:0;border-radius:12px;padding:12px;font-weight:700;font-size:1rem}
.go:disabled{opacity:.7;cursor:wait}
.note{font-size:.84rem;color:var(--amb);background:var(--ambbg);border-radius:10px;padding:8px 12px;margin:12px 0}
h2{font-size:1.15rem;margin:26px 0 10px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:6px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}
.stat b{display:block;font-size:1.8rem;font-weight:800;line-height:1.1}.stat span{color:var(--mute);font-size:.84rem}
.stat.win{background:var(--tealbg);border-color:var(--teal)}.stat.win b{color:var(--teal)}
.title{display:flex;flex-wrap:wrap;align-items:center;gap:8px}.title b{font-size:1.1rem}
.badge{font-size:.76rem;border-radius:999px;padding:2px 10px;background:var(--tealbg);color:var(--teal);font-weight:600}
.badge.warn{background:var(--ambbg);color:var(--amb)}.badge.bad{background:var(--redbg);color:var(--red)}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}.chip{font-size:.8rem;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:2px 9px;color:var(--mute)}
.why{font-size:.86rem;color:var(--mute);margin:4px 0 8px}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:440px;font-size:.92rem}
th{font-size:.78rem;text-transform:uppercase;letter-spacing:.04em;color:var(--mute)}
th,td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left}
tr.best td{background:var(--tealbg);font-weight:600}tr:last-child td{border-bottom:0}
.alert{border-radius:12px;padding:10px 14px;margin-bottom:8px;font-size:.93rem}
.alert.warn{background:var(--ambbg);color:var(--amb)}.alert.danger{background:var(--redbg);color:var(--red)}.alert.ok{background:var(--tealbg);color:var(--teal)}
.doses{display:flex;flex-wrap:wrap;gap:10px;margin-top:6px}
.dose{width:78px;height:78px;border-radius:50%;border:2px solid var(--teal);background:var(--tealbg);color:var(--teal);font-size:.7rem;line-height:1.25;padding:0;font-weight:600}
.dose.taken{background:transparent;border-style:dashed;opacity:.65}.dose.taken::after{content:"\\2713 taken";display:block}
.dose.skipped{background:var(--redbg);border-color:var(--red);color:var(--red)}.dose.skipped::after{content:"skipped";display:block}
.hint{font-size:.82rem;color:var(--mute)}
pre{white-space:pre-wrap;margin:6px 0 0;font-size:.88rem}
footer{color:var(--mute);font-size:.8rem;text-align:center;padding:24px 16px 40px}
:focus-visible{outline:3px solid var(--teal);outline-offset:2px}
</style></head><body>
<div class="hero"><div class="wrap"><div class="brand"><span class="logo"></span>PillPilot</div>
<p>Guiding every dose and every rupee. Upload a printed prescription to find cheaper same-salt options, check safety and plan your doses.</p></div></div>
<div class="wrap">
<form class="card up" method="post" enctype="multipart/form-data" id="f">
<label class="drop" id="drop"><input type="file" name="image" id="file" accept="image/*">
<b>Drop a prescription image here, or click to choose</b><span>PNG or JPG, printed or typed prescriptions only</span><img id="prev" alt="Preview of the chosen prescription"></label>
<div class="or">or paste the text, one medicine per line</div>
<textarea name="text" aria-label="Prescription text">{{ text }}</textarea>
<button class="go" id="btn">Analyse prescription</button>
<div class="note">Demo data: prices and interactions are illustrative samples, not medical advice. Always confirm with your doctor or pharmacist before changing a medicine.</div>
</form>
{% if err %}<div class="alert danger">{{ err }}</div>{% endif %}
{% if r %}
{% if ocr %}<div class="card"><b>Text read from the image</b><pre>{{ ocr }}</pre></div>{% endif %}
<h2>Course cost</h2>
<div class="stats"><div class="stat"><b>₹{{ '%.0f'|format(r.prescribed) }}</b><span>As prescribed</span></div>
<div class="stat win"><b>₹{{ '%.0f'|format(r.cheapest) }}</b><span>Cheapest valid combination</span></div>
<div class="stat"><b>₹{{ '%.0f'|format(r.prescribed-r.cheapest) }}</b><span>Possible saving{% if r.prescribed %} ({{ '%.0f'|format((r.prescribed-r.cheapest)/r.prescribed*100) }}%){% endif %}</span></div></div>
<h2>Medicines</h2>
{% for i in r['items'] %}<div class="card">
{% if not i.row %}<div class="title"><b>{{ i.line }}</b><span class="badge bad">Not recognised</span></div><p class="why">No close match in the dataset. Check the spelling or ask your pharmacist.</p>
{% else %}<div class="title"><b>{{ i.row.brand }}</b>{% if i.dist %}<span class="badge warn">Please confirm (edit distance {{ i.dist }})</span>{% else %}<span class="badge">Exact match</span>{% endif %}</div>
<div class="chips"><span class="chip">{{ i.row.salt }}</span><span class="chip">{{ i.row.strength }}</span><span class="chip">{{ i.row.form }}</span><span class="chip">{{ i.qty }} units</span><span class="chip">{{ i.parse.freq|join('-') }} for {{ i.parse.days }} days</span>{% if i.parse.assumed %}<span class="chip">days missing, 5 assumed</span>{% endif %}</div>
<p class="why">Why these match: same salt, same strength and same form as the prescribed medicine.</p>
<div class="scroll"><table><tr><th>Option</th><th>Type</th><th>Per unit</th><th>Course</th></tr>
{% for a in i.alts %}<tr class="{{ 'best' if loop.first }}"><td>{{ a.brand }}{% if loop.first %} · cheapest{% endif %}</td><td>{{ a.type }}</td><td>₹{{ a.price }}</td><td>₹{{ '%.0f'|format(a.price*i.qty) }}</td></tr>{% endfor %}</table></div>
<p class="hint" style="margin:12px 0 0">Doses today (tap to mark taken, tap again for skipped, again to reset)</p>
<div class="doses">{% for s in i.sched %}<button type="button" class="dose" data-id="{{ i.row.brand }}|{{ s }}" aria-label="{{ s }} dose of {{ i.row.brand }}">{{ s.split(' ')[0] }}<br>{{ s.split(' ')[1] }}</button>{% endfor %}</div>
{% endif %}</div>{% endfor %}
<h2>Safety checks</h2>
{% for c,t in r.alerts %}<div class="alert {{ c }}">{{ t }}</div>{% else %}<div class="alert ok">No duplicate salts or known interactions found in the sample list.</div>{% endfor %}
<p class="hint">Every swap keeps the same salt, strength and form. Confirm with a doctor or pharmacist first.</p>
{% endif %}
</div>
<footer>PillPilot · decision support only · does not sell or dispense medicines</footer>
<script>
const drop=document.getElementById("drop"),file=document.getElementById("file"),prev=document.getElementById("prev");
function show(){const f=file.files[0];if(!f)return;prev.src=URL.createObjectURL(f);prev.style.display="inline-block";drop.querySelector("b").textContent=f.name}
file.addEventListener("change",show);
["dragenter","dragover"].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.add("over")}));
["dragleave","drop"].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.remove("over")}));
drop.addEventListener("drop",ev=>{if(ev.dataTransfer.files.length){file.files=ev.dataTransfer.files;show()}});
document.getElementById("f").addEventListener("submit",()=>{const b=document.getElementById("btn");b.disabled=true;b.textContent="Reading prescription..."});
const KEY="pillpilot-doses-"+new Date().toDateString();let st={};
try{st=JSON.parse(localStorage.getItem(KEY)||"{}")}catch(e){}
document.querySelectorAll(".dose").forEach(b=>{const s=st[b.dataset.id];if(s)b.classList.add(s);
 b.addEventListener("click",()=>{const cur=st[b.dataset.id]||"",nx=cur===""?"taken":cur==="taken"?"skipped":"";
  b.classList.remove("taken","skipped");if(nx){b.classList.add(nx);st[b.dataset.id]=nx}else delete st[b.dataset.id];
  try{localStorage.setItem(KEY,JSON.stringify(st))}catch(e){}})});
</script></body></html>"""

@app.route("/", methods=["GET", "POST"])
def index():
    text, r, ocr = SAMPLE, None, None
    if request.method == "POST":
        f = request.files.get("image")
        if f and f.filename:
            try:
                ocr = pytesseract.image_to_string(Image.open(io.BytesIO(f.read())))
            except Exception:
                return render_template_string(PAGE, text=SAMPLE, r=None, ocr=None, err="Could not read that file. Please upload a PNG or JPG image.")
            text = ocr
        else:
            text = request.form.get("text", "")
        r = analyse(text)
    return render_template_string(PAGE, text=text, r=r, ocr=ocr, err=None)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
