# Mini CRM (Flask + SQLite)

Fonctionnalités de base :
- Connexion / déconnexion (sessions)
- Rôles : **admin** et **user**
- **User** : "Créer un dossier" + "Mes dossiers"
- **Admin** : liste de **tous les dossiers**, gestion des **utilisateurs** (création)
- SQLite inclus (fichier `crm.db` créé automatiquement)

## Démarrage (local)
1) Créez un environnement Python 3.10+
```
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```
2) Lancez le serveur :
```
export FLASK_APP=app.py
python app.py
```
3) Ouvrez http://localhost:5000

### Identifiants admin par défaut
- Email : `admin@example.com`
- Mot de passe : `admin123`

Vous pouvez personnaliser via des variables d'env avant le lancement :
```
export ADMIN_EMAIL="votre_admin@exemple.com"
export ADMIN_PASSWORD="motdepassefort"
export FLASK_SECRET_KEY="une_chaine_ultra_secrete"
```

## Déploiement
- **Railway/Render/Dokku/VM** : OK (SQLite fichier)
- **Heroku** : préférez un add-on Postgres si vous scalez (adapter le code)
- Pour un usage simple et interne, SQLite convient très bien.

## Étapes suivantes
- Ajout de champs custom sur un dossier
- Upload de fichiers dans un dossier
- Droits fins (lecture/écriture par utilisateur)
- Recherche / filtres
- Export CSV/PDF
