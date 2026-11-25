from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import wraps

from flask import abort, redirect, request, url_for
from flask_login import current_user

from app import db
from app.models import BitacoraAcceso, Usuario


def log_access(accion: str, detalle: str = "", user: Usuario | None = None) -> None:
    actor = user if user is not None else (current_user if current_user.is_authenticated else None)
    db.session.add(
        BitacoraAcceso(
            usuario_id=actor.id if actor else None,
            ip=request.headers.get("X-Forwarded-For", request.remote_addr),
            accion=accion,
            detalle=(detalle or "")[:255],
        )
    )


def roles_required(*roles: str):
    """Permite el acceso al administrador y a los roles indicados."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if not current_user.puede(*roles):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def parse_fecha(valor: str | None, defecto: date | None = None) -> date | None:
    if not valor:
        return defecto
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        return defecto


def rango_fechas_desde_request(dias_defecto: int = 30) -> tuple[date, date]:
    hoy = date.today()
    hasta = parse_fecha(request.args.get("hasta"), hoy)
    desde = parse_fecha(request.args.get("desde"), hasta - timedelta(days=dias_defecto))
    if desde > hasta:
        desde, hasta = hasta, desde
    return desde, hasta


MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def etiqueta_mes(anio: int, mes: int) -> str:
    return f"{MESES[mes - 1]} {str(anio)[2:]}"
