from flask import Flask, render_template, request, redirect, url_for, session, flash, g
import sqlite3, os, datetime
from passlib.hash import pbkdf2_sha256

DB_PATH = os.path.join(os.path.dirname(__file__), "crm.db")
SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-" + os.urandom(16).hex())

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','user')),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS dossiers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            owner_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(owner_id) REFERENCES users(id)
        );
        """
    )
    db.commit()

def ensure_admin():
    # Create default admin if none exists
    db = get_db()
    cur = db.execute("SELECT id FROM users WHERE role='admin' LIMIT 1")
    if not cur.fetchone():
        # Default credentials
        email = os.environ.get("ADMIN_EMAIL", "admin@example.com")
        password = os.environ.get("ADMIN_PASSWORD", "admin123")
        name = "Admin"
        pwd_hash = pbkdf2_sha256.hash(password)
        db.execute(
            "INSERT INTO users (email, name, password_hash, role, created_at) VALUES (?,?,?,?,?)",
            (email, name, pwd_hash, "admin", datetime.datetime.utcnow().isoformat())
        )
        db.commit()
        print(f"[INIT] Admin créé: {email} / {password}")

@app.before_first_request
def startup():
    init_db()
    ensure_admin()

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    db = get_db()
    u = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    return u

def login_required(view):
    from functools import wraps
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            flash("Veuillez vous connecter.", "warn")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    from functools import wraps
    @wraps(view)
    def wrapped(*args, **kwargs):
        u = current_user()
        if not u or u["role"] != "admin":
            flash("Accès administrateur requis.", "error")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped

@app.route("/")
def home():
    if current_user():
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        db = get_db()
        u = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if u and pbkdf2_sha256.verify(password, u["password_hash"]):
            session["user_id"] = u["id"]
            flash("Bienvenue !", "ok")
            return redirect(url_for("dashboard"))
        flash("Identifiants invalides.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Déconnecté(e).", "ok")
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    u = current_user()
    return render_template("dashboard.html", user=u)

# --- Users (admin) ---
@app.route("/admin/users", methods=["GET","POST"])
@admin_required
def admin_users():
    db = get_db()
    if request.method == "POST":
        # create user
        email = request.form["email"].strip().lower()
        name = request.form["name"].strip()
        role = request.form.get("role","user")
        password = request.form["password"]
        if not email or not name or not password:
            flash("Champs requis manquants.", "error")
        else:
            try:
                db.execute(
                    "INSERT INTO users (email, name, password_hash, role, created_at) VALUES (?,?,?,?,?)",
                    (email, name, pbkdf2_sha256.hash(password), role, datetime.datetime.utcnow().isoformat())
                )
                db.commit()
                flash("Utilisateur créé.", "ok")
            except sqlite3.IntegrityError:
                flash("Email déjà utilisé.", "error")
    users = db.execute("SELECT id, email, name, role, created_at FROM users ORDER BY created_at DESC").fetchall()
    return render_template("admin_users.html", users=users)

# --- Dossiers ---
@app.route("/dossiers")
@login_required
def my_dossiers():
    u = current_user()
    db = get_db()
    ds = db.execute("SELECT * FROM dossiers WHERE owner_id=? ORDER BY created_at DESC", (u["id"],)).fetchall()
    return render_template("dossiers_list.html", dossiers=ds, title_page="Mes dossiers")

@app.route("/dossiers/new", methods=["GET","POST"])
@login_required
def create_dossier():
    u = current_user()
    if request.method == "POST":
        title = request.form["title"].strip()
        description = request.form.get("description","").strip()
        if not title:
            flash("Le titre est requis.", "error")
        else:
            db = get_db()
            db.execute(
                "INSERT INTO dossiers (title, description, owner_id, created_at) VALUES (?,?,?,?)",
                (title, description, u["id"], datetime.datetime.utcnow().isoformat())
            )
            db.commit()
            flash("Dossier créé.", "ok")
            return redirect(url_for("my_dossiers"))
    return render_template("dossier_create.html")

# --- Admin: liste de tous les dossiers ---
@app.route("/admin/dossiers")
@admin_required
def admin_dossiers():
    db = get_db()
    ds = db.execute("""
        SELECT d.id, d.title, d.description, d.created_at, u.name as owner_name, u.email as owner_email
        FROM dossiers d
        JOIN users u ON u.id = d.owner_id
        ORDER BY d.created_at DESC
    """).fetchall()
    return render_template("admin_dossiers.html", dossiers=ds)

if __name__ == "__main__":
    # Local dev server
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
