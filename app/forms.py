from __future__ import annotations

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import (
    BooleanField,
    DecimalField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional

from app.models import CANALES, ROLES, TIPOS_CLIENTE


class LoginForm(FlaskForm):
    username = StringField("Usuario", validators=[DataRequired(), Length(max=80)])
    password = PasswordField("Contraseña", validators=[DataRequired(), Length(max=128)])
    remember = BooleanField("Recordarme")
    submit = SubmitField("Ingresar")


class ProductoForm(FlaskForm):
    codigo = StringField("Código", validators=[DataRequired(), Length(max=60)])
    codigos_alternos = StringField("Códigos alternos / equivalentes", validators=[Optional(), Length(max=255)])
    nombre = StringField("Nombre", validators=[DataRequired(), Length(max=180)])
    categoria_id = SelectField("Categoría", coerce=int, validators=[DataRequired()])
    marca = SelectField("Marca", choices=[("MAZA Parts", "MAZA Parts (marca propia)"), ("AMC", "AMC"), ("Importada", "Importada"), ("Original", "Original")])
    marca_vehiculo = StringField("Marca de vehículo", validators=[Optional(), Length(max=80)])
    aplicacion = TextAreaField("Aplicación (vehículos y motores)", validators=[Optional(), Length(max=255)])
    atributos = StringField("Atributos (pines, medidas, material)", validators=[Optional(), Length(max=255)])
    unidad = SelectField("Unidad", choices=[("pieza", "Pieza"), ("juego", "Juego"), ("par", "Par"), ("caja", "Caja")])
    costo_unitario = DecimalField("Costo unitario (Bs)", places=2, validators=[Optional(), NumberRange(min=0)], default=0)
    precio_mayorista = DecimalField("Precio mayorista (Bs)", places=2, validators=[Optional(), NumberRange(min=0)], default=0)
    precio_sugerido = DecimalField("Precio sugerido al público (Bs)", places=2, validators=[Optional(), NumberRange(min=0)], default=0)
    stock_minimo = IntegerField("Stock mínimo", validators=[Optional(), NumberRange(min=0)], default=0)
    punto_reorden = IntegerField("Punto de reorden", validators=[Optional(), NumberRange(min=0)], default=0)
    stock_maximo = IntegerField("Stock máximo", validators=[Optional(), NumberRange(min=0)], default=0)
    proveedor_id = SelectField("Proveedor", coerce=int, validators=[Optional()])
    activo = BooleanField("Producto activo", default=True)
    submit = SubmitField("Guardar producto")


class AjusteForm(FlaskForm):
    producto_id = IntegerField("Producto", validators=[DataRequired()])
    almacen_id = SelectField("Almacén", coerce=int, validators=[DataRequired()])
    tipo = SelectField("Tipo de ajuste", choices=[("conteo", "Conteo físico (fijar cantidad)"), ("entrada", "Entrada"), ("salida", "Salida")])
    cantidad = IntegerField("Cantidad", validators=[DataRequired(), NumberRange(min=0)])
    motivo = SelectField(
        "Motivo",
        choices=[
            ("Conteo físico", "Conteo físico"),
            ("Producto dañado", "Producto dañado"),
            ("Devolución de cliente", "Devolución de cliente"),
            ("Garantía", "Garantía"),
            ("Muestra / kit de bienvenida", "Muestra / kit de bienvenida"),
            ("Bonificación primera compra", "Bonificación primera compra"),
            ("Liquidación stock lento", "Liquidación stock lento"),
            ("Otro", "Otro"),
        ],
    )
    submit = SubmitField("Registrar ajuste")


class TransferenciaForm(FlaskForm):
    producto_id = IntegerField("Producto", validators=[DataRequired()])
    origen_id = SelectField("Desde", coerce=int, validators=[DataRequired()])
    destino_id = SelectField("Hacia", coerce=int, validators=[DataRequired()])
    cantidad = IntegerField("Cantidad", validators=[DataRequired(), NumberRange(min=1)])
    submit = SubmitField("Transferir")


class PedidoNoAtendidoForm(FlaskForm):
    producto_id = IntegerField("Producto", validators=[Optional()])
    descripcion = StringField("Si no está en el catálogo, descríbelo", validators=[Optional(), Length(max=255)])
    cantidad = IntegerField("Cantidad pedida", validators=[DataRequired(), NumberRange(min=1)], default=1)
    tipo_cliente = SelectField("Tipo de cliente", choices=[(t, t) for t in TIPOS_CLIENTE])
    cliente_id = SelectField("Cliente (opcional)", coerce=int, validators=[Optional()])
    canal = SelectField("Canal", choices=[(c, c) for c in CANALES])
    motivo = SelectField("Motivo", choices=[("Sin stock", "Sin stock"), ("No lo trabajamos", "No lo trabajamos"), ("Stock en otra ciudad", "Stock en otra ciudad")])
    almacen_id = SelectField("Almacén", coerce=int)
    submit = SubmitField("Registrar pedido no atendido")


class ClienteForm(FlaskForm):
    nombre = StringField("Nombre o razón social", validators=[DataRequired(), Length(max=160)])
    tipo = SelectField("Tipo", choices=[(t, t) for t in TIPOS_CLIENTE])
    ciudad = SelectField("Ciudad", choices=[("Cochabamba", "Cochabamba"), ("Santa Cruz", "Santa Cruz"), ("Otra", "Otra")])
    zona = StringField("Zona", validators=[Optional(), Length(max=120)])
    telefono = StringField("Teléfono / WhatsApp", validators=[Optional(), Length(max=40)])
    nit = StringField("NIT", validators=[Optional(), Length(max=40)])
    canal_origen = SelectField("¿Cómo llegó?", choices=[(c, c) for c in CANALES])
    registrado_whatsapp = BooleanField("Registrado en WhatsApp Business")
    recibio_kit = BooleanField("Recibió kit de bienvenida")
    notas = StringField("Notas", validators=[Optional(), Length(max=255)])
    activo = BooleanField("Activo", default=True)
    submit = SubmitField("Guardar cliente")


class ProveedorForm(FlaskForm):
    nombre = StringField("Nombre", validators=[DataRequired(), Length(max=160)])
    pais = StringField("País", validators=[Optional(), Length(max=80)])
    contacto = StringField("Contacto", validators=[Optional(), Length(max=160)])
    telefono = StringField("Teléfono", validators=[Optional(), Length(max=40)])
    dias_entrega = IntegerField("Días de entrega", validators=[Optional(), NumberRange(min=0)], default=30)
    activo = BooleanField("Activo", default=True)
    submit = SubmitField("Guardar proveedor")


class UsuarioForm(FlaskForm):
    username = StringField("Usuario", validators=[DataRequired(), Length(max=80)])
    nombre_completo = StringField("Nombre completo", validators=[DataRequired(), Length(max=160)])
    email = StringField("Correo", validators=[DataRequired(), Email(), Length(max=160)])
    rol = SelectField("Rol", choices=list(ROLES.items()))
    estado = SelectField("Estado", choices=[("activo", "Activo"), ("inactivo", "Inactivo")])
    password = PasswordField("Contraseña (déjala vacía para no cambiarla)", validators=[Optional(), Length(min=6, max=128)])
    submit = SubmitField("Guardar usuario")


class CsvUploadForm(FlaskForm):
    csv_file = FileField(
        "Archivo CSV",
        validators=[FileRequired(), FileAllowed(["csv"], "Solo se permiten archivos CSV.")],
    )
    actualizar = BooleanField("Actualizar precios y parámetros de productos que ya existen", default=True)
    submit = SubmitField("Importar")


class DocumentoForm(FlaskForm):
    """Solo aporta el token CSRF a los formularios de venta y compra con líneas dinámicas."""
