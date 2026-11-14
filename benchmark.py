"""DAA benchmark on a dataset scaled to 20,000 brands. Two separate tests, reported honestly."""
import random, string, time, csv
from core import ROWS, Trie, top_k, lev
random.seed(1)
big = list(ROWS)
while len(big) < 20000:
    k = "".join(random.choices(string.ascii_lowercase, k=random.randint(4, 9))) + " " + str(random.choice([5, 10, 40, 50, 500, 650]))
    big.append({"key": k, "brand": k})
trie = Trie()
for r in big: trie.add(r["key"], r)
def ms(fn, qs):
    t = time.perf_counter()
    for q in qs: fn(q)
    return (time.perf_counter() - t) / len(qs) * 1000
def typo(s):
    i = random.randrange(len(s)); return s[:i] + random.choice(string.ascii_lowercase) + s[i + 1:]

# Test A: exact brand lookup, linear scan O(N) vs trie O(L)
exact_q = [r["key"] for r in random.sample(big, 500)]
def scan(q):
    for r in big:
        if r["key"] == q: return r
a1, a2 = ms(scan, exact_q), ms(trie.get, exact_q)

# Test B: closest 3 brands for a misspelt name, full sort vs size-3 heap (edit distance dominates both)
typo_q = [typo(r["key"]) for r in random.sample(ROWS, 8)]
b1 = ms(lambda q: sorted(big, key=lambda r: lev(q, r["key"]))[:3], typo_q)
b2 = ms(lambda q: top_k(q, 3, big), typo_q)

rows = [("Exact lookup: linear scan", a1), ("Exact lookup: trie", a2), ("Top-3 typo match: full sort", b1), ("Top-3 typo match: heap (K=3)", b2)]
print(f"Dataset: {len(big)} brands")
for n, v in rows: print(f"{n:32s} {v:10.4f} ms per query")
print(f"Trie speed-up over scan: {a1 / a2:.0f}x")
print(f"Heap vs full sort: {b1 / b2:.2f}x  (edit distance dominates, so similar time; heap needs O(K) memory instead of O(N))")
with open("benchmark.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["test", "ms_per_query"]); w.writerows(rows)
