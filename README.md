# SMULIT-Hackathon-Prismatic
To install prerequisite TesseractOCR
1) Download the installer: UB Mannheim's Windows build —
https://github.com/UB-Mannheim/tesseract/wiki
2) Add it to PATH:
    Search "Environment Variables" in the Start menu → Edit the system environment variables
    Under System variables, select Path → Edit → New
    Add: C:\Program Files\Tesseract-OCR\



To start the app

1) Open the terminal
2) run "cd aithena-hack"
3) run "pip install -r requirements.txt"
4) run "$env:OPENROUTER_API_KEY = """
5) run "uvicorn app.main:app --reload --port 8000"
6) Open another terminal
7) run "cd aithena-hack"
8) run "cd web"
10) Run "npm install"
11) Run "npm install --legacy-peer-deps"
12) Run "npm run dev"