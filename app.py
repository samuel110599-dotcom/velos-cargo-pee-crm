
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

# --- AJOUT: auto-remplissage via API publique (gratuite, sans clé) ---
import requests
from flask import jsonify, request

@app.route("/api/lookup_siret")
def lookup_siret():
    siret = (request.args.get("siret") or "").replace(" ", "")
    if not siret or len(siret) < 9:
        return jsonify({"ok": False, "error": "SIRET invalide"}), 400

    q = siret  # l'API accepte SIRET ou SIREN dans q
    try:
        r = requests.get(
            "https://recherche-entreprises.api.gouv.fr/search",
            params={"q": q, "page": 1, "per_page": 1},
            timeout=10
        )
        r.raise_for_status()
        data = r.json()
        results = (data.get("results") or [])
        if not results:
            return jsonify({"ok": False, "error": "Entreprise introuvable"}), 404
        ent = results[0]
    except Exception as e:
        return jsonify({"ok": False, "error": f"API publique indisponible: {e}"}), 502

    # Nom entreprise
    company_name = ent.get("nom_raison_sociale") or ent.get("nom_complet") or ""

    # Dirigeants (souvent dispo via RNE)
    reps = ent.get("representants") or []
    best = None
    for kw in ("président", "president", "gérant", "gerant", "dirigeant"):
        best = next((d for d in reps if kw in (d.get("role","").lower())), None)
        if best: break
    if not best and reps:
        best = reps[0]

    signer_first_name = (best or {}).get("prenom") or ""
    signer_last_name  = (best or {}).get("nom") or ""
    signer_role       = (best or {}).get("role") or ""

    # Adresse siège si dispo
    siege = ent.get("etablissement_siege") or {}
    adr = siege.get("adresse") or {}
    billing_address = " ".join(filter(None, [
        adr.get("numero_voie"), adr.get("type_voie"), adr.get("nom_voie")
    ])) or (adr.get("libelle_commune") or "")
    billing_zip = adr.get("code_postal") or ""
    billing_city = adr.get("libelle_commune") or ""

    return jsonify({
        "ok": True,
        "company_name": company_name,
        "signer_first_name": signer_first_name,
        "signer_last_name": signer_last_name,
        "signer_role": signer_role,
        "billing_address": billing_address,
        "billing_zip": billing_zip,
        "billing_city": billing_city,
    })
# --- FIN AJOUT ---

