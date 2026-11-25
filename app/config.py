from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        # Sin DATABASE_URL se usa SQLite local para que el sistema funcione de inmediato.
        (BASE_DIR / "instance").mkdir(exist_ok=True)
        return f"sqlite:///{BASE_DIR / 'instance' / 'maza_inventario.db'}"
    # Render entrega URLs con el prefijo postgres://, SQLAlchemy necesita postgresql+psycopg2://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    return url


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "cambia-esta-clave-en-produccion")
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    WTF_CSRF_TIME_LIMIT = None
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(16 * 1024 * 1024)))

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE

    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
    ADMIN_FULL_NAME = os.getenv("ADMIN_FULL_NAME", "Administrador MAZA")

    # Parámetros del negocio
    EMPRESA_NOMBRE = os.getenv("EMPRESA_NOMBRE", "MAZA Autorepuestos")
    WHATSAPP_PEDIDOS = os.getenv("WHATSAPP_PEDIDOS", "72201855")
    DIAS_ANALISIS_ABC = int(os.getenv("DIAS_ANALISIS_ABC", "180"))
    DIAS_SIN_ROTACION = int(os.getenv("DIAS_SIN_ROTACION", "180"))
    DIAS_CLIENTE_INACTIVO = int(os.getenv("DIAS_CLIENTE_INACTIVO", "60"))
    ZONA_HORARIA = os.getenv("ZONA_HORARIA", "America/La_Paz")
    DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"

    CSV_UPLOAD_FOLDER = os.getenv("CSV_UPLOAD_FOLDER", str(BASE_DIR / "tmp" / "uploads"))


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite://"
