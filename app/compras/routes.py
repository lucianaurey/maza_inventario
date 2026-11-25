from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.forms import DocumentoForm, ProveedorForm
from app.models import Compra, Producto, Proveedor
from app.services import inventario as inv
from app.utils import log_access, rango_fechas_desde_request, roles_required

compras_bp = Blueprint("compras", __name__)


def _decimal(valor: str | None) -> Decimal:
    try:
        return Decimal((valor or "0").replace(",", "."))
    except InvalidOperation:
        return Decimal("0")


@compras_bp.route("/")
@login_required
def lista():
    desde, hasta = rango_fechas_desde_request(90)
    compras = (
        Compra.query.filter(
            Compra.fecha >= datetime.combine(desde, datetime.min.time()),
            Compra.fecha < datetime.combine(hasta + timedelta(days=1), datetime.min.time()),
        )
        .order_by(Compra.fecha.desc())
        .all()
    )
    return render_template(
        "compras/lista.html", title="Compras e ingresos", compras=compras, desde=desde, hasta=hasta,
        total=sum(float(c.total) for c in compras),
    )


@compras_bp.route("/nueva", methods=["GET", "POST"])
@roles_required("gerencia", "almacen")
def nueva():
    form = DocumentoForm()
    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()
    if form.validate_on_submit():
        almacen_id = request.form.get("almacen_id", type=int)
        lineas = []
        for pid, cant, costo in zip(
            request.form.getlist("producto_id[]"), request.form.getlist("cantidad[]"), request.form.getlist("precio[]")
        ):
            producto = db.session.get(Producto, int(pid)) if pid else None
            try:
                cantidad = int(cant)
            except (TypeError, ValueError):
                cantidad = 0
            if producto and cantidad > 0:
                lineas.append(inv.LineaDocumento(producto, cantidad, _decimal(costo)))
        if not lineas:
            flash("Agrega al menos un producto con cantidad mayor a cero.", "warning")
        else:
            compra = inv.registrar_compra(
                lineas, almacen_id, request.form.get("proveedor_id", type=int) or None,
                request.form.get("documento", "")[:60], request.form.get("nota", "")[:255], current_user.id,
                actualizar_costo=request.form.get("actualizar_costo") == "1",
            )
            log_access("compra", compra.numero)
            db.session.commit()
            flash(f"Ingreso {compra.numero} registrado.", "success")
            return redirect(url_for("compras.detalle", compra_id=compra.id))

    # precarga desde la sugerencia de reposición
    precarga = []
    proveedor_sel = request.args.get("proveedor_id", type=int)
    if request.args.get("desde_reposicion"):
        for fila in inv.sugerencias_reposicion():
            p = fila["producto"]
            if proveedor_sel and p.proveedor_id != proveedor_sel:
                continue
            if fila["sugerido"] > 0:
                precarga.append({
                    "id": p.id, "codigo": p.codigo, "nombre": p.nombre, "cantidad": fila["sugerido"],
                    "precio": float(p.costo_unitario or 0), "stock": fila["stock"],
                })
    return render_template(
        "compras/nueva.html", title="Nuevo ingreso de mercadería", form=form, almacenes=inv.almacenes_activos(),
        proveedores=proveedores, precarga=precarga[:60], proveedor_sel=proveedor_sel,
    )


@compras_bp.route("/<int:compra_id>")
@login_required
def detalle(compra_id: int):
    compra = db.session.get(Compra, compra_id) or abort(404)
    return render_template("compras/detalle.html", title=compra.numero, compra=compra)


@compras_bp.route("/proveedores")
@login_required
def proveedores():
    return render_template("compras/proveedores.html", title="Proveedores", proveedores=Proveedor.query.order_by(Proveedor.nombre).all())


@compras_bp.route("/proveedores/nuevo", methods=["GET", "POST"])
@compras_bp.route("/proveedores/<int:proveedor_id>/editar", methods=["GET", "POST"])
@roles_required("gerencia", "almacen")
def proveedor_form(proveedor_id: int | None = None):
    proveedor = db.session.get(Proveedor, proveedor_id) if proveedor_id else None
    if proveedor_id and proveedor is None:
        abort(404)
    form = ProveedorForm(obj=proveedor)
    if form.validate_on_submit():
        proveedor = proveedor or Proveedor()
        form.populate_obj(proveedor)
        db.session.add(proveedor)
        db.session.commit()
        flash("Proveedor guardado.", "success")
        return redirect(url_for("compras.proveedores"))
    return render_template("compras/proveedor_form.html", title="Proveedor", form=form, proveedor=proveedor)
