from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.forms import ClienteForm, DocumentoForm
from app.models import CANALES, Cliente, PedidoNoAtendido, Producto, Venta
from app.services import inventario as inv
from app.utils import log_access, rango_fechas_desde_request, roles_required

ventas_bp = Blueprint("ventas", __name__)


def _decimal(valor: str | None) -> Decimal:
    try:
        return Decimal((valor or "0").replace(",", "."))
    except InvalidOperation:
        return Decimal("0")


@ventas_bp.route("/")
@login_required
def lista():
    desde, hasta = rango_fechas_desde_request(30)
    ventas = (
        Venta.query.filter(
            Venta.fecha >= datetime.combine(desde, datetime.min.time()),
            Venta.fecha < datetime.combine(hasta + timedelta(days=1), datetime.min.time()),
        )
        .order_by(Venta.fecha.desc())
        .all()
    )
    confirmadas = [v for v in ventas if v.estado == "confirmada"]
    return render_template(
        "ventas/lista.html",
        title="Ventas",
        ventas=ventas,
        desde=desde,
        hasta=hasta,
        total=sum(float(v.total) for v in confirmadas),
        cantidad=len(confirmadas),
    )


@ventas_bp.route("/nueva", methods=["GET", "POST"])
@roles_required("gerencia", "ventas")
def nueva():
    form = DocumentoForm()
    almacenes = inv.almacenes_activos()
    clientes = Cliente.query.filter_by(activo=True).order_by(Cliente.nombre).all()
    if form.validate_on_submit():
        almacen_id = request.form.get("almacen_id", type=int)
        cliente_id = request.form.get("cliente_id", type=int) or None
        canal = request.form.get("canal") or "WhatsApp"
        tipo_precio = request.form.get("tipo_precio") or "mayorista"
        registrar_faltantes = request.form.get("registrar_faltantes") == "1"
        ids = request.form.getlist("producto_id[]")
        cantidades = request.form.getlist("cantidad[]")
        precios = request.form.getlist("precio[]")

        lineas, faltantes = [], []
        for pid, cant, precio in zip(ids, cantidades, precios):
            producto = db.session.get(Producto, int(pid)) if pid else None
            try:
                cantidad = int(cant)
            except (TypeError, ValueError):
                cantidad = 0
            if not producto or cantidad <= 0:
                continue
            disponible = producto.stock_en(almacen_id)
            if disponible < cantidad:
                faltantes.append((producto, cantidad, disponible))
                if disponible > 0 and registrar_faltantes:
                    lineas.append(inv.LineaDocumento(producto, disponible, _decimal(precio)))
                continue
            lineas.append(inv.LineaDocumento(producto, cantidad, _decimal(precio)))

        if faltantes and not registrar_faltantes:
            for p, c, d in faltantes:
                flash(f"{p.codigo}: se pidieron {c} y hay {d} en este almacén.", "danger")
        elif not lineas and not faltantes:
            flash("Agrega al menos un producto con cantidad mayor a cero.", "warning")
        else:
            cliente = db.session.get(Cliente, cliente_id) if cliente_id else None
            venta = None
            if lineas:
                venta = inv.registrar_venta(
                    lineas, almacen_id, cliente_id, canal, tipo_precio,
                    _decimal(request.form.get("descuento")), request.form.get("nota", "")[:255], current_user.id,
                )
            for p, c, d in faltantes:
                db.session.add(PedidoNoAtendido(
                    producto_id=p.id, cantidad=c - d if d > 0 else c,
                    tipo_cliente=cliente.tipo if cliente else "Conductor", cliente_id=cliente_id,
                    canal=canal, motivo="Sin stock", almacen_id=almacen_id, usuario_id=current_user.id,
                ))
            log_access("venta", venta.numero if venta else "solo faltantes")
            db.session.commit()
            if faltantes:
                flash(f"Se registraron {len(faltantes)} pedido(s) no atendido(s) por falta de stock.", "warning")
            if venta:
                flash(f"Venta {venta.numero} registrada por Bs {venta.total:,.2f}.".replace(",", "X").replace(".", ",").replace("X", "."), "success")
                return redirect(url_for("ventas.detalle", venta_id=venta.id))
            return redirect(url_for("pedidos.lista"))
    return render_template(
        "ventas/nueva.html", title="Nueva venta", form=form, almacenes=almacenes, clientes=clientes, canales=CANALES,
    )


@ventas_bp.route("/<int:venta_id>")
@login_required
def detalle(venta_id: int):
    venta = db.session.get(Venta, venta_id) or abort(404)
    return render_template("ventas/detalle.html", title=venta.numero, venta=venta, form=DocumentoForm())


@ventas_bp.route("/<int:venta_id>/anular", methods=["POST"])
@roles_required("gerencia")
def anular(venta_id: int):
    form = DocumentoForm()
    venta = db.session.get(Venta, venta_id) or abort(404)
    if not form.validate_on_submit() or venta.estado != "confirmada":
        flash("No se pudo anular la venta.", "danger")
        return redirect(url_for("ventas.detalle", venta_id=venta.id))
    for d in venta.detalles:
        inv.mover_stock(d.producto, venta.almacen_id, d.cantidad, "entrada", "Anulación de venta", venta.numero,
                        usuario_id=current_user.id)
    venta.estado = "anulada"
    log_access("venta_anulada", venta.numero)
    db.session.commit()
    flash(f"Venta {venta.numero} anulada y stock devuelto.", "info")
    return redirect(url_for("ventas.detalle", venta_id=venta.id))


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------

@ventas_bp.route("/clientes")
@login_required
def clientes():
    filas = inv.reporte_clientes()
    return render_template("clientes/lista.html", title="Clientes", filas=filas)


@ventas_bp.route("/clientes/nuevo", methods=["GET", "POST"])
@roles_required("gerencia", "ventas")
def cliente_nuevo():
    form = ClienteForm()
    if form.validate_on_submit():
        cliente = Cliente()
        form.populate_obj(cliente)
        db.session.add(cliente)
        log_access("cliente_nuevo", cliente.nombre)
        db.session.commit()
        flash("Cliente registrado.", "success")
        return redirect(url_for("ventas.clientes"))
    return render_template("clientes/form.html", title="Nuevo cliente", form=form, cliente=None)


@ventas_bp.route("/clientes/<int:cliente_id>/editar", methods=["GET", "POST"])
@roles_required("gerencia", "ventas")
def cliente_editar(cliente_id: int):
    cliente = db.session.get(Cliente, cliente_id) or abort(404)
    form = ClienteForm(obj=cliente)
    if form.validate_on_submit():
        form.populate_obj(cliente)
        db.session.commit()
        flash("Cliente actualizado.", "success")
        return redirect(url_for("ventas.cliente_detalle", cliente_id=cliente.id))
    return render_template("clientes/form.html", title=f"Editar {cliente.nombre}", form=form, cliente=cliente)


@ventas_bp.route("/clientes/<int:cliente_id>")
@login_required
def cliente_detalle(cliente_id: int):
    cliente = db.session.get(Cliente, cliente_id) or abort(404)
    ventas = cliente.ventas.order_by(Venta.fecha.desc()).limit(100).all()
    no_atendidos = PedidoNoAtendido.query.filter_by(cliente_id=cliente.id).order_by(PedidoNoAtendido.fecha.desc()).limit(50).all()
    total = sum(float(v.total) for v in ventas if v.estado == "confirmada")
    return render_template(
        "clientes/detalle.html", title=cliente.nombre, cliente=cliente, ventas=ventas, no_atendidos=no_atendidos, total=total,
    )
