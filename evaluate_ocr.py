"""Runs OCR + matching on samples/ and prints precision, recall and F1 (medicine level)."""
import os, csv
from PIL import Image
import pytesseract
from core import match_line, norm
WIN = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(WIN): pytesseract.pytesseract.tesseract_cmd = WIN
TP = FP = FN = 0; rows = []
for f in sorted(os.listdir("samples")):
    if not f.lower().endswith((".png", ".jpg", ".jpeg")): continue
    truth = {norm(x) for x in open(f"samples/{os.path.splitext(f)[0]}.txt").read().splitlines() if x.strip()}
    text = pytesseract.image_to_string(Image.open(f"samples/{f}"))
    pred = {m["row"]["key"] for m in (match_line(l) for l in text.splitlines() if l.strip()) if m["row"]}
    tp, fp, fn = len(truth & pred), len(pred - truth), len(truth - pred)
    TP += tp; FP += fp; FN += fn; rows.append([f, tp, fp, fn])
    print(f"{f}: correct={tp} wrong={fp} missed={fn}")
P = TP / (TP + FP) if TP + FP else 0; R = TP / (TP + FN) if TP + FN else 0
F1 = 2 * P * R / (P + R) if P + R else 0
print(f"\nPrecision={P:.3f}  Recall={R:.3f}  F1={F1:.3f}")
with open("ocr_results.csv", "w", newline="") as o:
    w = csv.writer(o); w.writerow(["image", "tp", "fp", "fn"]); w.writerows(rows)
    w.writerow(["TOTAL", TP, FP, FN]); w.writerow(["precision/recall/F1", round(P,3), round(R,3), round(F1,3)])
