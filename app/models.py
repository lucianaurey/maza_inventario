from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from flask_login import UserMixin
from sqlalchemy import UniqueConstraint, func

from app import db

ROLES = {
    "admin": "Administrador",
    "gerencia": "Gerencia",
    "ventas": "Ventas",
    "almacen": "Almacén",
}

TIPOS_CLIENTE = ["Tienda de repuestos", "Taller mecánico", "Conductor", "Empresa / flota"]
CANALES = ["WhatsApp", "Tienda Supermall", "Visita del vendedor", "Página web", "Teléfono"]


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    nombre_completo = db.Column(db.String(160), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default="ventas", index=True)
    estado = db.Column(db.String(20), nullable=False, default="activo", index=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    ultimo_acceso = db.Column(db.DateTime)

    accesos = db.relationship("BitacoraAcceso", back_populates="usuario", lazy="dynamic")

    @property
    def is_active(self) -> bool:
        return self.estado == "activo"

    @property
    def rol_nombre(self) -> str:
        return ROLES.get(self.rol, self.rol)

    def puede(self, *roles: str) -> bool:
        return self.rol == "admin" or self.rol in roles


class BitacoraAcceso(db.Model):
    __tablename__ = "bitacora_acceso"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True, index=True)
    fecha_hora = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    ip = db.Column(db.String(64))
    accion = db.Column(db.String(80), nullable=False)
    detalle = db.Column(db.String(255))

    usuario = db.relationship("Usuario", back_populates="accesos")


class Almacen(db.Model):
    __tablename__ = "almacenes"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), unique=True, nullable=False)
    ciudad = db.Column(db.String(80), nullable=False)
    direccion = db.Column(db.String(255))
    activo = db.Column(db.Boolean, nullable=False, default=True)


class Categoria(db.Model):
    __tablename__ = "categorias"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), unique=True, nullable=False)
    descripcion = db.Column(db.String(255))

    productos = db.relationship("Producto", back_populates="categoria", lazy="dynamic")


class Proveedor(db.Model):
    __tablename__ = "proveedores"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(160), unique=True, nullable=False)
    pais = db.Column(db.String(80))
    contacto = db.Column(db.String(160))
    telefono = db.Column(db.String(40))
    dias_entrega = db.Column(db.Integer, nullable=False, default=30)
    activo = db.Column(db.Boolean, nullable=False, default=True)


class Producto(db.Model):
    __tablename__ = "productos"

    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(60), unique=True, nullable=False, index=True)
    codigos_alternos = db.Column(db.String(255))
    nombre = db.Column(db.String(180), nullable=False, index=True)
    categoria_id = db.Column(db.Integer, db.ForeignKey("categorias.id"), nullable=False, index=True)
    marca = db.Column(db.String(80), nullable=False, default="Importada", index=True)
    marca_vehiculo = db.Column(db.String(80), index=True)
    aplicacion = db.Column(db.String(255))
    atributos = db.Column(db.String(255))
    unidad = db.Column(db.String(20), nullable=False, default="pieza")
    costo_unitario = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    precio_mayorista = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    precio_sugerido = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    stock_minimo = db.Column(db.Integer, nullable=False, default=0)
    punto_reorden = db.Column(db.Integer, nullable=False, default=0)
    stock_maximo = db.Column(db.Integer, nullable=False, default=0)
    proveedor_id = db.Column(db.Integer, db.ForeignKey("proveedores.id"), nullable=True)
    pagina_catalogo = db.Column(db.Integer)
    fuente = db.Column(db.String(80))
    activo = db.Column(db.Boolean, nullable=False, default=True, index=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    categoria = db.relationship("Categoria", back_populates="productos")
    proveedor = db.relationship("Proveedor")
    existencias = db.relationship("Existencia", back_populates="producto", cascade="all, delete-orphan")

    @property
    def stock_total(self) -> int:
        return sum(e.cantidad for e in self.existencias)

    def stock_en(self, almacen_id: int) -> int:
        for e in self.existencias:
            if e.almacen_id == almacen_id:
                return e.cantidad
        return 0

    @property
    def estado_stock(self) -> str:
        stock = self.stock_total
        if stock <= 0:
            return "agotado"
        if stock <= self.stock_minimo:
            return "critico"
        if stock <= self.punto_reorden:
            return "reponer"
        return "ok"

    @property
    def margen_mayorista(self) -> float:
        if not self.precio_mayorista:
            return 0.0
        return float((Decimal(self.precio_mayorista) - Decimal(self.costo_unitario)) / Decimal(self.precio_mayorista) * 100)


class Existencia(db.Model):
    __tablename__ = "existencias"
    __table_args__ = (UniqueConstraint("producto_id", "almacen_id", name="uq_existencia_producto_almacen"),)

    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), nullable=False, index=True)
    almacen_id = db.Column(db.Integer, db.ForeignKey("almacenes.id"), nullable=False, index=True)
    cantidad = db.Column(db.Integer, nullable=False, default=0)
    ubicacion = db.Column(db.String(60))

    producto = db.relationship("Producto", back_populates="existencias")
    almacen = db.relationship("Almacen")


class Cliente(db.Model):
    __tablename__ = "clientes"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(160), nullable=False, index=True)
    tipo = db.Column(db.String(40), nullable=False, default="Tienda de repuestos", index=True)
    ciudad = db.Column(db.String(80), nullable=False, default="Cochabamba", index=True)
    zona = db.Column(db.String(120))
    telefono = db.Column(db.String(40))
    nit = db.Column(db.String(40))
    canal_origen = db.Column(db.String(40))
    registrado_whatsapp = db.Column(db.Boolean, nullable=False, default=False)
    recibio_kit = db.Column(db.Boolean, nullable=False, default=False)
    notas = db.Column(db.String(255))
    activo = db.Column(db.Boolean, nullable=False, default=True)
    fecha_registro = db.Column(db.Date, nullable=False, default=lambda: datetime.utcnow().date())

    ventas = db.relationship("Venta", back_populates="cliente", lazy="dynamic")


class Venta(db.Model):
    __tablename__ = "ventas"

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(20), unique=True, nullable=False, index=True)
    fecha = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=True, index=True)
    almacen_id = db.Column(db.Integer, db.ForeignKey("almacenes.id"), nullable=False)
    canal = db.Column(db.String(40), nullable=False, default="WhatsApp", index=True)
    tipo_precio = db.Column(db.String(20), nullable=False, default="mayorista")
    descuento = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    estado = db.Column(db.String(20), nullable=False, default="confirmada")
    nota = db.Column(db.String(255))
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))

    cliente = db.relationship("Cliente", back_populates="ventas")
    almacen = db.relationship("Almacen")
    usuario = db.relationship("Usuario")
    detalles = db.relationship("VentaDetalle", back_populates="venta", cascade="all, delete-orphan")

    @property
    def subtotal(self) -> Decimal:
        return sum((d.subtotal for d in self.detalles), Decimal("0"))


class VentaDetalle(db.Model):
    __tablename__ = "venta_detalles"

    id = db.Column(db.Integer, primary_key=True)
    venta_id = db.Column(db.Integer, db.ForeignKey("ventas.id"), nullable=False, index=True)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), nullable=False, index=True)
    cantidad = db.Column(db.Integer, nullable=False)
    precio_unitario = db.Column(db.Numeric(12, 2), nullable=False)
    costo_unitario = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    venta = db.relationship("Venta", back_populates="detalles")
    producto = db.relationship("Producto")

    @property
    def subtotal(self) -> Decimal:
        return Decimal(self.precio_unitario) * self.cantidad


class Compra(db.Model):
    __tablename__ = "compras"

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(20), unique=True, nullable=False, index=True)
    fecha = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    proveedor_id = db.Column(db.Integer, db.ForeignKey("proveedores.id"), nullable=True)
    almacen_id = db.Column(db.Integer, db.ForeignKey("almacenes.id"), nullable=False)
    documento = db.Column(db.String(60))
    total = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    nota = db.Column(db.String(255))
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))

    proveedor = db.relationship("Proveedor")
    almacen = db.relationship("Almacen")
    usuario = db.relationship("Usuario")
    detalles = db.relationship("CompraDetalle", back_populates="compra", cascade="all, delete-orphan")


class CompraDetalle(db.Model):
    __tablename__ = "compra_detalles"

    id = db.Column(db.Integer, primary_key=True)
    compra_id = db.Column(db.Integer, db.ForeignKey("compras.id"), nullable=False, index=True)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), nullable=False, index=True)
    cantidad = db.Column(db.Integer, nullable=False)
    costo_unitario = db.Column(db.Numeric(12, 2), nullable=False)

    compra = db.relationship("Compra", back_populates="detalles")
    producto = db.relationship("Producto")

    @property
    def subtotal(self) -> Decimal:
        return Decimal(self.costo_unitario) * self.cantidad


class Movimiento(db.Model):
    """Kardex: cada cambio de stock queda registrado aquí."""

    __tablename__ = "movimientos"

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), nullable=False, index=True)
    almacen_id = db.Column(db.Integer, db.ForeignKey("almacenes.id"), nullable=False, index=True)
    tipo = db.Column(db.String(20), nullable=False, index=True)  # entrada, salida, ajuste, transferencia
    motivo = db.Column(db.String(60), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)  # positiva = entra, negativa = sale
    saldo = db.Column(db.Integer, nullable=False)
    costo_unitario = db.Column(db.Numeric(12, 2))
    referencia = db.Column(db.String(60))
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))

    producto = db.relationship("Producto")
    almacen = db.relationship("Almacen")
    usuario = db.relationship("Usuario")


class PedidoNoAtendido(db.Model):
    """Pedido que el cliente hizo y MAZA no pudo atender (KPI de la Propuesta 7)."""

    __tablename__ = "pedidos_no_atendidos"

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), nullable=True, index=True)
    descripcion = db.Column(db.String(255))
    cantidad = db.Column(db.Integer, nullable=False, default=1)
    tipo_cliente = db.Column(db.String(40), nullable=False, index=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=True)
    canal = db.Column(db.String(40), nullable=False, index=True)
    motivo = db.Column(db.String(40), nullable=False, default="Sin stock", index=True)
    almacen_id = db.Column(db.Integer, db.ForeignKey("almacenes.id"))
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))

    producto = db.relationship("Producto")
    cliente = db.relationship("Cliente")
    almacen = db.relationship("Almacen")
    usuario = db.relationship("Usuario")


def siguiente_numero(modelo, prefijo: str) -> str:
    ultimo = db.session.query(func.max(modelo.id)).scalar() or 0
    return f"{prefijo}-{ultimo + 1:06d}"
