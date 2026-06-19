import os
import re
import json
import sqlite3
from datetime import datetime, date

import fitz  # PyMuPDF
from dotenv import load_dotenv
from flask import (Flask, render_template, request, redirect,
                   url_for, flash, session, jsonify)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import google.generativeai as genai

load_dotenv()

# ── App config ───────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "studyverse_secret_key_change_me")
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

os.makedirs("uploads", exist_ok=True)

# ── Database ─────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "")

class DBAdapter:
    def __init__(self):
        self.is_pg = DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://")
        if self.is_pg:
            # psycopg2 requires 'postgresql://' instead of standard 'postgres://' URLs Render sometimes provides
            self.db_uri = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        else:
            self.db_uri = "database.db"

    def get_conn(self):
        if self.is_pg:
            import psycopg2
            return psycopg2.connect(self.db_uri)
        else:
            conn = sqlite3.connect(self.db_uri)
            conn.row_factory = sqlite3.Row
            return conn

    def init_db(self):
        conn = self.get_conn()
        cur = conn.cursor()
        if self.is_pg:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id          SERIAL PRIMARY KEY,
                    username    VARCHAR(100) NOT NULL UNIQUE,
                    email       VARCHAR(100) NOT NULL UNIQUE,
                    password    VARCHAR(255) NOT NULL,
                    xp          INTEGER NOT NULL DEFAULT 0,
                    level       INTEGER NOT NULL DEFAULT 1,
                    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS documents (
                    id              SERIAL PRIMARY KEY,
                    user_id         INTEGER NOT NULL REFERENCES users(id),
                    title           VARCHAR(255) NOT NULL,
                    filename        VARCHAR(255) NOT NULL,
                    page_count      INTEGER NOT NULL DEFAULT 0,
                    summary         TEXT,
                    flashcards_json TEXT,
                    quiz_json       TEXT,
                    uploaded_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS quiz_sessions (
                    id          SERIAL PRIMARY KEY,
                    user_id     INTEGER NOT NULL REFERENCES users(id),
                    doc_id      INTEGER NOT NULL REFERENCES documents(id),
                    score       INTEGER NOT NULL DEFAULT 0,
                    total       INTEGER NOT NULL DEFAULT 0,
                    xp_earned   INTEGER NOT NULL DEFAULT 0,
                    taken_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
        else:
            cur.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    username    TEXT    NOT NULL UNIQUE,
                    email       TEXT    NOT NULL UNIQUE,
                    password    TEXT    NOT NULL,
                    xp          INTEGER NOT NULL DEFAULT 0,
                    level       INTEGER NOT NULL DEFAULT 1,
                    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS documents (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id         INTEGER NOT NULL REFERENCES users(id),
                    title           TEXT    NOT NULL,
                    filename        TEXT    NOT NULL,
                    page_count      INTEGER NOT NULL DEFAULT 0,
                    summary         TEXT,
                    flashcards_json TEXT,
                    quiz_json       TEXT,
                    uploaded_at     TEXT    NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS quiz_sessions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER NOT NULL REFERENCES users(id),
                    doc_id      INTEGER NOT NULL REFERENCES documents(id),
                    score       INTEGER NOT NULL DEFAULT 0,
                    total       INTEGER NOT NULL DEFAULT 0,
                    xp_earned   INTEGER NOT NULL DEFAULT 0,
                    taken_at    TEXT    NOT NULL DEFAULT (datetime('now'))
                );
            """)
            conn.commit()
        conn.close()

db_adapter = DBAdapter()

class MockCursor:
    def __init__(self, val):
        self.val = val
    def fetchone(self):
        return [self.val]

class ConnectionWrapper:
    def __init__(self, conn, is_pg):
        self.conn = conn
        self.is_pg = is_pg
        self.last_row_id = None

    def execute(self, query, params=()):
        if self.is_pg:
            if "last_insert_rowid()" in query:
                return MockCursor(self.last_row_id)
            
            translated_query = query.replace("?", "%s")
            
            is_insert = translated_query.strip().lower().startswith("insert")
            if is_insert:
                translated_query += " RETURNING id"
                
            from psycopg2.extras import RealDictCursor
            cur = self.conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(translated_query, params)
            
            if is_insert:
                row = cur.fetchone()
                if row:
                    self.last_row_id = row['id']
            return cur
        else:
            return self.conn.execute(query, params)

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

def get_db():
    if db_adapter.is_pg:
        return ConnectionWrapper(db_adapter.get_conn(), True)
    else:
        return ConnectionWrapper(db_adapter.get_conn(), False)

def init_db():
    db_adapter.init_db()

# Run database initialization at startup so tables exist on live server
try:
    init_db()
except Exception as e:
    print(f"Warning: Database initialization failed at startup: {repr(e)}")


# ── XP / level helpers ────────────────────────────────────────────────────────
LEVEL_TITLES = {1:"Novice", 2:"Apprentice", 3:"Scholar",
                4:"Expert",  5:"Master",    6:"Grandmaster", 7:"Legend"}
XP_PER_LEVEL = 200   # XP needed per level


def level_title(level):
    return LEVEL_TITLES.get(level, "Legend")


def xp_progress_pct(xp, level):
    earned_in_level = xp - (level - 1) * XP_PER_LEVEL
    return min(100, max(0, int(earned_in_level / XP_PER_LEVEL * 100)))


def award_xp(user_id, amount):
    conn = get_db()
    row = conn.execute("SELECT xp, level FROM users WHERE id=?", (user_id,)).fetchone()
    new_xp = row["xp"] + amount
    new_level = min(7, (new_xp // XP_PER_LEVEL) + 1)
    conn.execute("UPDATE users SET xp=?, level=? WHERE id=?", (new_xp, new_level, user_id))
    conn.commit()
    conn.close()
    return new_xp, new_level


# ── PDF helpers ───────────────────────────────────────────────────────────────
def extract_pdf_text(filepath):
    doc = fitz.open(filepath)
    text = "".join(page.get_text() for page in doc)
    pages = len(doc)
    doc.close()
    return text, pages


# ── Gemini helpers ────────────────────────────────────────────────────────────
def _local_fallback_flashcards(text, title="Concept"):
    cards = []
    seen = set()
    sentences = [s.strip() for s in re.split(r'[.!?\n]', text) if len(s.strip()) > 15]
    
    for s in sentences:
        s_clean = re.sub(r'\s+', ' ', s).strip()
        match = re.search(r'^([A-Z][A-Za-z0-9\s_]{2,25})\s*(?::| is | - )\s*(.+)$', s_clean)
        if match:
            front = match.group(1).strip()
            back = match.group(2).strip()
            if front.lower() not in seen and len(front.split()) <= 4 and len(back) > 10:
                seen.add(front.lower())
                cards.append({"front": front, "back": back[:150]})
                if len(cards) >= 10:
                    break
    
    if len(cards) < 3:
        for s in sentences[:15]:
            s_clean = re.sub(r'\s+', ' ', s).strip()
            words_s = s_clean.split()
            if len(words_s) > 4:
                front = " ".join(words_s[:3])
                back = " ".join(words_s[3:])
                if front.lower() not in seen:
                    seen.add(front.lower())
                    cards.append({"front": front, "back": back[:150]})
                    if len(cards) >= 10:
                        break

    if not cards:
        cards = [
            {"front": "Core Material", "back": f"Study details extracted from your file: '{title}'."},
            {"front": "Key Takeaway", "back": "Ensure you read all slides and chapters before testing."}
        ]
    return cards


def _local_fallback_quiz(text, title="Concept"):
    cards = _local_fallback_flashcards(text, title)
    quiz = []
    for card in cards[:8]:
        correct = card["back"]
        options = [correct]
        others = [c["back"] for c in cards if c["back"] != correct]
        while len(options) < 4:
            if others:
                options.append(others.pop(0))
            else:
                options.append(f"Alternative definition option {len(options) + 1} from text.")
        
        options_sorted = list(options)
        options_sorted.sort()
        
        quiz.append({
            "question": f"Based on the text, what is the description of '{card['front']}'?",
            "options": options_sorted,
            "answer": correct,
            "explanation": f"The document states that '{card['front']}' is: '{correct}'."
        })
    if not quiz:
        quiz = [
            {
                "question": "What is the primary topic of this document?",
                "options": [title, "An unrelated science topic", "An unrelated history topic", "None of the above"],
                "answer": title,
                "explanation": f"The document is titled {title}."
            }
        ]
    return quiz


def _local_fallback_summary(text, title="Document"):
    stopwords = {'the', 'and', 'a', 'of', 'to', 'in', 'is', 'that', 'it', 'for', 'on', 'with', 'as', 'this', 'by', 'an', 'are', 'or', 'at', 'be', 'from', 'this', 'our', 'your', 'will', 'can', 'we', 'you', 'i'}
    words = re.findall(r'\b[a-zA-Z]{4,15}\b', text.lower())
    freq = {}
    for w in words:
        if w not in stopwords:
            freq[w] = freq.get(w, 0) + 1
    sorted_w = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    top_topics = [w[0].capitalize() for w in sorted_w[:5]]
    if not top_topics:
        top_topics = ["General overview"]

    sentences = [s.strip() for s in re.split(r'[.!?\n]', text) if len(s.strip()) > 15]
    concepts = []
    seen_concepts = set()
    for s in sentences:
        if any(kw in s for kw in [" is ", " are ", " refers to ", " means ", " defined as "]) or (s.count(':') == 1 and 20 < len(s) < 180):
            s_clean = re.sub(r'\s+', ' ', s).strip()
            if s_clean.lower() not in seen_concepts and len(s_clean) < 180:
                seen_concepts.add(s_clean.lower())
                concepts.append(s_clean)
                if len(concepts) >= 5:
                    break
    if not concepts:
        concepts = [s[:150] for s in sentences[:3]]

    topics_list = "\n".join(f"* {t}" for t in top_topics)
    concepts_list = "\n".join(f"* **Concept**: {c}" for c in concepts)

    summary_md = f"""## Key Topics
{topics_list}

## Important Concepts
{concepts_list}

## Detailed Summary
*(Local Text Preview - Gemini API is currently unavailable)*

{text[:1200]}...

## Exam Tips
* Review key terms: {', '.join(top_topics[:3])}.
* Analyze core definitions in the text body."""
    return summary_md


def _gemini(prompt):
    if not GEMINI_API_KEY:
        return None
    for model_name in ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-flash-latest"]:
        try:
            print(f"Calling Gemini API using model: {model_name}...")
            model = genai.GenerativeModel(model_name)
            res = model.generate_content(prompt).text
            if res:
                return res
        except Exception as e:
            print(f"Exception calling {model_name}: {repr(e)}")
    return None


def generate_summary(text, title="Document"):
    res = _gemini(f"""You are an expert study assistant.
Analyze the following study material in detail and generate a highly comprehensive, detailed study guide.
Your output must be structured with the following sections:

# Study Guide: {title}

## Executive Summary
Provide a clear, high-level overview summarizing the core focus, context, and key themes of the material (150-250 words).

## Key Topics & Themes
Identify and list the main topics, themes, or modules covered in the material. Under each topic, provide a brief bullet-point summary explaining why it is significant.

## In-Depth Analysis of Core Concepts
For every major concept, theory, formula, process, or event introduced in the text:
* **[Concept Name]**: Provide a comprehensive explanation (at least 3-4 sentences) including its context, how it operates, and any examples or applications mentioned.

## Comprehensive Detailed Summary
Provide an extensive, section-by-section (or chapter-by-chapter) summary. Do not generalize or gloss over details. Explain the core arguments, mechanisms, dates, names, steps, or technical nuances in depth. Make this section extremely detailed and thorough (aim for at least 800 - 1500 words to ensure complete coverage).

## Exam Cheat Sheet & Key Facts
* Provide a list of high-yield facts, rules, equations, formulas, dates, or definitions that are critical to remember for exams.

## Critical Thinking & Practice Questions
* Provide 5 open-ended review questions that test deep conceptual understanding, along with brief guidance on what a complete, high-scoring answer should include.

Study Material:
{text[:120000]}""")
    
    if not res:
        return _local_fallback_summary(text, title)
    return res


def generate_quiz(text, title="Document"):
    raw = _gemini(f"""Create exactly 8 multiple-choice questions from the study material below.

Return ONLY a valid JSON array. No markdown, no code fences, no explanation.

Format:
[
  {{
    "question": "Question text here?",
    "options": ["Option A", "Option B", "Option C", "Option D"],
    "answer": "Option A",
    "explanation": "Brief reason why this is correct."
  }}
]

Study Material:
{text[:60000]}""")
    if not raw:
        return _local_fallback_quiz(text, title)
    try:
        clean = re.sub(r"```json|```", "", raw).strip()
        return json.loads(clean)
    except Exception as e:
        print("Quiz JSON parse error, falling back to local quiz generator:", repr(e))
        return _local_fallback_quiz(text, title)


def generate_flashcards(text, title="Document"):
    raw = _gemini(f"""Create exactly 10 flashcards from the study material below.

Return ONLY a valid JSON array. No markdown, no code fences, no explanation.

Format:
[
  {{
    "front": "Term or concept",
    "back": "Clear definition or explanation"
  }}
]

Study Material:
{text[:60000]}""")
    if not raw:
        return _local_fallback_flashcards(text, title)
    try:
        clean = re.sub(r"```json|```", "", raw).strip()
        return json.loads(clean)
    except Exception as e:
        print("Flashcard JSON parse error, falling back to local flashcard generator:", repr(e))
        return _local_fallback_flashcards(text, title)


@app.before_request
def check_user_exists():
    if request.path.startswith('/static/'):
        return
    if "user_id" in session:
        conn = get_db()
        user = conn.execute("SELECT id FROM users WHERE id=?", (session["user_id"],)).fetchone()
        conn.close()
        if not user:
            session.clear()
            flash("Your session has expired. Please log in again.", "info")
            return redirect(url_for("login"))


# ── Auth routes ───────────────────────────────────────────────────────────────
@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not username or not email or not password:
            flash("All fields are required.", "error")
            return render_template("register.html")

        conn = get_db()
        existing = conn.execute(
            "SELECT id FROM users WHERE username=? OR email=?",
            (username, email)
        ).fetchone()

        if existing:
            conn.close()
            flash("Username or email already taken.", "error")
            return render_template("register.html")

        conn.execute(
            "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
            (username, email, generate_password_hash(password))
        )
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        conn.close()

        session["user_id"]  = user["id"]
        session["username"] = user["username"]
        flash("Welcome to StudyVerse! 🎉", "success")
        return redirect(url_for("dashboard"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        print(request.form)
        identifier = request.form.get("identifier", "").strip()
        password   = request.form.get("password", "")

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE email=? OR username=?",
            (identifier, identifier)
        ).fetchone()
        print("User:", user)

        if user:
         print("Password Match:",
          check_password_hash(user["password"], password))
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"]  = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("dashboard"))

        flash("Invalid username/email or password.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn   = get_db()
    print("SESSION USER ID:", session.get("user_id"))
    user   = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    docs   = conn.execute(
        "SELECT * FROM documents WHERE user_id=? ORDER BY uploaded_at DESC",
        (session["user_id"],)
    ).fetchall()
    print("USER:", user)
    recent = conn.execute("""
        SELECT qs.*, d.title AS doc_title
        FROM quiz_sessions qs
        JOIN documents d ON d.id = qs.doc_id
        WHERE qs.user_id=?
        ORDER BY qs.taken_at DESC LIMIT 5
    """, (session["user_id"],)).fetchall()
    stats  = conn.execute("""
        SELECT COUNT(*) AS total_quizzes,
               AVG(CAST(score AS REAL) / NULLIF(total,0) * 100) AS avg_pct
        FROM quiz_sessions WHERE user_id=?
    """, (session["user_id"],)).fetchone()
    conn.close()

    return render_template("dashboard.html",
        user=user,
        docs=docs,
        recent=recent,
        total_quizzes=stats["total_quizzes"],
        avg_score=round(stats["avg_pct"] or 0, 1),
        level_title=level_title(user["level"]),
        xp_pct=xp_progress_pct(user["xp"], user["level"]),
        xp_next=user["level"] * XP_PER_LEVEL,
    )


# ── Upload ────────────────────────────────────────────────────────────────────
@app.route("/upload", methods=["GET", "POST"])
def upload():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        pdf   = request.files.get("pdf")
        title = request.form.get("title", "").strip()

        if not pdf or not pdf.filename.endswith(".pdf"):
            flash("Please upload a valid PDF file.", "error")
            return render_template("upload.html")

        filename  = secure_filename(pdf.filename)
        safe_name = f"{session['user_id']}_{filename}"
        filepath  = os.path.join(app.config["UPLOAD_FOLDER"], safe_name)
        pdf.save(filepath)

        text, pages = extract_pdf_text(filepath)

        summary    = generate_summary(text, title=title or filename)
        quiz_data  = generate_quiz(text, title=title or filename)
        flash_data = generate_flashcards(text, title=title or filename)

        conn = get_db()
        conn.execute("""
            INSERT INTO documents
                (user_id, title, filename, page_count, summary, flashcards_json, quiz_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            session["user_id"],
            title or filename,
            safe_name,
            pages,
            summary,
            json.dumps(flash_data),
            json.dumps(quiz_data),
        ))
        conn.commit()
        doc_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()

        award_xp(session["user_id"], 50)
        flash(f'"{title or filename}" processed! +50 XP awarded.', "success")
        return redirect(url_for("study", doc_id=doc_id))

    return render_template("upload.html")


# ── Study hub ─────────────────────────────────────────────────────────────────
@app.route("/study/<int:doc_id>")
def study(doc_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    doc  = conn.execute("SELECT * FROM documents WHERE id=? AND user_id=?",
                        (doc_id, session["user_id"])).fetchone()
    conn.close()

    if not doc:
        flash("Document not found.", "error")
        return redirect(url_for("dashboard"))

    cards = json.loads(doc["flashcards_json"] or "[]")
    quiz  = json.loads(doc["quiz_json"] or "[]")
    return render_template("study.html", doc=doc,
                           card_count=len(cards), quiz_count=len(quiz))


# ── Quiz ──────────────────────────────────────────────────────────────────────
@app.route("/quiz/<int:doc_id>", methods=["GET", "POST"])
def quiz(doc_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    doc  = conn.execute("SELECT * FROM documents WHERE id=? AND user_id=?",
                        (doc_id, session["user_id"])).fetchone()
    conn.close()

    if not doc:
        return redirect(url_for("dashboard"))

    questions = json.loads(doc["quiz_json"] or "[]")

    if request.method == "POST":
        data    = request.get_json() or {}
        score   = 0
        results = []

        for i, q in enumerate(questions):
            user_ans    = data.get(str(i), "")
            correct_ans = q.get("answer", "")
            is_correct  = user_ans.strip().lower() == correct_ans.strip().lower()
            if is_correct:
                score += 1
            results.append({
                "question":    q["question"],
                "options":     q.get("options", []),
                "user_answer": user_ans,
                "correct":     correct_ans,
                "is_correct":  is_correct,
                "explanation": q.get("explanation", ""),
            })

        xp_earned = score * 20
        conn = get_db()
        conn.execute("""
            INSERT INTO quiz_sessions (user_id, doc_id, score, total, xp_earned)
            VALUES (?, ?, ?, ?, ?)
        """, (session["user_id"], doc_id, score, len(questions), xp_earned))
        conn.commit()
        conn.close()

        new_xp, new_level = award_xp(session["user_id"], xp_earned)

        return jsonify({
            "score":      score,
            "total":      len(questions),
            "xp_earned":  xp_earned,
            "percentage": int(score / len(questions) * 100) if questions else 0,
            "results":    results,
            "new_xp":     new_xp,
            "new_level":  new_level,
        })

    return render_template("quiz.html", doc=doc, questions=questions)


# ── Flashcards ────────────────────────────────────────────────────────────────
@app.route("/flashcards/<int:doc_id>")
def flashcards(doc_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn  = get_db()
    doc   = conn.execute("SELECT * FROM documents WHERE id=? AND user_id=?",
                         (doc_id, session["user_id"])).fetchone()
    conn.close()

    if not doc:
        return redirect(url_for("dashboard"))

    cards = json.loads(doc["flashcards_json"] or "[]")
    return render_template("flashcards.html", doc=doc, cards=cards)


# ── Summary (legacy route kept so old links still work) ───────────────────────
@app.route("/summary/<int:doc_id>")
def summary(doc_id):
    return redirect(url_for("study", doc_id=doc_id))


# ── Leaderboard ───────────────────────────────────────────────────────────────
@app.route("/leaderboard")
def leaderboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn  = get_db()
    users = conn.execute(
        "SELECT id, username, xp, level FROM users ORDER BY xp DESC LIMIT 10"
    ).fetchall()
    conn.close()

    return render_template("leaderboard.html",
                           users=users,
                           current_user_id=session["user_id"],
                           level_title=level_title)


# ── Delete document ───────────────────────────────────────────────────────────
@app.route("/delete/<int:doc_id>", methods=["POST"])
def delete_doc(doc_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    doc  = conn.execute("SELECT * FROM documents WHERE id=? AND user_id=?",
                        (doc_id, session["user_id"])).fetchone()
    if doc:
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], doc["filename"])
        if os.path.exists(filepath):
            os.remove(filepath)
        conn.execute("DELETE FROM quiz_sessions WHERE doc_id=?", (doc_id,))
        conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        conn.commit()
        flash("Document deleted.", "success")
    conn.close()
    return redirect(url_for("dashboard"))


@app.route("/debug")
def debug_diagnostics():
    import traceback
    info = {
        "status": "healthy",
        "database_type": "PostgreSQL" if db_adapter.is_pg else "SQLite",
        "database_url_configured": bool(DATABASE_URL),
        "database_url_masked": re.sub(r'://([^:]+):([^@]+)@', r'://\1:****@', DATABASE_URL) if DATABASE_URL else "",
        "gemini_api_key_configured": bool(GEMINI_API_KEY),
        "secret_key_configured": bool(os.getenv("SECRET_KEY")),
        "tables": [],
        "connection_error": None
    }
    try:
        conn = get_db()
        if db_adapter.is_pg:
            cur = conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            info["tables"] = [row["table_name"] for row in cur.fetchall()]
        else:
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            info["tables"] = [row[0] for row in cur.fetchall()]
        conn.close()
    except Exception as e:
        info["status"] = "database_connection_failed"
        info["connection_error"] = traceback.format_exc()
        
    return jsonify(info)


# ── Jinja helpers ─────────────────────────────────────────────────────────────
@app.template_filter("pretty_date")
def pretty_date(dt_str):
    try:
        return datetime.fromisoformat(dt_str).strftime("%b %d, %Y")
    except Exception:
        return dt_str

@app.errorhandler(Exception)
def handle_exception(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e

    import traceback
    tb = traceback.format_exc()
    if request.path.startswith('/api/') or request.headers.get('Accept') == 'application/json':
        return jsonify({"error": str(e), "traceback": tb}), 500
    
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Application Error - StudyVerse</title>
        <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;600;700&display=swap" rel="stylesheet">
        <style>
            body {{
                background: radial-gradient(circle at 50% 50%, #1a1a2e 0%, #0f0f1b 100%);
                color: #e2e8f0;
                font-family: 'Plus Jakarta Sans', sans-serif;
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                margin: 0;
                padding: 20px;
                box-sizing: border-box;
            }}
            .error-container {{
                background: rgba(30, 41, 59, 0.45);
                backdrop-filter: blur(16px);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 20px;
                padding: 40px;
                max-width: 800px;
                width: 100%;
                box-shadow: 0 20px 50px rgba(0, 0, 0, 0.3);
            }}
            h1 {{
                font-size: 2rem;
                font-weight: 700;
                color: #ff5555;
                margin-top: 0;
                margin-bottom: 10px;
            }}
            p {{
                color: #94a3b8;
                font-size: 1.1rem;
                line-height: 1.6;
                margin-bottom: 25px;
            }}
            .traceback-container {{
                background: rgba(15, 23, 42, 0.6);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 12px;
                padding: 20px;
                overflow-x: auto;
                font-family: 'Courier New', Courier, monospace;
                font-size: 0.9rem;
                color: #38bdf8;
                max-height: 400px;
                text-align: left;
            }}
            .btn {{
                display: inline-block;
                background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
                color: white;
                text-decoration: none;
                padding: 12px 24px;
                border-radius: 10px;
                font-weight: 600;
                margin-top: 20px;
                transition: transform 0.2s, box-shadow 0.2s;
            }}
            .btn:hover {{
                transform: translateY(-2px);
                box-shadow: 0 10px 20px rgba(99, 102, 241, 0.3);
            }}
        </style>
    </head>
    <body>
        <div class="error-container">
            <h1>Something Went Wrong 🚀</h1>
            <p>An unexpected error occurred in the application. Below is the debug traceback to help you diagnose the issue:</p>
            <div class="traceback-container">
                <pre style="margin:0;">{tb}</pre>
            </div>
            <a href="/" class="btn">Return to Home</a>
        </div>
    </body>
    </html>
    """, 500


if __name__ == "__main__":
    app.run(debug=True, port=5001)