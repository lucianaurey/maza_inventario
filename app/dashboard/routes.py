from __future__ import annotations

from flask import Blueprint, render_template
from flask_login import login_required

from app.models import PedidoNoAtendido
from app.services import inventario as inv

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def inicio():
    abc = inv.clasificacion_abc()
    clases = {f["producto"].id: f["clase"] for f in abc}
    kpis = inv.kpis_inicio()
    reposicion = inv.sugerencias_reposicion(clases)
    rotacion = inv.reporte_rotacion()
    sin_rotacion = [r for r in rotacion if r["sin_rotacion"]]

    serie = kpis["serie_no_atendidos"]
    charts = {
        "ventas": inv.ventas_mensuales(12),
        "categorias": inv.ventas_por_categoria(90),
        "no_atendidos": {
            "labels": [s["etiqueta"] for s in serie],
            "data": [round(s["pct"], 2) if s["pct"] is not None else None for s in serie],
        },
        "abc": {
            "labels": ["Clase A", "Clase B", "Clase C"],
            "data": [r["productos"] for r in inv.resumen_abc(abc)],
        },
    }
    ultimos_na = PedidoNoAtendido.query.order_by(PedidoNoAtendido.fecha.desc()).limit(8).all()
    return render_template(
        "dashboard.html",
        title="Inicio",
        kpis=kpis,
        charts=charts,
        reposicion=reposicion[:10],
        total_reposicion=len(reposicion),
        sin_rotacion=sin_rotacion[:6],
        total_sin_rotacion=len(sin_rotacion),
        valor_inmovilizado=sum(r["valor_stock"] for r in sin_rotacion),
        resumen_abc=inv.resumen_abc(abc),
        ultimos_na=ultimos_na,
    )
