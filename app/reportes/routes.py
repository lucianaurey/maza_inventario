from __future__ import annotations

from flask import Blueprint, current_app, render_template, request
from flask_login import login_required

from app.models import Proveedor
from app.services import inventario as inv

reportes_bp = Blueprint("reportes", __name__)


@reportes_bp.route("/abc")
@login_required
def abc():
    dias = request.args.get("dias", type=int) or current_app.config["DIAS_ANALISIS_ABC"]
    filas = inv.clasificacion_abc(dias)
    resumen = inv.resumen_abc(filas)
    vendidos = [f for f in filas if f["valor"] > 0]
    pareto = {
        "labels": [f["producto"].codigo for f in vendidos[:60]],
        "valor": [round(f["valor"], 2) for f in vendidos[:60]],
        "acumulado": [round(f["acumulado"], 2) for f in vendidos[:60]],
    }
    return render_template(
        "reportes/abc.html", title="Clasificación ABC", filas=filas, resumen=resumen, dias=dias, pareto=pareto,
    )


@reportes_bp.route("/rotacion")
@login_required
def rotacion():
    dias = request.args.get("dias", type=int) or 90
    filas = inv.reporte_rotacion(dias)
    sin_rotacion = [f for f in filas if f["sin_rotacion"]]
    return render_template(
        "reportes/rotacion.html",
        title="Rotación y stock lento",
        filas=filas,
        dias=dias,
        dias_sin=current_app.config["DIAS_SIN_ROTACION"],
        total_sin=len(sin_rotacion),
        valor_sin=sum(f["valor_stock"] for f in sin_rotacion),
        valor_total=sum(f["valor_stock"] for f in filas),
    )


@reportes_bp.route("/reposicion")
@login_required
def reposicion():
    filas = inv.sugerencias_reposicion()
    proveedores = {p.id: p for p in Proveedor.query.all()}
    por_proveedor: dict = {}
    for f in filas:
        pid = f["producto"].proveedor_id
        grupo = por_proveedor.setdefault(pid, {"proveedor": proveedores.get(pid), "items": 0, "costo": 0.0})
        grupo["items"] += 1
        grupo["costo"] += f["costo_estimado"]
    return render_template(
        "reportes/reposicion.html",
        title="Reposición sugerida",
        filas=filas,
        por_proveedor=sorted(por_proveedor.values(), key=lambda g: -g["costo"]),
        costo_total=sum(f["costo_estimado"] for f in filas),
    )


@reportes_bp.route("/clientes")
@login_required
def clientes():
    filas = inv.reporte_clientes()
    return render_template(
        "reportes/clientes.html",
        title="Clientes mayoristas",
        filas=filas,
        activos=sum(1 for f in filas if f["estado"] == "activo"),
        inactivos=sum(1 for f in filas if f["estado"] == "inactivo"),
        dias_inactivo=current_app.config["DIAS_CLIENTE_INACTIVO"],
    )


@reportes_bp.route("/indicadores")
@login_required
def indicadores():
    serie = inv.serie_pedidos_no_atendidos(12)
    return render_template(
        "reportes/indicadores.html",
        title="Indicadores del plan",
        indicadores=inv.indicadores_plan(),
        base=inv.linea_base_y_actual(serie),
        serie=serie,
    )
