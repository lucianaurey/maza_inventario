from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta

from flask import Blueprint, Response, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from app import db
from app.forms import ProductoForm
from app.models import Categoria, Movimiento, PedidoNoAtendido, Producto, Proveedor, Venta, VentaDetalle
from app.services import inventario as inv
from app.utils import etiqueta_mes, log_access, roles_required

productos_bp = Blueprint("productos", __name__)


def _opciones(form: ProductoForm) -> None:
    form.categoria_id.choices = [(c.id, c.nombre) for c in Categoria.query.order_by(Categoria.nombre)]
    form.proveedor_id.choices = [(0, "— Sin proveedor —")] + [
        (p.id, p.nombre) for p in Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre)
    ]


@productos_bp.route("/")
@login_required
def lista():
    clases = inv.mapa_clases_abc()
    stock = dict(
        db.session.query(Producto.id, func.coalesce(func.sum(inv.Existencia.cantidad), 0))
        .outerjoin(inv.Existencia, inv.Existencia.producto_id == Producto.id)
        .group_by(Producto.id)
        .all()
    )
    productos = Producto.query.join(Categoria).order_by(Categoria.nombre, Producto.codigo).all()
    return render_template(
        "productos/lista.html",
        title="Productos",
        productos=productos,
        stock=stock,
        clases=clases,
        categorias=Categoria.query.order_by(Categoria.nombre).all(),
        filtro_estado=request.args.get("estado", ""),
    )


@productos_bp.route("/nuevo", methods=["GET", "POST"])
@roles_required("gerencia", "almacen")
def nuevo():
    form = ProductoForm()
    _opciones(form)
    if form.validate_on_submit():
        codigo = form.codigo.data.strip().upper()
        if Producto.query.filter_by(codigo=codigo).first():
            flash("Ya existe un producto con ese código.", "danger")
        else:
            producto = Producto(codigo=codigo, fuente="Registro manual")
            _guardar(form, producto)
            db.session.add(producto)
            log_access("producto_nuevo", codigo)
            db.session.commit()
            flash(f"Producto {codigo} creado.", "success")
            return redirect(url_for("productos.detalle", producto_id=producto.id))
    return render_template("productos/form.html", title="Nuevo producto", form=form, producto=None)


@productos_bp.route("/<int:producto_id>/editar", methods=["GET", "POST"])
@roles_required("gerencia", "almacen")
def editar(producto_id: int):
    producto = db.session.get(Producto, producto_id) or abort(404)
    form = ProductoForm(obj=producto)
    _opciones(form)
    if request.method == "GET":
        form.proveedor_id.data = producto.proveedor_id or 0
    if form.validate_on_submit():
        codigo = form.codigo.data.strip().upper()
        otro = Producto.query.filter(Producto.codigo == codigo, Producto.id != producto.id).first()
        if otro:
            flash("Otro producto ya usa ese código.", "danger")
        else:
            producto.codigo = codigo
            _guardar(form, producto)
            log_access("producto_editado", codigo)
            db.session.commit()
            flash("Cambios guardados.", "success")
            return redirect(url_for("productos.detalle", producto_id=producto.id))
    return render_template("productos/form.html", title=f"Editar {producto.codigo}", form=form, producto=producto)


def _guardar(form: ProductoForm, producto: Producto) -> None:
    producto.codigos_alternos = form.codigos_alternos.data or None
    producto.nombre = form.nombre.data.strip()
    producto.categoria_id = form.categoria_id.data
    producto.marca = form.marca.data
    producto.marca_vehiculo = (form.marca_vehiculo.data or "").strip().upper() or None
    producto.aplicacion = form.aplicacion.data or None
    producto.atributos = form.atributos.data or None
    producto.unidad = form.unidad.data
    producto.costo_unitario = form.costo_unitario.data or 0
    producto.precio_mayorista = form.precio_mayorista.data or 0
    producto.precio_sugerido = form.precio_sugerido.data or 0
    producto.stock_minimo = form.stock_minimo.data or 0
    producto.punto_reorden = form.punto_reorden.data or 0
    producto.stock_maximo = form.stock_maximo.data or 0
    producto.proveedor_id = form.proveedor_id.data or None
    producto.activo = bool(form.activo.data)


@productos_bp.route("/<int:producto_id>")
@login_required
def detalle(producto_id: int):
    producto = db.session.get(Producto, producto_id) or abort(404)
    movimientos = (
        Movimiento.query.filter_by(producto_id=producto.id).order_by(Movimiento.fecha.desc(), Movimiento.id.desc()).limit(150).all()
    )
    desde = datetime.utcnow() - timedelta(days=365)
    ventas = (
        db.session.query(Venta.fecha, VentaDetalle.cantidad)
        .join(VentaDetalle)
        .filter(VentaDetalle.producto_id == producto.id, Venta.fecha >= desde)
        .all()
    )
    por_mes: dict[tuple[int, int], int] = {}
    for fecha, cantidad in ventas:
        por_mes[(fecha.year, fecha.month)] = por_mes.get((fecha.year, fecha.month), 0) + cantidad
    hoy = datetime.utcnow()
    labels, data = [], []
    anio, mes = (hoy.year - 1, hoy.month + 1) if hoy.month < 12 else (hoy.year, 1)
    for _ in range(12):
        labels.append(etiqueta_mes(anio, mes))
        data.append(por_mes.get((anio, mes), 0))
        mes += 1
        if mes > 12:
            mes, anio = 1, anio + 1
    no_atendidos = PedidoNoAtendido.query.filter_by(producto_id=producto.id).count()
    clase = inv.mapa_clases_abc().get(producto.id, "C")
    return render_template(
        "productos/detalle.html",
        title=producto.codigo,
        producto=producto,
        movimientos=movimientos,
        almacenes=inv.almacenes_activos(),
        chart={"labels": labels, "data": data},
        unidades_anio=sum(data),
        no_atendidos=no_atendidos,
        clase=clase,
    )


@productos_bp.route("/api/buscar")
@login_required
def api_buscar():
    q = (request.args.get("q") or "").strip()
    almacen_id = request.args.get("almacen_id", type=int)
    if len(q) < 2:
        return jsonify([])
    patron = f"%{q}%"
    productos = (
        Producto.query.filter(Producto.activo.is_(True))
        .filter(
            or_(
                Producto.codigo.ilike(patron),
                Producto.codigos_alternos.ilike(patron),
                Producto.nombre.ilike(patron),
                Producto.aplicacion.ilike(patron),
            )
        )
        .order_by(Producto.codigo)
        .limit(15)
        .all()
    )
    return jsonify(
        [
            {
                "id": p.id,
                "codigo": p.codigo,
                "nombre": p.nombre,
                "aplicacion": (p.aplicacion or "")[:90],
                "stock": p.stock_en(almacen_id) if almacen_id else p.stock_total,
                "stock_total": p.stock_total,
                "precio_mayorista": float(p.precio_mayorista or 0),
                "precio_sugerido": float(p.precio_sugerido or 0),
                "costo": float(p.costo_unitario or 0),
            }
            for p in productos
        ]
    )


@productos_bp.route("/exportar.csv")
@login_required
def exportar():
    salida = io.StringIO()
    writer = csv.writer(salida)
    writer.writerow([
        "codigo", "codigos_alternos", "nombre", "categoria", "marca", "marca_vehiculo", "aplicacion", "atributos",
        "unidad", "costo_unitario", "precio_mayorista", "precio_sugerido", "stock_minimo", "punto_reorden",
        "stock_maximo", "stock_total", "activo",
    ])
    for p in Producto.query.join(Categoria).order_by(Categoria.nombre, Producto.codigo):
        writer.writerow([
            p.codigo, p.codigos_alternos or "", p.nombre, p.categoria.nombre, p.marca, p.marca_vehiculo or "",
            p.aplicacion or "", p.atributos or "", p.unidad, p.costo_unitario, p.precio_mayorista, p.precio_sugerido,
            p.stock_minimo, p.punto_reorden, p.stock_maximo, p.stock_total, "si" if p.activo else "no",
        ])
    log_access("exportar_productos", f"{current_user.username}")
    db.session.commit()
    return Response(
        "﻿" + salida.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=productos_maza.csv"},
    )
