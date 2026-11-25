from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, redirect, render_template, url_for
from werkzeug.security import generate_password_hash

from app import db
from app.forms import CsvUploadForm, UsuarioForm
from app.models import BitacoraAcceso, Categoria, Producto, Usuario
from app.utils import log_access, roles_required

admin_bp = Blueprint("admin", __name__)

COLUMNAS_CSV = [
    "codigo", "nombre", "categoria", "marca", "marca_vehiculo", "aplicacion", "atributos", "costo_unitario",
    "precio_mayorista", "precio_sugerido", "stock_minimo", "punto_reorden", "stock_maximo",
]


@admin_bp.route("/usuarios")
@roles_required()
def usuarios():
    return render_template("admin/usuarios.html", title="Usuarios", usuarios=Usuario.query.order_by(Usuario.username).all())


@admin_bp.route("/usuarios/nuevo", methods=["GET", "POST"])
@admin_bp.route("/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
@roles_required()
def usuario_form(usuario_id: int | None = None):
    usuario = db.session.get(Usuario, usuario_id) if usuario_id else None
    if usuario_id and usuario is None:
        abort(404)
    form = UsuarioForm(obj=usuario)
    if form.validate_on_submit():
        duplicado = Usuario.query.filter(
            (Usuario.username == form.username.data.strip()) | (Usuario.email == form.email.data.strip())
        ).filter(Usuario.id != (usuario.id if usuario else 0)).first()
        if duplicado:
            flash("Ese usuario o correo ya está registrado.", "danger")
        elif usuario is None and not form.password.data:
            flash("Define una contraseña para el usuario nuevo.", "danger")
        else:
            usuario = usuario or Usuario()
            usuario.username = form.username.data.strip()
            usuario.nombre_completo = form.nombre_completo.data.strip()
            usuario.email = form.email.data.strip()
            usuario.rol = form.rol.data
            usuario.estado = form.estado.data
            if form.password.data:
                usuario.password_hash = generate_password_hash(form.password.data)
            db.session.add(usuario)
            log_access("usuario_guardado", usuario.username)
            db.session.commit()
            flash("Usuario guardado.", "success")
            return redirect(url_for("admin.usuarios"))
    return render_template("admin/usuario_form.html", title="Usuario", form=form, usuario=usuario)


def _num(valor, tipo=Decimal):
    if valor is None or str(valor).strip() == "":
        return None
    try:
        return tipo(str(valor).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


@admin_bp.route("/importar", methods=["GET", "POST"])
@roles_required("gerencia")
def importar():
    form = CsvUploadForm()
    resultado = None
    if form.validate_on_submit():
        contenido = form.csv_file.data.read().decode("utf-8-sig", errors="replace")
        muestra = contenido[:2000]
        separador = ";" if muestra.count(";") > muestra.count(",") else ","
        lector = csv.DictReader(io.StringIO(contenido), delimiter=separador)
        categorias = {c.nombre.lower(): c for c in Categoria.query.all()}
        resultado = {"nuevos": 0, "actualizados": 0, "omitidos": 0, "errores": []}
        for n, fila in enumerate(lector, start=2):
            fila = {(k or "").strip().lower(): (v or "").strip() for k, v in fila.items()}
            codigo = fila.get("codigo", "").upper()
            if not codigo or not fila.get("nombre") and not Producto.query.filter_by(codigo=codigo).first():
                resultado["errores"].append(f"Línea {n}: falta código o nombre.")
                continue
            producto = Producto.query.filter_by(codigo=codigo).first()
            if producto and not form.actualizar.data:
                resultado["omitidos"] += 1
                continue
            nombre_cat = fila.get("categoria") or (producto.categoria.nombre if producto else "Varios")
            categoria = categorias.get(nombre_cat.lower())
            if categoria is None:
                categoria = Categoria(nombre=nombre_cat)
                db.session.add(categoria)
                db.session.flush()
                categorias[nombre_cat.lower()] = categoria
            nuevo = producto is None
            producto = producto or Producto(codigo=codigo, fuente="Importación CSV")
            producto.nombre = fila.get("nombre") or producto.nombre
            producto.categoria_id = categoria.id
            for campo in ("marca", "marca_vehiculo", "aplicacion", "atributos"):
                if fila.get(campo):
                    setattr(producto, campo, fila[campo])
            for campo in ("costo_unitario", "precio_mayorista", "precio_sugerido"):
                valor = _num(fila.get(campo))
                if valor is not None:
                    setattr(producto, campo, valor)
            for campo in ("stock_minimo", "punto_reorden", "stock_maximo"):
                valor = _num(fila.get(campo), int)
                if valor is not None:
                    setattr(producto, campo, valor)
            if nuevo:
                producto.marca = producto.marca or "Importada"
                db.session.add(producto)
                resultado["nuevos"] += 1
            else:
                resultado["actualizados"] += 1
        log_access("importar_productos", f"nuevos={resultado['nuevos']} actualizados={resultado['actualizados']}")
        db.session.commit()
        flash("Importación terminada.", "success")
    return render_template("admin/importar.html", title="Importar productos", form=form, resultado=resultado, columnas=COLUMNAS_CSV)


@admin_bp.route("/bitacora")
@roles_required()
def bitacora():
    registros = BitacoraAcceso.query.order_by(BitacoraAcceso.fecha_hora.desc()).limit(500).all()
    return render_template("admin/bitacora.html", title="Bitácora", registros=registros)
