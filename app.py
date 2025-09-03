
import os, sqlite3
from flask import Flask, render_template, request, redirect, url_for, g

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")

DB_FILE = os.path.join(os.path.dirname(__file__), "crm.db")

def get_db():
    db = getattr(g, "_db", None)
    if db is None:
        db = g._db = sqlite3.connect(DB_FILE)
    return db

@app.teardown_appcontext
def close_db(exception):
    db = getattr(g, "_db", None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS dossiers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            shipping_city TEXT
        )
    """)
    db.commit()

@app.before_request
def before_request():
    init_db()

@app.route("/")
def dashboard():
    return render_template("dashboard.html")

@app.route("/dossiers")
def dossiers():
    cur = get_db().execute("SELECT id, company_name, siret FROM dossiers ORDER BY id DESC")
    return render_template("dossiers_list.html", dossiers=cur.fetchall())

@app.route("/dossier/create", methods=["GET","POST"])
def create_dossier():
    if request.method == "POST":
        f = request.form
        get_db().execute(
            """INSERT INTO dossiers(
                company_name, siret,
                signer_first_name, signer_last_name, signer_role, signer_phone, signer_email,
                billing_address, billing_zip, billing_city,
                shipping_address, shipping_zip, shipping_city
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                f.get("company_name"), f.get("siret"),
                f.get("signer_first_name"), f.get("signer_last_name"), f.get("signer_role"),
                f.get("signer_phone"), f.get("signer_email"),
                f.get("billing_address"), f.get("billing_zip"), f.get("billing_city"),
                f.get("shipping_address"), f.get("shipping_zip"), f.get("shipping_city"),
            )
        )
        get_db().commit()
        return redirect(url_for("dossiers"))
    return render_template("dossier_create.html")

if __name__ == "__main__":
    app.run(debug=True)

# --- AJOUT: auto-remplissage via Pappers ---
import os, requests
from flask import jsonify, request

PAPPERS_API_KEY = os.environ.get("PAPPERS_API_KEY")  # ta clé à mettre dans Render

@app.route("/api/lookup_siret")
def lookup_siret():
    siret = (request.args.get("siret") or "").replace(" ", "")
    if not siret or len(siret) < 9:
        return jsonify({"ok": False, "error": "SIRET invalide"}), 400

    siren = siret[:9]  # Pappers fonctionne avec le SIREN (9 chiffres)

    try:
        r = requests.get(
            "https://api.pappers.fr/v2/entreprise",
            params={"api_token": PAPPERS_API_KEY, "siren": siren},
            timeout=10
        )
        data = r.json()
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502

    # Récupération infos
    company_name = data.get("denomination") or ""
    reps = data.get("representants") or []
    dirigeant = reps[0] if reps else {}

    return jsonify({
        "ok": True,
        "company_name": company_name,
        "signer_first_name": dirigeant.get("prenom",""),
        "signer_last_name": dirigeant.get("nom",""),
        "signer_role": dirigeant.get("fonction",""),
    })
# --- FIN AJOUT ---
