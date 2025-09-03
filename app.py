
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
            company_name TEXT,
            siret TEXT,
            signer_first_name TEXT,
            signer_last_name TEXT,
            signer_role TEXT,
            signer_phone TEXT,
            signer_email TEXT,
            billing_address TEXT,
            billing_zip TEXT,
            billing_city TEXT,
            shipping_address TEXT,
            shipping_zip TEXT,
            shipping_city TEXT,
            FOREIGN KEY(owner_id) REFERENCES users(id)
        );
        """
    )
    db.commit()

def ensure_columns():
    db = get_db()
    cur = db.execute("PRAGMA table_info(dossiers)")
    cols = {r["name"] for r in cur.fetchall()}
    wanted = [
        ("company_name", "TEXT"),
        ("siret", "TEXT"),
        ("signer_first_name", "TEXT"),
        ("signer_last_name", "TEXT"),
        ("signer_role", "TEXT"),
        ("signer_phone", "TEXT"),
        ("signer_email", "TEXT"),
        ("billing_address", "TEXT"),
        ("billing_zip", "TEXT"),
        ("billing_city", "TEXT"),
        ("shipping_address", "TEXT"),
        ("shipping_zip", "TEXT"),
        ("shipping_city", "TEXT"),
    ]
    for name, typ in wanted:
        if name not in cols:
            db.execute(f"ALTER TABLE dossiers ADD COLUMN {name} {typ}")
    db.commit()

def ensure_admin():
    db = get_db()
    cur = db.execute("SELECT id FROM users WHERE role='admin' LIMIT 1")
    if not cur.fetchone():
        email = os.environ.get("ADMIN_EMAIL", "admin@example.com")
        password = os.environ.get("ADMIN_PASSWORD", "admin123")
        name = "Admin"
        pwd = pbkdf2_sha256.hash(password)
        db.execute(
            "INSERT INTO users (email, name, password_hash, role, created_at) VALUES (?,?,?,?,?)",
            (email, name, pwd, "admin", datetime.datetime.utcnow().isoformat())
        )
        db.commit()
        print(f"[INIT] Admin créé: {email} / {password}")

@app.before_request
def startup():
    if not hasattr(app, "db_initialized"):
        init_db()
        ensure_columns()
        ensure_admin()
        app.db_initialized = True

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    db = get_db()
    return db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()

@app.context_processor
def inject_user():
    return {"user": current_user()}

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

@app.route("/admin/users", methods=["GET","POST"])
@admin_required
def admin_users():
    db = get_db()
    if request.method == "POST":
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

@app.route("/dossiers")
@login_required
def my_dossiers():
    u = current_user()
    db = get_db()
    ds = db.execute("SELECT * FROM dossiers WHERE owner_id=? ORDER BY created_at DESC", (u['id'],)).fetchall()
    return render_template("dossiers_list.html", dossiers=ds, title_page="Mes dossiers")

@app.route("/dossiers/new", methods=["GET","POST"])
@login_required
def create_dossier():
    u = current_user()
    if request.method == "POST":
        title = request.form["title"].strip()
        description = request.form.get("description","").strip()
        company_name = request.form.get("company_name","").strip()
        siret = request.form.get("siret","").strip()
        signer_first_name = request.form.get("signer_first_name","").strip()
        signer_last_name = request.form.get("signer_last_name","").strip()
        signer_role = request.form.get("signer_role","").strip()
        signer_phone = request.form.get("signer_phone","").strip()
        signer_email = request.form.get("signer_email","").strip()
        billing_address = request.form.get("billing_address","").strip()
        billing_zip = request.form.get("billing_zip","").strip()
        billing_city = request.form.get("billing_city","").strip()
        shipping_address = request.form.get("shipping_address","").strip()
        shipping_zip = request.form.get("shipping_zip","").strip()
        shipping_city = request.form.get("shipping_city","").strip()

        if not title:
            flash("Le titre est requis.", "error")
        else:
            db = get_db()
            db.execute(
                """INSERT INTO dossiers
                   (title, description, owner_id, created_at,
                    company_name, siret,
                    signer_first_name, signer_last_name, signer_role, signer_phone, signer_email,
                    billing_address, billing_zip, billing_city,
                    shipping_address, shipping_zip, shipping_city)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (title, description, u["id"], datetime.datetime.utcnow().isoformat(),
                 company_name, siret,
                 signer_first_name, signer_last_name, signer_role, signer_phone, signer_email,
                 billing_address, billing_zip, billing_city,
                 shipping_address, shipping_zip, shipping_city)
            )
            db.commit()
            flash("Dossier créé.", "ok")
            return redirect(url_for("my_dossiers"))
    return render_template("dossier_create.html")

@app.route("/admin/dossiers")
@admin_required
def admin_dossiers():
    db = get_db()
    ds = db.execute(
        """
        SELECT d.id, d.title, d.description, d.created_at,
               d.company_name, d.siret,
               d.signer_first_name, d.signer_last_name, d.signer_role, d.signer_phone, d.signer_email,
               d.billing_address, d.billing_zip, d.billing_city,
               d.shipping_address, d.shipping_zip, d.shipping_city,
               u.name as owner_name, u.email as owner_email
        FROM dossiers d
        JOIN users u ON u.id = d.owner_id
        ORDER BY d.created_at DESC
        """
    ).fetchall()
    return render_template("admin_dossiers.html", dossiers=ds)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
