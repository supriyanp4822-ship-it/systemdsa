# Hospital Queue Management System

A Flask and Machine Learning based Hospital Queue Management System separated into dedicated **Backend** and **Frontend** services.

---

## 📁 Repository Structure

```
HospitalQueueManagementSystem/
├── backend/                  # Flask REST API, ML Engine & Database
│   ├── app.py                # Application Factory & Database Seeding
│   ├── config.py             # Configuration (Dev/Prod)
│   ├── wsgi.py               # WSGI Entry point
│   ├── models.py             # SQLAlchemy Database Models
│   ├── predictor.py          # ML Prediction Engine
│   ├── routes/               # API & Feature Blueprints
│   ├── services/             # UPI & Notification Services
│   ├── Dockerfile            # Backend Docker Setup
│   ├── Procfile              # PaaS Deployment Config
│   └── requirements.txt      # Python Dependencies
├── frontend/                 # UI Templates & Static Web Assets
│   ├── templates/            # Jinja2 HTML Templates
│   ├── static/               # CSS, JavaScript & Media Files
│   ├── nginx.conf            # Nginx Reverse Proxy Config
│   └── Dockerfile            # Frontend Nginx Docker Setup
├── docker-compose.yml        # Orchestration for Full Stack
└── README.md
```

---

## 🚀 Quick Start (Docker)

To launch the entire stack (Backend + Frontend) with Docker Compose:

```bash
docker-compose up --build -d
```

- **Frontend**: http://localhost
- **Backend API**: http://localhost:5000

---

## 🛠️ Local Development (Without Docker)

### 1. Run Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
python wsgi.py
```

The Flask app will automatically serve the templates from `frontend/templates` and static files from `frontend/static` in development mode.

---

## ☁️ Separate Cloud Deployment

### Deploying Backend (e.g. Render, Railway, Heroku, AWS App Runner)
- Root directory: `backend`
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn --config gunicorn.conf.py wsgi:app`

### Deploying Frontend (e.g. Vercel, Netlify, Nginx, Cloudflare Pages)
- Root directory: `frontend`
- Configure reverse proxy or set backend API endpoint URL for API calls.
