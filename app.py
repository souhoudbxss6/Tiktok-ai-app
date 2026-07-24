"""
============================================================
  TikTok AI Poster - Application principale (Flask)
============================================================
"""

import os
import shutil
import sqlite3
import secrets
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, send_from_directory, flash,
)
from apscheduler.schedulers.background import BackgroundScheduler

import requests as http_requests

from niches import NICHES
from ai_engine import generate_complete_video
from scheduler_logic import get_next_optimal_slots
import video_providers

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(16))

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "database.db")
MEDIA_DIR = os.path.join(BASE_DIR, "media")
os.makedirs(MEDIA_DIR, exist_ok=True)

TIKTOK_CLIENT_KEY = os.environ.get("TIKTOK_CLIENT_KEY", "REMPLACE_MOI")
TIKTOK_CLIENT_SECRET = os.environ.get("TIKTOK_CLIENT_SECRET", "REMPLACE_MOI")
TIKTOK_REDIRECT_URI = os.environ.get("TIKTOK_REDIRECT_URI", "http://localhost:5000/auth/callback")

TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_UPLOAD_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"

PROVIDER_CHOICES = [
    ("auto", "Automatique (le meilleur disponible)"),
    ("heygen", "HeyGen - avatar IA (voix + visage)"),
    ("runway", "Runway - clip cinematique genere par IA"),
    ("broll", "Pexels + ElevenLabs - videos reelles + voix IA"),
]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tiktok_open_id TEXT UNIQUE,
            access_token TEXT,
            refresh_token TEXT,
            niche TEXT,
            preferred_provider TEXT DEFAULT 'auto',
            timezone TEXT DEFAULT 'Europe/Paris',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            niche TEXT,
            title TEXT,
            script TEXT,
            video_path TEXT,
            provider_used TEXT,
            status TEXT DEFAULT 'draft',
            scheduled_at TEXT,
            posted_at TEXT,
            error_message TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """
    )
    conn.commit()
    conn.close()


def run_generation_pipeline(conn, user_row):
    niche_id = user_row["niche"] or "storytelling"
    provider_pref = user_row["preferred_provider"] or "auto"

    try:
        result = generate_complete_video(niche_id, provider_pref)

        final_name = f"user{user_row['id']}_{secrets.token_hex(6)}.mp4"
        final_path = os.path.join(MEDIA_DIR, final_name)
        shutil.move(result["video_path"], final_path)

        slots = get_next_optimal_slots(user_row["timezone"], count=1)
        scheduled_at = slots[0].isoformat() if slots else None

        conn.execute(
            """INSERT INTO videos
               (user_id, niche, title, script, video_path, provider_used, status, scheduled_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                user_row["id"], niche_id, result["title"], result["script"],
                final_name, result["provider_used"], "scheduled", scheduled_at,
            ),
        )
        conn.commit()
        return True, None

    except video_providers.ProviderUnavailable as e:
        conn.execute(
            """INSERT INTO videos (user_id, niche, title, status, error_message)
               VALUES (?,?,?,?,?)""",
            (user_row["id"], niche_id, "Echec de generation", "failed", str(e)),
        )
        conn.commit()
        return False, str(e)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/niches")
def niches_page():
    return render_template("niches.html", niches=NICHES)


@app.route("/niches/select", methods=["POST"])
def select_niche():
    niche_id = request.form.get("niche_id")
    session["selected_niche"] = niche_id
    if "user_id" in session:
        conn = get_db()
        conn.execute("UPDATE users SET niche = ? WHERE id = ?", (niche_id, session["user_id"]))
        conn.commit()
        conn.close()
    return redirect(url_for("dashboard"))


@app.route("/settings", methods=["GET", "POST"])
def settings():
    if "user_id" not in session:
        return redirect(url_for("index"))

    conn = get_db()
    if request.method == "POST":
        provider = request.form.get("preferred_provider", "auto")
        timezone = request.form.get("timezone", "Europe/Paris")
        conn.execute(
            "UPDATE users SET preferred_provider=?, timezone=? WHERE id=?",
            (provider, timezone, session["user_id"]),
        )
        conn.commit()
        flash("Preferences mises a jour.")

    user = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    conn.close()
    return render_template("settings.html", user=user, providers=PROVIDER_CHOICES)


@app.route("/auth/login")
def tiktok_login():
    state = secrets.token_urlsafe(16)
    session["oauth_state"] = state
    params = {
        "client_key": TIKTOK_CLIENT_KEY,
        "response_type": "code",
        "scope": "user.info.basic,video.publish,video.upload",
        "redirect_uri": TIKTOK_REDIRECT_URI,
        "state": state,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return redirect(f"{TIKTOK_AUTH_URL}?{query}")


@app.route("/auth/callback")
def tiktok_callback():
    code = request.args.get("code")
    state = request.args.get("state")

    if state != session.get("oauth_state"):
        return "Etat OAuth invalide, connexion refusee.", 400
    if not code:
        return "Autorisation TikTok refusee.", 400

    payload = {
        "client_key": TIKTOK_CLIENT_KEY,
        "client_secret": TIKTOK_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": TIKTOK_REDIRECT_URI,
    }
    resp = http_requests.post(TIKTOK_TOKEN_URL, data=payload, timeout=15)
    data = resp.json()

    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    open_id = data.get("open_id")

    conn = get_db()
    row = conn.execute("SELECT id FROM users WHERE tiktok_open_id = ?", (open_id,)).fetchone()
    if row:
        user_id = row["id"]
        conn.execute(
            "UPDATE users SET access_token=?, refresh_token=? WHERE id=?",
            (access_token, refresh_token, user_id),
        )
    else:
        cur = conn.execute(
            "INSERT INTO users (tiktok_open_id, access_token, refresh_token) VALUES (?,?,?)",
            (open_id, access_token, refresh_token),
        )
        user_id = cur.lastrowid
    conn.commit()
    conn.close()

    session["user_id"] = user_id
    return redirect(url_for("niches_page"))


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("index"))

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    videos = conn.execute(
        "SELECT * FROM videos WHERE user_id=? ORDER BY id DESC LIMIT 20", (session["user_id"],)
    ).fetchall()
    conn.close()

    return render_template("dashboard.html", user=user, videos=videos)


@app.route("/videos/generate", methods=["POST"])
def generate_video_now():
    if "user_id" not in session:
        return redirect(url_for("index"))

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    success, error = run_generation_pipeline(conn, user)
    conn.close()

    if not success:
        flash(f"Echec de la generation video : {error}")
    return redirect(url_for("dashboard"))


@app.route("/media/<path:filename>")
def serve_media(filename):
    return send_from_directory(MEDIA_DIR, filename)


def daily_auto_pipeline():
    conn = get_db()
    users = conn.execute("SELECT * FROM users WHERE niche IS NOT NULL").fetchall()
    for user in users:
        run_generation_pipeline(conn, user)
    conn.close()


def publish_due_videos():
    conn = get_db()
    now = datetime.utcnow().isoformat()
    due_videos = conn.execute(
        "SELECT * FROM videos WHERE status='scheduled' AND scheduled_at <= ?", (now,)
    ).fetchall()

    for video in due_videos:
        user = conn.execute("SELECT * FROM users WHERE id=?", (video["user_id"],)).fetchone()
        video_file_path = os.path.join(MEDIA_DIR, video["video_path"] or "")

        if not os.path.isfile(video_file_path):
            conn.execute(
                "UPDATE videos SET status='failed', error_message=? WHERE id=?",
                ("Fichier video introuvable.", video["id"]),
            )
            conn.commit()
            continue

        try:
            headers = {
                "Authorization": f"Bearer {user['access_token']}",
                "Content-Type": "application/json; charset=UTF-8",
            }
            video_size = os.path.getsize(video_file_path)

            init_payload = {
                "post_info": {"title": video["title"], "privacy_level": "PUBLIC_TO_EVERYONE"},
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": video_size,
                    "chunk_size": video_size,
                    "total_chunk_count": 1,
                },
            }
            init_resp = http_requests.post(
                TIKTOK_UPLOAD_INIT_URL, headers=headers, json=init_payload, timeout=15
            )
            init_data = init_resp.json().get("data", {})
            upload_url = init_data.get("upload_url")

            if not upload_url:
                raise RuntimeError(f"Reponse d'initialisation TikTok invalide : {init_resp.text[:300]}")

            with open(video_file_path, "rb") as f:
                video_bytes = f.read()
            http_requests.put(
                upload_url,
                data=video_bytes,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Range": f"bytes 0-{video_size - 1}/{video_size}",
                },
                timeout=120,
            )

            conn.execute(
                "UPDATE videos SET status='posted', posted_at=? WHERE id=?",
                (datetime.utcnow().isoformat(), video["id"]),
            )
        except Exception as e:
            conn.execute(
                "UPDATE videos SET status='failed', error_message=? WHERE id=?",
                (str(e), video["id"]),
            )
            print(f"[Erreur publication] video {video['id']}: {e}")

    conn.commit()
    conn.close()


scheduler = BackgroundScheduler()
scheduler.add_job(daily_auto_pipeline, "cron", hour=5, minute=0)
scheduler.add_job(publish_due_videos, "interval", minutes=5)


@app.route("/tiktokbyL07tDQ550QRiSVW8YRZFB22AbfuhUp.txt")
def tiktok_verification():
    return "tiktok-developers-site-verification=byL07tDQ550QRiSVW8YRZFB22AbfuhUp", 200, {"Content-Type": "text/plain"}


@app.route("/tiktokXjvdz1UqY2U9i300pJVSu5PrO2TaqSD4.txt")
def tiktok_verification_2():
    return "tiktok-developers-site-verification=Xjvdz1UqY2U9i300pJVSu5PrO2TaqSD4", 200, {"Content-Type": "text/plain"}


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


init_db()
scheduler.start()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
