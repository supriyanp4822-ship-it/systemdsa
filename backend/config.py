import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-12345-change-in-production')

    # MongoDB Atlas Database Configuration
    MONGODB_URI = os.environ.get('MONGODB_URI', '')
    MONGODB_DATABASE = os.environ.get('MONGODB_DATABASE', 'hospital_queue')

    # ML model files paths
    MODEL_PATH = os.environ.get('MODEL_PATH', str(BASE_DIR / 'model.joblib'))
    FEATURE_ENCODER_PATH = os.environ.get('FEATURE_ENCODER_PATH', str(BASE_DIR / 'feature_encoder.joblib'))
    SPECIALTY_ENCODER_PATH = os.environ.get('SPECIALTY_ENCODER_PATH', str(BASE_DIR / 'specialty_encoder.joblib'))

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False
    @classmethod
    def init_app(cls, app):
        if app.config.get('SECRET_KEY') == 'dev-secret-key-12345-change-in-production':
            import warnings
            warnings.warn("SECRET_KEY is using default dev value in production mode! Set SECRET_KEY in environment variables.", UserWarning)

class TestingConfig(Config):
    TESTING = True
    MONGODB_DATABASE = 'hospital_queue_test'

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
