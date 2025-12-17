import sqlite3
import smtplib
import uuid
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import wraps
from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash
)
from werkzeug.security import generate_password_hash, check_password_hash

# -------------------------------------------------
# APP CONFIG
# -------------------------------------------------
app = Flask(__name__)
app.secret_key = "change_this_secret_for_demo"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

# UPDATE THIS TO YOUR CURRENT PUBLIC IP / DOMAIN
APP_HOST = "http://15.207.109.73:5000/"

# -------------------------------------------------
# EMAIL CONFIG (GMAIL SMTP)
# -------------------------------------------------
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465
SMTP_USER = "rhushiarnd@gmail.com"
SMTP_PASS = "mplhcthixtzcrtmu"

# -------------------------------------------------
# DATABASE INITIALIZATION
# -------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Campaigns table
    c.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            subject TEXT,
            body TEXT
        )
    """)

    # Events table
    c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER,
            email TEXT,
            tracking_code TEXT,
            clicked INTEGER DEFAULT 0
        )
    """)

    # Admin users table
    c.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT
        )
    """)

    conn.commit()
    conn.close()

init_db()

# -------------------------------------------------
# CREATE DEFAULT ADMIN (RUNS ONCE)
# -------------------------------------------------
def ensure_admin():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM admins")
    count = c.fetchone()[0]

    if count == 0:
        # default admin credentials
        username = "admin"
        password = "admin123"
        pwd_hash = generate_password_hash(password)
        c.execute(
            "INSERT INTO admins (username, password_hash) VALUES (?, ?)",
            (username, pwd_hash)
        )
        conn.commit()
        print("Default admin created -> username: admin | password: admin123")

    conn.close()

ensure_admin()

# -------------------------------------------------
# LOGIN REQUIRED DECORATOR
# -------------------------------------------------
def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("login", next=request.path))
        return func(*args, **kwargs)
    return wrapper

# -------------------------------------------------
# EMAIL SENDER
# -------------------------------------------------
def send_mail(to_email, subject, body_html):
    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_USER
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body_html, "html"))

    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, to_email, msg.as_string())

# -------------------------------------------------
# ROUTES
# -------------------------------------------------

# LOGIN
@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = request.args.get("next") or url_for("index")

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "SELECT password_hash FROM admins WHERE username = ?",
            (username,)
        )
        row = c.fetchone()
        conn.close()

        if row and check_password_hash(row[0], password):
            session.clear()
            session["admin_logged_in"] = True
            session["admin_username"] = username
            return redirect(next_url)

        flash("Invalid username or password", "danger")

    return render_template("login.html")

# LOGOUT
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# DASHBOARD
@app.route("/")
@login_required
def index():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, subject FROM campaigns ORDER BY id DESC")
    campaigns = c.fetchall()
    conn.close()
    return render_template("index.html", campaigns=campaigns)

# CREATE CAMPAIGN
@app.route("/campaign/create", methods=["GET", "POST"])
@login_required
def create_campaign():
    if request.method == "POST":
        name = request.form["name"]
        subject = request.form["subject"]
        body = request.form["body"]
        recipients = request.form["recipients"]

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        c.execute(
            "INSERT INTO campaigns (name, subject, body) VALUES (?, ?, ?)",
            (name, subject, body)
        )
        campaign_id = c.lastrowid

        emails = [e.strip() for e in recipients.split(",") if e.strip()]

        for email in emails:
            code = str(uuid.uuid4())
            track_url = f"{APP_HOST}/track/{code}"
            email_body = body.replace("{{TRACK}}", track_url)

            c.execute(
                "INSERT INTO events (campaign_id, email, tracking_code) VALUES (?, ?, ?)",
                (campaign_id, email, code)
            )

            send_mail(email, subject, email_body)

        conn.commit()
        conn.close()
        return redirect(url_for("index"))

    return render_template("create_campaign.html")

# CAMPAIGN STATS
@app.route("/campaign/<int:cid>")
@login_required
def campaign_dashboard(cid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT email, clicked FROM events WHERE campaign_id = ?",
        (cid,)
    )
    rows = c.fetchall()
    conn.close()
    return render_template("dashboard.html", rows=rows)

# TRACKING PAGE (PUBLIC)
@app.route("/track/<code>")
def track(code):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "UPDATE events SET clicked = 1 WHERE tracking_code = ?",
        (code,)
    )
    conn.commit()
    conn.close()
    return render_template("tracking.html")

# -------------------------------------------------
# RUN APP
# -------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
