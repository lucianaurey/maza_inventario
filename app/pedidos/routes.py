from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.forms import PedidoNoAtendidoForm
from app.models import Cliente, PedidoNoAtendido, Producto
from app.services import inventario as inv
from app.utils import log_access, rango_fechas_desde_request, roles_required

pedidos_bp = Blueprint("pedidos", __name__)


@pedidos_bp.route("/")
@login_required
def lista():
    desde, hasta = rango_fechas_desde_request(90)
    pedidos = (
        PedidoNoAtendido.query.filter(
            PedidoNoAtendido.fecha >= datetime.combine(desde, datetime.min.time()),
            PedidoNoAtendido.fecha < datetime.combine(hasta + timedelta(days=1), datetime.min.time()),
        )
        .order_by(PedidoNoAtendido.fecha.desc())
        .all()
    )
    top = Counter()
    unidades = Counter()
    for p in pedidos:
        clave = p.producto_id or f"txt:{p.descripcion}"
        top[clave] += 1
        unidades[clave] += p.cantidad
    productos = {p.id: p for p in Producto.query.filter(Producto.id.in_([k for k in top if isinstance(k, int)])).all()}
    ranking = [
        {
            "producto": productos.get(k) if isinstance(k, int) else None,
            "descripcion": None if isinstance(k, int) else k[4:],
            "veces": n,
            "unidades": unidades[k],
        }
        for k, n in top.most_common(10)
    ]
    serie = inv.serie_pedidos_no_atendidos(12)
    base = inv.linea_base_y_actual(serie)
    por_canal = Counter(p.canal for p in pedidos)
    por_tipo = Counter(p.tipo_cliente for p in pedidos)
    return render_template(
        "pedidos/lista.html",
        title="Pedidos no atendidos",
        pedidos=pedidos,
        desde=desde,
        hasta=hasta,
        ranking=ranking,
        serie=serie,
        base=base,
        chart={
            "labels": [s["etiqueta"] for s in serie],
            "pct": [round(s["pct"], 2) if s["pct"] is not None else None for s in serie],
            "meta": [round(base["meta"], 2) if base["meta"] is not None else None for _ in serie],
        },
        por_canal=por_canal.most_common(),
        por_tipo=por_tipo.most_common(),
    )


@pedidos_bp.route("/nuevo", methods=["GET", "POST"])
@roles_required("gerencia", "ventas", "almacen")
def nuevo():
    form = PedidoNoAtendidoForm()
    form.cliente_id.choices = [(0, "— Sin cliente registrado —")] + [
        (c.id, c.nombre) for c in Cliente.query.filter_by(activo=True).order_by(Cliente.nombre)
    ]
    form.almacen_id.choices = [(a.id, a.nombre) for a in inv.almacenes_activos()]
    if form.validate_on_submit():
        producto = db.session.get(Producto, form.producto_id.data) if form.producto_id.data else None
        if not producto and not (form.descripcion.data or "").strip():
            flash("Elige un producto del catálogo o describe lo que pidió el cliente.", "warning")
        else:
            pedido = PedidoNoAtendido(
                producto_id=producto.id if producto else None,
                descripcion=(form.descripcion.data or "").strip() or None,
                cantidad=form.cantidad.data,
                tipo_cliente=form.tipo_cliente.data,
                cliente_id=form.cliente_id.data or None,
                canal=form.canal.data,
                motivo=form.motivo.data,
                almacen_id=form.almacen_id.data,
                usuario_id=current_user.id,
            )
            db.session.add(pedido)
            log_access("pedido_no_atendido", producto.codigo if producto else pedido.descripcion)
            db.session.commit()
            flash("Pedido no atendido registrado. ¡Gracias por anotarlo!", "success")
            if request.form.get("otro"):
                return redirect(url_for("pedidos.nuevo"))
            return redirect(url_for("pedidos.lista"))
    return render_template("pedidos/nuevo.html", title="Registrar pedido no atendido", form=form)
