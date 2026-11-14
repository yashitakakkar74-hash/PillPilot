"""PillPilot core logic. DAA parts (edit distance, trie, max-heap top-K) are written by hand."""
import csv, os, re

def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()

def load(path=None):
    path = path or os.path.join(os.path.dirname(__file__), "data.csv")
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r["price"] = float(r["price"]); r["key"] = norm(r["brand"]); rows.append(r)
    return rows

ROWS = load()

# ---- DAA 1: Levenshtein edit distance, dynamic programming, O(n*m) ----
def lev(a, b):
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i]
        for j in range(1, len(b) + 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1])))
        prev = cur
    return prev[-1]

# ---- DAA 2: Trie, exact lookup in O(length of word) ----
class Trie:
    def __init__(self): self.root = {}
    def add(self, word, value):
        n = self.root
        for c in word: n = n.setdefault(c, {})
        n["$"] = value
    def get(self, word):
        n = self.root
        for c in word:
            n = n.get(c)
            if n is None: return None
        return n.get("$")

TRIE = Trie()
for _r in ROWS: TRIE.add(_r["key"], _r)

# ---- DAA 3: max-heap of size K keeps the K closest matches, O(N log K) ----
class MaxHeap:
    def __init__(self): self.a = []
    def top(self): return self.a[0][0]
    def push(self, item):
        self.a.append(item); i = len(self.a) - 1
        while i > 0 and self.a[(i - 1) // 2][0] < self.a[i][0]:
            p = (i - 1) // 2; self.a[p], self.a[i] = self.a[i], self.a[p]; i = p
    def replace_top(self, item):
        self.a[0] = item; i = 0; n = len(self.a)
        while True:
            l, r, m = 2 * i + 1, 2 * i + 2, i
            if l < n and self.a[l][0] > self.a[m][0]: m = l
            if r < n and self.a[r][0] > self.a[m][0]: m = r
            if m == i: break
            self.a[i], self.a[m] = self.a[m], self.a[i]; i = m

def top_k(query, k=3, rows=None):
    heap = MaxHeap()
    for idx, r in enumerate(rows if rows is not None else ROWS):
        d = lev(query, r["key"])
        if len(heap.a) < k: heap.push((d, idx, r))
        elif d < heap.top(): heap.replace_top((d, idx, r))
    return [(d, r) for d, _, r in sorted(heap.a, key=lambda t: (t[0], t[1]))]

# ---- Parsing and matching one prescription line ----
FREQ = {"od": (1,0,0), "bd": (1,0,1), "bid": (1,0,1), "tds": (1,1,1), "tid": (1,1,1), "qid": (1,1,1)}

def parse_line(line):
    s = line.lower().replace(",", " ").replace(".", " ")
    freq, days, assumed = None, 5, True
    m = re.search(r"\b([01])\s*-\s*([01])\s*-\s*([01])\b", s)
    if m: freq = tuple(int(x) for x in m.groups()); s = s.replace(m.group(0), " ")
    else:
        m = re.search(r"\b(od|bd|bid|tds|tid|qid)\b", s)
        if m: freq = FREQ[m.group(1)]; s = s.replace(m.group(0), " ")
    m = re.search(r"(?:x|for)?\s*(\d+)\s*(days?|d|weeks?|wks?)\b", s)
    if m:
        days = int(m.group(1)) * (7 if m.group(2).startswith("w") else 1)
        s = s.replace(m.group(0), " ")
        assumed = False
    if freq is None: freq = (1, 0, 1)
    s = norm(re.sub(r"\b(tab|tablet|cap|capsule|mg|mcg)\b", " ", s))
    return {"key": s, "freq": freq, "days": days, "assumed": assumed}

def match_line(line):
    p = parse_line(line)
    exact = TRIE.get(p["key"])
    cands = [(0, exact)] if exact else []
    cands += [c for c in top_k(p["key"], 3) if c[1] is not exact]
    ok = bool(cands) and cands[0][0] <= max(2, int(len(p["key"]) * 0.3))
    return {"line": line, "parse": p, "cands": cands, "row": cands[0][1] if ok else None,
            "dist": cands[0][0] if ok else None, "qty": sum(p["freq"]) * p["days"]}

def alternatives(r):
    return sorted([x for x in ROWS if (x["salt"], x["strength"], x["form"]) == (r["salt"], r["strength"], r["form"])],
                  key=lambda x: x["price"])

INTERACT = [("Ibuprofen","Diclofenac","Two NSAIDs together raise the risk of stomach bleeding and kidney strain."),
            ("Aspirin","Ibuprofen","Ibuprofen can interfere with low-dose aspirin and adds bleeding risk."),
            ("Aspirin","Diclofenac","Two NSAID-type drugs together raise bleeding risk."),
            ("Telmisartan","Ibuprofen","NSAIDs can weaken blood-pressure control and strain the kidneys."),
            ("Telmisartan","Diclofenac","NSAIDs can weaken blood-pressure control and strain the kidneys."),
            ("Pantoprazole","Levothyroxine","May reduce levothyroxine absorption; the doctor may need to adjust the dose.")]
CHECK_DOCTOR = {"Levothyroxine": "Narrow dose range: confirm with your doctor before changing brand."}
SLOTS = ["Morning 8:00", "Afternoon 14:00", "Night 21:00"]

def analyse(text):
    items = [match_line(l.strip()) for l in text.splitlines() if l.strip()]
    ok = [i for i in items if i["row"]]
    for i in ok:
        i["alts"] = alternatives(i["row"])
        i["sched"] = [SLOTS[k] for k, f in enumerate(i["parse"]["freq"]) if f]
    prescribed = sum(i["row"]["price"] * i["qty"] for i in ok)
    # Each medicine is an independent choice, so the cheapest valid option per medicine gives the cheapest basket (greedy is optimal).
    cheapest = sum(i["alts"][0]["price"] * i["qty"] for i in ok)
    salts = [i["row"]["salt"] for i in ok]; alerts = []
    for k, s in enumerate(salts):
        if s in salts[:k]: alerts.append(("danger", f"Duplicate salt: {s} appears more than once."))
    for a, b, t in INTERACT:
        if a in salts and b in salts: alerts.append(("warn", f"{a} + {b}: {t}"))
    for s in dict.fromkeys(salts):
        if s in CHECK_DOCTOR: alerts.append(("warn", f"{s}: {CHECK_DOCTOR[s]}"))
    return {"items": items, "prescribed": prescribed, "cheapest": cheapest, "alerts": alerts}
