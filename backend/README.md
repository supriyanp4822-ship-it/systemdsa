# Hospital Queue Management System - Backend API & App

This folder contains the Flask backend application, SQLAlchemy database models, AI wait time prediction module, and business logic blueprints.

## Directory Structure

```
backend/
├── app.py                   # Application Factory & Database Seeding
├── config.py                # Environment Configuration
├── wsgi.py                  # WSGI Server Entry Point
├── extensions.py            # Extensions (SQLAlchemy, LoginManager)
├── models.py                # Database Models
├── predictor.py             # Machine Learning Wait Time Predictor
├── train_model.py           # ML Model Trainer
├── gunicorn.conf.py         # Gunicorn Configuration
├── Procfile                 # Cloud Deployment Procfile
├── Dockerfile               # Production Docker Container Setup
├── requirements.txt         # Python Dependencies
├── routes/                  # Modular Blueprints (auth, queue, admin, payments, etc.)
└── services/                # Background Services (UPI, Notifications)
```

## Running the Backend

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
python wsgi.py
```
