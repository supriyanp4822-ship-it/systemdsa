import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-12345-change-in-production')

    # Handle PostgreSQL URL format compatibility (Render/Heroku use postgres://)
    db_url = os.environ.get('DATABASE_URL')
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    SQLALCHEMY_DATABASE_URI = db_url or f"sqlite:///{BASE_DIR / 'instance' / 'hospital.db'}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ML model files paths
    MODEL_PATH = os.environ.get('MODEL_PATH', str(BASE_DIR / 'model.joblib'))
    FEATURE_ENCODER_PATH = os.environ.get('FEATURE_ENCODER_PATH', str(BASE_DIR / 'feature_encoder.joblib'))
    SPECIALTY_ENCODER_PATH = os.environ.get('SPECIALTY_ENCODER_PATH', str(BASE_DIR / 'specialty_encoder.joblib'))

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False
    # Ensure a strong secret key in production
    @classmethod
    def init_app(cls, app):
        if app.config['SECRET_KEY'] == 'dev-secret-key-12345-change-in-production':
            import warnings
            warnings.warn("SECRET_KEY is using default dev value in production mode! Set SECRET_KEY in environment variables.", UserWarning)

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
