"""Makes 15 typed prescription images plus ground-truth files in samples/ (no Word needed)."""
import os, random
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from core import ROWS
random.seed(7); os.makedirs("samples", exist_ok=True)
try: font = ImageFont.truetype("arial.ttf", 30)
except OSError:
    try: font = ImageFont.truetype("DejaVuSans.ttf", 30)
    except OSError: font = ImageFont.load_default()
brands = [r for r in ROWS if not r["brand"].startswith("Jan")]
for n in range(1, 16):
    meds = random.sample(brands, random.randint(3, 5))
    lines = [f"Tab {m['brand']} {random.choice(['1-0-1','1-0-0','1-1-1','0-0-1'])} x {random.choice([3,5,7,10])} days" for m in meds]
    img = Image.new("RGB", (900, 120 + 60 * len(lines)), "white"); d = ImageDraw.Draw(img)
    d.text((30, 20), "Dr. A. Sharma, MBBS    Rx", fill="black", font=font)
    for k, l in enumerate(lines): d.text((30, 100 + 60 * k), l, fill="black", font=font)
    if n % 3 == 0: img = img.rotate(random.uniform(-2, 2), fillcolor="white").filter(ImageFilter.GaussianBlur(0.8))
    img.save(f"samples/rx{n:02d}.png")
    open(f"samples/rx{n:02d}.txt", "w").write("\n".join(m["brand"] for m in meds))
print("Made 15 samples in samples/")
