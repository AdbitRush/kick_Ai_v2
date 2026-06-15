# kickbacks_fetch.py – שליפת רווחי Kickbacks באמצעות Playwright
# תסריט זה משמש בתת‑סשן (sub‑agent) של OpenClaw. הוא קורא את שם המשתמש והסיסמה
# מקובץ הסביבה kickbacks_settings.env, נכנס לדף ההתחברות של Kickbacks,
# מושך את ה‑balance מדף /me, ושומר את התוצאה בקובץ JSON זמני.
# ניתן להגדיר הרצה בתדירות רצויה בעזרת משימת cron.

import os
import json
import subprocess
from pathlib import Path

# נסיון לטעון משתני סביבה מקובץ .env במידת האפשר
env_path = Path("/root/.openclaw/workspace/kickbacks_settings.env")
if env_path.is_file():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

# משתנים דרושים
USERNAME = os.getenv("KICKBACKS_USER")
PASSWORD = os.getenv("KICKBACKS_PASS")
OUTFILE = "/tmp/kickbacks_balance.json"

if not USERNAME or not PASSWORD:
    raise RuntimeError("Kickbacks credentials not set – please fill kickbacks_settings.env")

# וידוא שה‑Playwright מותקן (pip install playwright && playwright install)
def ensure_playwright():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        subprocess.check_call(["python3", "-m", "pip", "install", "playwright"])
        subprocess.check_call(["playwright", "install", "chromium"])

ensure_playwright()

from playwright.sync_api import sync_playwright

def fetch_balance():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        # פתיחה של דף הכניסה
        page.goto("https://kickbacks.ai/login", wait_until="networkidle")
        # אם יש אסימון Google IDTOKEN – נשתמש בו (הכנסת קוּקִי/אחסון מקומי)
        if os.getenv('KICKBACKS_GOOGLE_IDTOKEN'):
            # נכניס את האסימון כקוקי בשם "id_token" (שם הדומה למה שה‑Google משתמשת)
            page.context.add_cookies([
                {
                    'name': 'id_token',
                    'value': os.getenv('KICKBACKS_GOOGLE_IDTOKEN'),
                    'domain': 'kickbacks.ai',
                    'path': '/',
                    'httpOnly': False,
                    'secure': True,
                }
            ])
            # נוודא שה‑session משתמשת באותו קוקי ובתור מייד עורכים ניווט ל‑/me
            page.goto('https://kickbacks.ai/me', wait_until='networkidle')
        else:
            # ניסיונות כניסה – אם יש שדה email/password רגיל
            if page.query_selector('input[name="email"]'):
                page.fill('input[name="email"]', USERNAME)
                page.fill('input[name="password"]', PASSWORD)
                # לחיצה על כפתור ההתחברות (יכול להיות type="submit" או class שונה)
                submit_btn = page.query_selector('button[type="submit"]') or page.query_selector('button')
                if submit_btn:
                    submit_btn.click()
                else:
                    page.keyboard.press("Enter")
                # המתנה לטעינת עמוד החשבון
                page.wait_for_url("**/me", timeout=15000)
                page.wait_for_load_state('networkidle')
            else:
                # במידה והדף מציג Login with Google – נצא עם הודעה למשתמש.
                raise RuntimeError("Login page does not contain email/password fields. אפשר לשקול התחברות דרך Google, שדורשת תהליך OAuth חיצוני.")
        # חיפוש אלמנט המצביע על ה‑balance – משערים class בשם balance או data-testid
        balance_el = page.query_selector('.balance') or page.query_selector('[data-testid="balance"]')
        if not balance_el:
            # fallback – נסה לחפש טקסט שמתחיל במטבע $ או ש"""
