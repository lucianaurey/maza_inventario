from __future__ import annotations

from datetime import datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.forms import AjusteForm, TransferenciaForm
from app.models import Categoria, Existencia, Movimiento, Producto
from app.services import inventario as inv
from app.utils import log_access, rango_fechas_desde_request, roles_required

inventario_bp = Blueprint("inventario", __name__)


@inventario_bp.route("/existencias")
@login_required
def existencias():
    almacenes = inv.almacenes_activos()
    clases = inv.mapa_clases_abc()
    filas = []
    existencias = {}
    for e in Existencia.query.all():
        existencias[(e.producto_id, e.almacen_id)] = e
    for p in Producto.query.filter_by(activo=True).join(Categoria).order_by(Categoria.nombre, Producto.codigo):
        por_almacen = [existencias.get((p.id, a.id)) for a in almacenes]
        total = sum(e.cantidad for e in por_almacen if e)
        filas.append({
            "producto": p,
            "por_almacen": [e.cantidad if e else 0 for e in por_almacen],
            "ubicacion": next((e.ubicacion for e in por_almacen if e and e.ubicacion), ""),
            "total": total,
            "valor": total * float(p.costo_unitario or 0),
            "clase": clases.get(p.id, "C"),
        })
    return render_template(
        "inventario/existencias.html",
        title="Existencias",
        filas=filas,
        almacenes=almacenes,
        valor_total=sum(f["valor"] for f in filas),
        unidades_total=sum(f["total"] for f in filas),
    )


@inventario_bp.route("/ajuste", methods=["GET", "POST"])
@roles_required("gerencia", "almacen")
def ajuste():
    form = AjusteForm()
    form.almacen_id.choices = [(a.id, a.nombre) for a in inv.almacenes_activos()]
    producto = None
    if request.method == "GET" and request.args.get("producto_id"):
        producto = db.session.get(Producto, request.args.get("producto_id", type=int))
        if producto:
            form.producto_id.data = producto.id
    if form.validate_on_submit():
        producto = db.session.get(Producto, form.producto_id.data)
        if producto is None:
            flash("Selecciona un producto de la lista.", "danger")
        else:
            actual = producto.stock_en(form.almacen_id.data)
            if form.tipo.data == "conteo":
                diferencia = form.cantidad.data - actual
            elif form.tipo.data == "entrada":
                diferencia = form.cantidad.data
            else:
                diferencia = -form.cantidad.data
            if diferencia == 0:
                flash("El conteo coincide con el sistema; no se registró ningún cambio.", "info")
            else:
                try:
                    inv.mover_stock(
                        producto, form.almacen_id.data, diferencia, "ajuste", form.motivo.data,
                        referencia=f"AJ-{datetime.utcnow():%y%m%d%H%M}", usuario_id=current_user.id,
                    )
                    log_access("ajuste_stock", f"{producto.codigo} {diferencia:+d}")
                    db.session.commit()
                    flash(f"Ajuste registrado: {producto.codigo} {diferencia:+d} unidades.", "success")
                    return redirect(url_for("productos.detalle", producto_id=producto.id))
                except inv.StockInsuficiente as exc:
                    db.session.rollback()
                    flash(str(exc), "danger")
    return render_template("inventario/ajuste.html", title="Ajuste de inventario", form=form, producto=producto)


@inventario_bp.route("/transferencia", methods=["GET", "POST"])
@roles_required("gerencia", "almacen")
def transferencia():
    form = TransferenciaForm()
    opciones = [(a.id, a.nombre) for a in inv.almacenes_activos()]
    form.origen_id.choices = opciones
    form.destino_id.choices = opciones
    if request.method == "GET" and len(opciones) > 1:
        form.destino_id.data = opciones[1][0]
    producto = None
    if form.validate_on_submit():
        producto = db.session.get(Producto, form.producto_id.data)
        if producto is None:
            flash("Selecciona un producto de la lista.", "danger")
        elif form.origen_id.data == form.destino_id.data:
            flash("El almacén de origen y el de destino deben ser distintos.", "danger")
        else:
            try:
                inv.transferir(producto, form.origen_id.data, form.destino_id.data, form.cantidad.data, current_user.id)
                log_access("transferencia", f"{producto.codigo} x{form.cantidad.data}")
                db.session.commit()
                flash(f"Se transfirieron {form.cantidad.data} unidades de {producto.codigo}.", "success")
                return redirect(url_for("inventario.existencias"))
            except inv.StockInsuficiente as exc:
                db.session.rollback()
                flash(str(exc), "danger")
    return render_template("inventario/transferencia.html", title="Transferencia entre almacenes", form=form, producto=producto)


@inventario_bp.route("/kardex")
@login_required
def kardex():
    desde, hasta = rango_fechas_desde_request(30)
    tipo = request.args.get("tipo", "")
    almacen_id = request.args.get("almacen_id", type=int)
    q = Movimiento.query.filter(
        Movimiento.fecha >= datetime.combine(desde, datetime.min.time()),
        Movimiento.fecha < datetime.combine(hasta + timedelta(days=1), datetime.min.time()),
    )
    if tipo:
        q = q.filter(Movimiento.tipo == tipo)
    if almacen_id:
        q = q.filter(Movimiento.almacen_id == almacen_id)
    movimientos = q.order_by(Movimiento.fecha.desc(), Movimiento.id.desc()).limit(3000).all()
    return render_template(
        "inventario/kardex.html",
        title="Movimientos (kardex)",
        movimientos=movimientos,
        desde=desde,
        hasta=hasta,
        tipo=tipo,
        almacen_id=almacen_id,
        almacenes=inv.almacenes_activos(),
    )
