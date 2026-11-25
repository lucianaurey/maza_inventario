from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import click
from flask import Flask, redirect, render_template, url_for
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from werkzeug.security import generate_password_hash

from app.config import Config

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()


def create_app(config_class: type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)
    login_manager.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Inicia sesión para continuar."
    login_manager.login_message_category = "warning"

    from app.models import Usuario

    @login_manager.user_loader
    def load_user(user_id: str) -> Usuario | None:
        return db.session.get(Usuario, int(user_id))

    from app.admin.routes import admin_bp
    from app.auth.routes import auth_bp
    from app.compras.routes import compras_bp
    from app.dashboard.routes import dashboard_bp
    from app.inventario.routes import inventario_bp
    from app.pedidos.routes import pedidos_bp
    from app.productos.routes import productos_bp
    from app.reportes.routes import reportes_bp
    from app.ventas.routes import ventas_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp, url_prefix="/inicio")
    app.register_blueprint(productos_bp, url_prefix="/productos")
    app.register_blueprint(inventario_bp, url_prefix="/inventario")
    app.register_blueprint(ventas_bp, url_prefix="/ventas")
    app.register_blueprint(compras_bp, url_prefix="/compras")
    app.register_blueprint(pedidos_bp, url_prefix="/pedidos-no-atendidos")
    app.register_blueprint(reportes_bp, url_prefix="/reportes")
    app.register_blueprint(admin_bp, url_prefix="/admin")

    @app.route("/")
    def index():
        return redirect(url_for("dashboard.inicio"))

    @app.errorhandler(403)
    def forbidden(_):
        return render_template("errors/error.html", code=403, mensaje="No tienes permiso para ver esta sección."), 403

    @app.errorhandler(404)
    def not_found(_):
        return render_template("errors/error.html", code=404, mensaje="La página que buscas no existe."), 404

    @app.context_processor
    def inject_globals():
        return {
            "empresa": app.config["EMPRESA_NOMBRE"],
            "demo_mode": app.config["DEMO_MODE"],
            "ahora": datetime.now(),
        }

    register_template_filters(app)
    register_cli(app)
    _ensure_sqlite_schema(app)
    return app


def _ensure_sqlite_schema(app: Flask) -> None:
    """Con SQLite local, crea las tablas si la base está vacía para evitar el error 500."""
    if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite") or app.config.get("TESTING"):
        return
    from sqlalchemy import inspect

    with app.app_context():
        if not inspect(db.engine).has_table("usuarios"):
            db.create_all()
            from app.services.seed import crear_datos_base

            crear_datos_base()
            app.logger.warning(
                "Base de datos vacía: se crearon las tablas. Ejecuta 'flask --app run.py create-admin' "
                "para crear el usuario administrador."
            )


def register_template_filters(app: Flask) -> None:
    @app.template_filter("money")
    def money(value):
        if value is None:
            value = 0
        texto = f"{float(value):,.2f}"
        # formato boliviano: punto para miles y coma para decimales
        texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"Bs {texto}"

    @app.template_filter("num")
    def num(value):
        if value is None:
            value = 0
        return f"{int(value):,}".replace(",", ".")

    @app.template_filter("pct")
    def pct(value, decimals: int = 1):
        if value is None:
            return "—"
        return f"{float(value):.{decimals}f} %".replace(".", ",")

    @app.template_filter("fecha")
    def fecha(value, con_hora: bool = False):
        """Las fechas se guardan en UTC y se muestran en la hora de Bolivia."""
        if not value:
            return "—"
        if isinstance(value, datetime):
            try:
                zona = ZoneInfo(app.config["ZONA_HORARIA"])
            except Exception:
                zona = timezone(timedelta(hours=-4))
            value = value.replace(tzinfo=timezone.utc).astimezone(zona)
        return value.strftime("%d/%m/%Y %H:%M" if con_hora else "%d/%m/%Y")


def register_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db_command():
        """Crea todas las tablas (alternativa rápida a flask db upgrade)."""
        db.create_all()
        from app.services.seed import crear_datos_base

        crear_datos_base()
        click.echo("Base de datos lista: tablas, almacenes, categorías y proveedores base.")

    @app.cli.command("create-admin")
    def create_admin_command():
        """Crea o actualiza el administrador con las variables del .env."""
        from app.models import Usuario

        password = app.config["ADMIN_PASSWORD"]
        if not password:
            raise click.ClickException("Define ADMIN_PASSWORD en el archivo .env antes de crear el administrador.")

        username = app.config["ADMIN_USERNAME"]
        user = Usuario.query.filter_by(username=username).first()
        action = "actualizado"
        if user is None:
            user = Usuario(username=username)
            db.session.add(user)
            action = "creado"
        user.nombre_completo = app.config["ADMIN_FULL_NAME"]
        user.email = app.config["ADMIN_EMAIL"]
        user.password_hash = generate_password_hash(password)
        user.rol = "admin"
        user.estado = "activo"
        db.session.commit()
        click.echo(f"Usuario admin {action}: {username}")

    @app.cli.command("cargar-catalogo")
    def cargar_catalogo_command():
        """Carga los productos de los catálogos MAZA 2026 y AMC 2025 (sin stock ni precios)."""
        from app.services.seed import cargar_catalogo

        nuevos = cargar_catalogo()
        click.echo(f"Productos del catálogo cargados: {nuevos} nuevos.")

    @app.cli.command("seed-demo")
    @click.option("--meses", default=12, show_default=True, help="Meses de historial de ventas de ejemplo.")
    def seed_demo_command(meses: int):
        """Genera precios, stock, clientes y ventas DE EJEMPLO para probar los reportes."""
        from app.services.seed import generar_demo

        resumen = generar_demo(meses=meses)
        click.echo("Datos de ejemplo generados: " + ", ".join(f"{k}={v}" for k, v in resumen.items()))
