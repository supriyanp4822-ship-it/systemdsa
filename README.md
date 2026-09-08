# Hospital Queue Management System

Minimal scaffold for a Flask-based Hospital Queue Management System.

Setup

```bash
python -m venv .venv
source .venv/bin/activate  # or `.venv\Scripts\activate` on Windows
pip install -r requirements.txt
export FLASK_APP=app.py
flask run
```

Files added by scaffold:
- `app.py` — Flask app factory
- `routes/` — example blueprints for auth, appointments, dashboard, admin, queue
- `templates/` — basic HTML pages
