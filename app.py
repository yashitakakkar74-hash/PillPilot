import os, io
from flask import Flask, request, render_template_string
from PIL import Image
import pytesseract
from core import analyse

WIN = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(WIN): pytesseract.pytesseract.tesseract_cmd = WIN

app = Flask(__name__)
SAMPLE = "Tab Dolo 650 1-0-1 x 5 days\nTab Azitral 500 OD x 3 days\nTab Pan 40 1-0-0 x 14 days\nTab Brufen 400 1-0-1 x 5 days\nTab Voveran 50 BD x 5 days\nTab Thyronorm 50 mcg 1-0-0 x 30 days"

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PillPilot</title><style>
body{font-family:system-ui,sans-serif;max-width:860px;margin:0 auto;padding:16px;background:#f2f6f8;color:#12203a}
.card{background:#fff;border:1px solid #d7e0e8;border-radius:12px;padding:14px;margin:10px 0}
textarea{width:100%;min-height:130px;font-family:monospace}table{border-collapse:collapse;width:100%}
td,th{padding:5px 8px;border-bottom:1px solid #d7e0e8;text-align:left}tr.best td{background:#d6efea;font-weight:600}
.warn{background:#fdeccd;padding:8px;border-radius:8px;margin:6px 0}.danger{background:#fde4e1;padding:8px;border-radius:8px;margin:6px 0}
.note{background:#fdeccd;padding:8px;border-radius:8px;font-size:.9em}button{padding:8px 16px;border-radius:20px;border:0;background:#0f766e;color:#fff;font-size:1em}
.sum{display:flex;gap:10px;flex-wrap:wrap}.sum div{flex:1;min-width:140px;background:#fff;border:1px solid #d7e0e8;border-radius:12px;padding:10px}.sum b{font-size:1.5em;display:block}
</style></head><body>
<h1>PillPilot</h1><p>Upload a printed prescription or paste its text. Cheaper same-salt options, safety checks and reminders.</p>
<div class="note">Sample dataset: prices and interactions are illustrative, not medical advice. Confirm every change with a doctor or pharmacist.</div>
<form class="card" method="post" enctype="multipart/form-data">
<p><b>1. Upload prescription image</b> (PNG or JPG)<br><input type="file" name="image" accept="image/*"></p>
<p><b>2. Or paste text</b> (one medicine per line)<br><textarea name="text">{{ text }}</textarea></p>
<button>Analyse prescription</button></form>
{% if r %}
{% if ocr %}<div class="card"><b>Text read from image</b><pre>{{ ocr }}</pre></div>{% endif %}
<div class="sum"><div><b>₹{{ '%.0f'|format(r.prescribed) }}</b>As prescribed</div><div><b>₹{{ '%.0f'|format(r.cheapest) }}</b>Cheapest valid combination</div><div><b>₹{{ '%.0f'|format(r.prescribed-r.cheapest) }}</b>Possible saving</div></div>
<h2>Medicines</h2>
{% for i in r['items'] %}<div class="card">
{% if not i.row %}<b>{{ i.line }}</b> – not recognised. Check the spelling or ask your pharmacist.
{% else %}<b>{{ i.row.brand }}</b> {% if i.dist %}<span class="warn">Please confirm: read as {{ i.row.brand }} (edit distance {{ i.dist }})</span>{% endif %}
<p>{{ i.row.salt }} · {{ i.row.strength }} · {{ i.row.form }} · {{ i.qty }} units ({{ i.parse.freq|join('-') }} for {{ i.parse.days }} days){% if i.parse.assumed %} · days missing, 5 assumed{% endif %}</p>
<p>Why these match: same salt, same strength, same form.</p>
<table><tr><th>Option</th><th>Type</th><th>Per unit</th><th>Course</th></tr>
{% for a in i.alts %}<tr class="{{ 'best' if loop.first }}"><td>{{ a.brand }}</td><td>{{ a.type }}</td><td>₹{{ a.price }}</td><td>₹{{ '%.0f'|format(a.price*i.qty) }}</td></tr>{% endfor %}</table>
<p><b>Reminders:</b> {{ i.sched|join(', ') }}</p>{% endif %}</div>{% endfor %}
<h2>Safety checks</h2>{% for c,t in r.alerts %}<div class="{{ c }}">{{ t }}</div>{% else %}<div class="card">No duplicates or known interactions found in the sample list.</div>{% endfor %}
{% endif %}</body></html>"""

@app.route("/", methods=["GET", "POST"])
def index():
    text, r, ocr = SAMPLE, None, None
    if request.method == "POST":
        f = request.files.get("image")
        if f and f.filename:
            ocr = pytesseract.image_to_string(Image.open(io.BytesIO(f.read())))
            text = ocr
        else:
            text = request.form.get("text", "")
        r = analyse(text)
    return render_template_string(PAGE, text=text, r=r, ocr=ocr)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
