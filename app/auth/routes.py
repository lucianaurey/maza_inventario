from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash

from app import db
from app.forms import LoginForm
from app.models import Usuario
from app.utils import log_access

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.inicio"))

    form = LoginForm()
    if form.validate_on_submit():
        user = Usuario.query.filter_by(username=form.username.data.strip()).first()
        if user and user.is_active and check_password_hash(user.password_hash, form.password.data):
            login_user(user, remember=form.remember.data)
            user.ultimo_acceso = datetime.utcnow()
            log_access("login", "Inicio de sesión correcto", user)
            db.session.commit()
            flash(f"Bienvenido, {user.nombre_completo.split()[0]}.", "success")
            next_url = request.args.get("next")
            if not next_url or urlparse(next_url).netloc:
                next_url = url_for("dashboard.inicio")
            return redirect(next_url)

        log_access("login_fallido", f"Usuario: {form.username.data}")
        db.session.commit()
        flash("Usuario o contraseña incorrectos, o el usuario está inactivo.", "danger")

    return render_template("login.html", form=form, title="Ingreso")


@auth_bp.route("/logout")
@login_required
def logout():
    log_access("logout", "Cierre de sesión")
    db.session.commit()
    logout_user()
    flash("Sesión cerrada.", "info")
    return redirect(url_for("auth.login"))
