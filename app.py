from flask import Flask, render_template, request, redirect, url_for
import sqlite3, os, uuid
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
DB_PATH = "database.db"

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASS")
APP_HOST = os.getenv("APP_HOST", "http://127.0.0.1:5000")

# --- DB init ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            subject TEXT,
            body TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER,
            email TEXT,
            tracking_code TEXT,
            clicked INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- send email (Gmail SMTP) ---
def send_mail(to_email, subject, html_body, tracking_code):
    if not (GMAIL_USER and GMAIL_APP_PASS):
        raise RuntimeError("GMAIL_USER or GMAIL_APP_PASS not set in .env")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = to_email

    # insert tracking URL
    track_url = f"{APP_HOST}/track/{tracking_code}"
    html_body = html_body.replace("{{TRACK}}", track_url)

    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_USER, GMAIL_APP_PASS)
        result = smtp.sendmail(GMAIL_USER, to_email, msg.as_string())
        # result is {} on success
        print("SMTP send result for", to_email, result)

# --- routes ---
@app.route("/")
def index():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, subject FROM campaigns ORDER BY id DESC")
    campaigns = c.fetchall()
    conn.close()
    return render_template("index.html", campaigns=campaigns)

@app.route("/campaign/create", methods=["GET","POST"])
def create_campaign():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        subject = request.form.get("subject","").strip()
        body = request.form.get("body","").strip()
        recipients = request.form.get("recipients","").split(",")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO campaigns (name, subject, body) VALUES (?, ?, ?)", (name, subject, body))
        campaign_id = c.lastrowid
        conn.commit()
        for r in recipients:
            r = r.strip()
            if not r:
                continue
            code = str(uuid.uuid4())
            c.execute("INSERT INTO events (campaign_id, email, tracking_code) VALUES (?, ?, ?)", (campaign_id, r, code))
            conn.commit()
            try:
                send_mail(r, subject, body, code)
                print("Sent to", r)
            except Exception as e:
                print("Error sending to", r, str(e))
        conn.close()
        return redirect(url_for("index"))
    return render_template("create_campaign.html")

@app.route("/track/<code>")
def track(code):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # mark the matching tracking_code clicked
    c.execute("UPDATE events SET clicked = 1 WHERE tracking_code = ?", (code,))
    conn.commit()
    conn.close()
    return render_template("tracking.html")

@app.route("/campaign/<int:cid>")
def campaign_dashboard(cid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT email, clicked FROM events WHERE campaign_id = ?", (cid,))
    rows = c.fetchall()
    conn.close()
    return render_template("dashboard.html", rows=rows)

if __name__ == '__main__':
    # run on all interfaces so EC2 IP is reachable
    app.run(host='0.0.0.0', port=5000, debug=True)
