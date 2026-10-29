from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = "change-this-secret-key-before-publishing"

DATABASE = "tasks.db"


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            due_date TEXT DEFAULT '',
            completed INTEGER DEFAULT 0,
            user_id INTEGER
        )
    """)

    # Добавляем user_id, если таблица задач уже существовала
    columns = [row["name"] for row in cursor.execute(
        "PRAGMA table_info(tasks)"
    ).fetchall()]

    if "user_id" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN user_id INTEGER")

    conn.commit()
    conn.close()


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper


@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("index"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if len(username) < 3:
            flash("Логин должен содержать минимум 3 символа.")
            return render_template("register.html")

        if len(password) < 6:
            flash("Пароль должен содержать минимум 6 символов.")
            return render_template("register.html")

        conn = get_db()

        try:
            conn.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, generate_password_hash(password))
            )
            conn.commit()

            user = conn.execute(
                "SELECT id FROM users WHERE username = ?",
                (username,)
            ).fetchone()

            session.clear()
            session["user_id"] = user["id"]
            session["username"] = username

            return redirect(url_for("index"))

        except sqlite3.IntegrityError:
            flash("Такой логин уже занят. Выбери другой.")
        finally:
            conn.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("index"))

        flash("Неверный логин или пароль.")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/tasks")
@login_required
def index():
    conn = get_db()

    tasks = conn.execute("""
        SELECT * FROM tasks
        WHERE user_id = ?
        ORDER BY completed ASC, due_date ASC, id DESC
    """, (session["user_id"],)).fetchall()

    total = len(tasks)
    completed = sum(task["completed"] for task in tasks)
    pending = total - completed

    conn.close()

    return render_template(
        "index.html",
        tasks=tasks,
        total=total,
        completed=completed,
        pending=pending,
        username=session.get("username")
    )


@app.route("/add", methods=["POST"])
@login_required
def add_task():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    due_date = request.form.get("due_date", "").strip()

    if title:
        conn = get_db()
        conn.execute("""
            INSERT INTO tasks (title, description, due_date, completed, user_id)
            VALUES (?, ?, ?, 0, ?)
        """, (title, description, due_date, session["user_id"]))
        conn.commit()
        conn.close()

    return redirect(url_for("index"))


@app.route("/complete/<int:task_id>", methods=["POST"])
@login_required
def complete_task(task_id):
    conn = get_db()
    conn.execute("""
        UPDATE tasks SET completed = CASE
            WHEN completed = 0 THEN 1 ELSE 0 END
        WHERE id = ? AND user_id = ?
    """, (task_id, session["user_id"]))
    conn.commit()
    conn.close()

    return redirect(url_for("index"))


@app.route("/delete/<int:task_id>", methods=["POST"])
@login_required
def delete_task(task_id):
    conn = get_db()
    conn.execute(
        "DELETE FROM tasks WHERE id = ? AND user_id = ?",
        (task_id, session["user_id"])
    )
    conn.commit()
    conn.close()

    return redirect(url_for("index"))


@app.route("/edit/<int:task_id>", methods=["GET", "POST"])
@login_required
def edit_task(task_id):
    conn = get_db()

    task = conn.execute("""
        SELECT * FROM tasks WHERE id = ? AND user_id = ?
    """, (task_id, session["user_id"])).fetchone()

    if task is None:
        conn.close()
        flash("Задача не найдена.")
        return redirect(url_for("index"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        due_date = request.form.get("due_date", "").strip()

        if title:
            conn.execute("""
                UPDATE tasks
                SET title = ?, description = ?, due_date = ?
                WHERE id = ? AND user_id = ?
            """, (
                title, description, due_date,
                task_id, session["user_id"]
            ))
            conn.commit()
            conn.close()
            return redirect(url_for("index"))

        flash("Название задачи не может быть пустым.")

    conn.close()
    return render_template("edit.html", task=task)


init_db()

if __name__ == "__main__":
    app.run(debug=True)
    
