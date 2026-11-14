# PillPilot: run it on Windows

1. Install Python (tick "Add python.exe to PATH") and Tesseract (UB Mannheim installer, default folder).
2. Open this folder in VS Code, then Terminal > New Terminal, and run:
   pip install -r requirements.txt
3. Start the app:  python app.py   then open http://localhost:5000
4. Accuracy (Deep Learning part):  python generate_samples.py   then   python evaluate_ocr.py
5. Benchmark (DAA part):           python benchmark.py
6. Docker (Cloud part):  docker build -t pillpilot .   then   docker run -p 5000:5000 pillpilot
   Take a screenshot of the browser at localhost:5000 while the container runs.

If Python says "pip is not recognized", try:  py -m pip install -r requirements.txt   and run scripts with  py app.py.
Prices and interactions in data.csv / core.py are SAMPLE data. Replace data.csv with Jan Aushadhi or NPPA data if you can.
