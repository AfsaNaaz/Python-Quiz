from flask import Flask, render_template, request, redirect, url_for, session, flash, g
import os, time, sqlite3, pathlib

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-only-afsa")

PASS_MARK = 5
QUIZ_DURATION = 600  # 10 minutes

# --- Data dir (Render Free -> /tmp). Auto-fallback if not writable. ---
DATA_DIR = os.getenv("DATA_DIR", ".")
try:
    p = pathlib.Path(DATA_DIR)
    p.mkdir(parents=True, exist_ok=True)
    test_file = p / ".write_test"
    with open(test_file, "w") as f:
        f.write("ok")
    test_file.unlink(missing_ok=True)
except Exception:
    DATA_DIR = "/tmp"
    pathlib.Path(DATA_DIR).mkdir(parents=True, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "quiz.db")

# ---------------- Questions ----------------
QUESTIONS = [
    {"id": 1, "text": "Which keyword is used to define a function in Python?", "options": ["def", "function", "func", "define"], "answer": 0},
    {"id": 2, "text": "Which Python data type is immutable?", "options": ["list", "set", "tuple", "dict"], "answer": 2},
    {"id": 3, "text": "Which of these is a valid Python list literal?", "options": ["(1, 2, 3)", "[1, 2, 3]", "{1, 2, 3}", "<1, 2, 3>"], "answer": 1},
    {"id": 4, "text": "Which operator performs floor division in Python?", "options": ["/", "//", "%", "**"], "answer": 1},
    {"id": 5, "text": "What is the result of len('hello')?", "options": ["4", "5", "6", "Error"], "answer": 1},
    {"id": 6, "text": "How do you import the math module?", "options": ["use math", "import(math)", "import math", "math import"], "answer": 2},
    {"id": 7, "text": "Which literal creates a set in Python?", "options": ["{}", "{1, 2, 3}", "[]", "()"], "answer": 1},
    {"id": 8, "text": "The index of the first element in a Python list is:", "options": ["1", "0", "-1", "Depends"], "answer": 1},
    {"id": 9, "text": "Which statement handles exceptions in Python?", "options": ["catch", "try...except", "error...handle", "guard"], "answer": 1},
    {"id": 10, "text": "Which of these is a Boolean value in Python?", "options": ["TRUE", "True", "true", "Yes"], "answer": 1},
]

# ---------------- SQLite helpers ----------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, check_same_thread=False)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS users(
            username   TEXT PRIMARY KEY,
            password   TEXT NOT NULL,
            status     TEXT NOT NULL DEFAULT 'new',   -- 'new' | 'failed' | 'passed'
            last_score INTEGER
        )
    """)
    db.commit()

def get_user(username):
    cur = get_db().execute("SELECT * FROM users WHERE username = ?", (username,))
    return cur.fetchone()

def create_user(username, password):
    db = get_db()
    db.execute("INSERT INTO users(username, password, status, last_score) VALUES (?, ?, 'new', NULL)", (username, password))
    db.commit()

def update_user_status(username, status, last_score):
    db = get_db()
    db.execute("UPDATE users SET status=?, last_score=? WHERE username=?", (status, last_score, username))
    db.commit()

# Expose user to templates
@app.context_processor
def inject_user():
    return {"user": session.get("user")}

# ---------------- Routes ----------------
@app.route("/")
def home():
    init_db()
    username = session.get("user")
    status = "new"
    if username:
        row = get_user(username)
        if row:
            status = row["status"]
    return render_template("index.html", total=len(QUESTIONS), status=status)

@app.route("/register", methods=["GET", "POST"])
def register():
    init_db()
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        password = (request.form.get("password") or "").strip()
        if not username or not password:
            flash("Username and password are required.", "error")
            return redirect(url_for("register"))
        if get_user(username):
            flash("Username already exists!", "error")
            return redirect(url_for("register"))
        create_user(username, password)
        flash("Registered successfully! Please login.", "ok")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    init_db()
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        password = (request.form.get("password") or "").strip()
        row = get_user(username)
        if row and row["password"] == password:
            session["user"] = username
            return redirect(url_for("home"))
        flash("Invalid username or password!", "error")
        return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("You have been logged out.", "ok")
    return redirect(url_for("home"))

@app.route("/quiz")
def quiz():
    init_db()
    username = session.get("user")
    if not username:
        flash("Please login to take the quiz.", "error")
        return redirect(url_for("login"))
    row = get_user(username)
    if not row:
        flash("Please register first.", "error")
        return redirect(url_for("register"))
    if row["status"] == "passed":
        return redirect(url_for("home"))

    session["start_time"] = int(time.time())
    return render_template("quiz.html", questions=QUESTIONS, duration=QUIZ_DURATION)

@app.route("/submit", methods=["POST"])
def submit():
    init_db()
    username = session.get("user")
    if not username:
        return redirect(url_for("login"))
    row = get_user(username)
    if not row:
        return redirect(url_for("register"))
    if row["status"] == "passed":
        return redirect(url_for("home"))

    score = 0
    submitted = {}
    for q in QUESTIONS:
        key = f"q{q['id']}"
        selected = request.form.get(key)
        if selected is not None:
            idx = int(selected)
            submitted[q["id"]] = idx
            if idx == q["answer"]:
                score += 1
        else:
            submitted[q["id"]] = None

    passed = score >= PASS_MARK
    update_user_status(username, "passed" if passed else "failed", score)

    return render_template(
        "result.html",
        questions=QUESTIONS,
        submitted=submitted,
        score=score,
        total=len(QUESTIONS),
        pass_mark=PASS_MARK,
        passed=passed
    )

@app.route("/restart")
def restart():
    init_db()
    username = session.get("user")
    if not username:
        return redirect(url_for("login"))
    row = get_user(username)
    if not row:
        return redirect(url_for("register"))
    if row["status"] == "passed":
        return redirect(url_for("home"))
    update_user_status(username, "new", row["last_score"])
    return redirect(url_for("quiz"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False)
