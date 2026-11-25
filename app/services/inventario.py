"""Lógica de inventario: movimientos de stock, ventas, compras y reportes."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import current_app
from sqlalchemy import func

from app import db
from app.models import (
    Almacen,
    Cliente,
    Compra,
    CompraDetalle,
    Existencia,
    Movimiento,
    PedidoNoAtendido,
    Producto,
    Venta,
    VentaDetalle,
    siguiente_numero,
)
from app.utils import etiqueta_mes


class StockInsuficiente(Exception):
    def __init__(self, producto: Producto, disponible: int, solicitado: int):
        self.producto = producto
        self.disponible = disponible
        self.solicitado = solicitado
        super().__init__(
            f"Stock insuficiente de {producto.codigo}: hay {disponible} y se pidieron {solicitado}."
        )


# ---------------------------------------------------------------------------
# Movimientos de stock
# ---------------------------------------------------------------------------

def obtener_existencia(producto_id: int, almacen_id: int) -> Existencia:
    existencia = Existencia.query.filter_by(producto_id=producto_id, almacen_id=almacen_id).first()
    if existencia is None:
        existencia = Existencia(producto_id=producto_id, almacen_id=almacen_id, cantidad=0)
        db.session.add(existencia)
        db.session.flush()
    return existencia


def mover_stock(
    producto: Producto,
    almacen_id: int,
    cantidad: int,
    tipo: str,
    motivo: str,
    referencia: str = "",
    costo_unitario: Decimal | None = None,
    usuario_id: int | None = None,
    fecha: datetime | None = None,
    permitir_negativo: bool = False,
) -> Movimiento:
    """Suma (cantidad > 0) o resta (cantidad < 0) stock y deja el registro en el kardex."""
    existencia = obtener_existencia(producto.id, almacen_id)
    nuevo_saldo = existencia.cantidad + cantidad
    if nuevo_saldo < 0 and not permitir_negativo:
        raise StockInsuficiente(producto, existencia.cantidad, -cantidad)
    existencia.cantidad = nuevo_saldo
    movimiento = Movimiento(
        fecha=fecha or datetime.utcnow(),
        producto_id=producto.id,
        almacen_id=almacen_id,
        tipo=tipo,
        motivo=motivo,
        cantidad=cantidad,
        saldo=nuevo_saldo,
        costo_unitario=costo_unitario if costo_unitario is not None else producto.costo_unitario,
        referencia=referencia,
        usuario_id=usuario_id,
    )
    db.session.add(movimiento)
    return movimiento


@dataclass
class LineaDocumento:
    producto: Producto
    cantidad: int
    precio: Decimal


def registrar_venta(
    lineas: list[LineaDocumento],
    almacen_id: int,
    cliente_id: int | None,
    canal: str,
    tipo_precio: str,
    descuento: Decimal,
    nota: str,
    usuario_id: int | None,
    fecha: datetime | None = None,
) -> Venta:
    venta = Venta(
        numero=siguiente_numero(Venta, "V"),
        fecha=fecha or datetime.utcnow(),
        cliente_id=cliente_id,
        almacen_id=almacen_id,
        canal=canal,
        tipo_precio=tipo_precio,
        descuento=descuento or Decimal("0"),
        nota=nota,
        usuario_id=usuario_id,
    )
    db.session.add(venta)
    db.session.flush()
    total = Decimal("0")
    for linea in lineas:
        mover_stock(
            linea.producto, almacen_id, -linea.cantidad, "salida", "Venta", venta.numero,
            usuario_id=usuario_id, fecha=venta.fecha,
        )
        venta.detalles.append(
            VentaDetalle(
                producto_id=linea.producto.id,
                cantidad=linea.cantidad,
                precio_unitario=linea.precio,
                costo_unitario=linea.producto.costo_unitario,
            )
        )
        total += linea.precio * linea.cantidad
    venta.total = max(total - venta.descuento, Decimal("0"))
    return venta


def registrar_compra(
    lineas: list[LineaDocumento],
    almacen_id: int,
    proveedor_id: int | None,
    documento: str,
    nota: str,
    usuario_id: int | None,
    actualizar_costo: bool = True,
    fecha: datetime | None = None,
) -> Compra:
    compra = Compra(
        numero=siguiente_numero(Compra, "C"),
        fecha=fecha or datetime.utcnow(),
        proveedor_id=proveedor_id,
        almacen_id=almacen_id,
        documento=documento,
        nota=nota,
        usuario_id=usuario_id,
    )
    db.session.add(compra)
    db.session.flush()
    total = Decimal("0")
    for linea in lineas:
        if actualizar_costo and linea.precio > 0:
            # costo promedio ponderado
            stock_actual = linea.producto.stock_total
            costo_actual = Decimal(linea.producto.costo_unitario or 0)
            if stock_actual + linea.cantidad > 0:
                linea.producto.costo_unitario = (
                    (costo_actual * max(stock_actual, 0) + linea.precio * linea.cantidad)
                    / (max(stock_actual, 0) + linea.cantidad)
                ).quantize(Decimal("0.01"))
        mover_stock(
            linea.producto, almacen_id, linea.cantidad, "entrada", "Compra", compra.numero,
            costo_unitario=linea.precio, usuario_id=usuario_id, fecha=compra.fecha,
        )
        compra.detalles.append(
            CompraDetalle(producto_id=linea.producto.id, cantidad=linea.cantidad, costo_unitario=linea.precio)
        )
        total += linea.precio * linea.cantidad
    compra.total = total
    return compra


def transferir(producto: Producto, origen_id: int, destino_id: int, cantidad: int, usuario_id: int | None) -> None:
    referencia = f"TR-{datetime.utcnow():%y%m%d%H%M%S}"
    mover_stock(producto, origen_id, -cantidad, "transferencia", "Transferencia (salida)", referencia, usuario_id=usuario_id)
    mover_stock(producto, destino_id, cantidad, "transferencia", "Transferencia (entrada)", referencia, usuario_id=usuario_id)


# ---------------------------------------------------------------------------
# Reportes
# ---------------------------------------------------------------------------

def _ventas_por_producto(desde: datetime, hasta: datetime | None = None) -> dict[int, dict]:
    hasta = hasta or datetime.utcnow() + timedelta(days=1)
    filas = (
        db.session.query(
            VentaDetalle.producto_id,
            func.sum(VentaDetalle.cantidad).label("unidades"),
            func.sum(VentaDetalle.cantidad * VentaDetalle.precio_unitario).label("valor"),
            func.sum(VentaDetalle.cantidad * VentaDetalle.costo_unitario).label("costo"),
            func.count(VentaDetalle.id).label("lineas"),
            func.max(Venta.fecha).label("ultima"),
        )
        .join(Venta, Venta.id == VentaDetalle.venta_id)
        .filter(Venta.fecha >= desde, Venta.fecha < hasta, Venta.estado == "confirmada")
        .group_by(VentaDetalle.producto_id)
        .all()
    )
    return {
        f.producto_id: {
            "unidades": int(f.unidades or 0),
            "valor": float(f.valor or 0),
            "costo": float(f.costo or 0),
            "lineas": int(f.lineas or 0),
            "ultima": f.ultima,
        }
        for f in filas
    }


def _stock_por_producto() -> dict[int, int]:
    return dict(
        db.session.query(Existencia.producto_id, func.sum(Existencia.cantidad)).group_by(Existencia.producto_id).all()
    )


def clasificacion_abc(dias: int | None = None, corte_a: float = 80.0, corte_b: float = 95.0) -> list[dict]:
    """Clasifica los productos por su aporte al valor vendido (método ABC / Pareto)."""
    dias = dias or current_app.config["DIAS_ANALISIS_ABC"]
    desde = datetime.utcnow() - timedelta(days=dias)
    ventas = _ventas_por_producto(desde)
    stock = _stock_por_producto()
    productos = Producto.query.filter_by(activo=True).all()
    total = sum(v["valor"] for v in ventas.values()) or 1.0

    filas = []
    for p in productos:
        v = ventas.get(p.id, {"unidades": 0, "valor": 0.0, "costo": 0.0, "lineas": 0, "ultima": None})
        filas.append(
            {
                "producto": p,
                "unidades": v["unidades"],
                "valor": v["valor"],
                "margen": v["valor"] - v["costo"],
                "lineas": v["lineas"],
                "stock": int(stock.get(p.id, 0) or 0),
            }
        )
    filas.sort(key=lambda f: f["valor"], reverse=True)
    acumulado = 0.0
    for f in filas:
        f["participacion"] = f["valor"] / total * 100
        acumulado += f["participacion"]
        f["acumulado"] = acumulado
        if f["valor"] <= 0:
            f["clase"] = "C"
        elif acumulado - f["participacion"] < corte_a:
            f["clase"] = "A"
        elif acumulado - f["participacion"] < corte_b:
            f["clase"] = "B"
        else:
            f["clase"] = "C"
    return filas


def mapa_clases_abc(dias: int | None = None) -> dict[int, str]:
    return {f["producto"].id: f["clase"] for f in clasificacion_abc(dias)}


def resumen_abc(filas: list[dict]) -> list[dict]:
    resumen = []
    total_valor = sum(f["valor"] for f in filas) or 1.0
    total_items = len(filas) or 1
    for clase in "ABC":
        grupo = [f for f in filas if f["clase"] == clase]
        valor = sum(f["valor"] for f in grupo)
        resumen.append(
            {
                "clase": clase,
                "productos": len(grupo),
                "pct_productos": len(grupo) / total_items * 100,
                "valor": valor,
                "pct_valor": valor / total_valor * 100,
            }
        )
    return resumen


def reporte_rotacion(dias: int | None = None) -> list[dict]:
    """Rotación, días de inventario y stock inmovilizado por producto."""
    dias_sin = current_app.config["DIAS_SIN_ROTACION"]
    dias = dias or 90
    hoy = datetime.utcnow()
    ventas_periodo = _ventas_por_producto(hoy - timedelta(days=dias))
    ultima_salida = dict(
        db.session.query(Movimiento.producto_id, func.max(Movimiento.fecha))
        .filter(Movimiento.motivo == "Venta")
        .group_by(Movimiento.producto_id)
        .all()
    )
    stock = _stock_por_producto()
    filas = []
    for p in Producto.query.filter_by(activo=True).all():
        s = int(stock.get(p.id, 0) or 0)
        unidades = ventas_periodo.get(p.id, {}).get("unidades", 0)
        diaria = unidades / dias
        ultima = ultima_salida.get(p.id)
        dias_desde = (hoy - ultima).days if ultima else None
        filas.append(
            {
                "producto": p,
                "stock": s,
                "unidades": unidades,
                "venta_diaria": diaria,
                "dias_inventario": (s / diaria) if diaria > 0 else None,
                "ultima_venta": ultima,
                "dias_sin_venta": dias_desde,
                "valor_stock": s * float(p.costo_unitario or 0),
                "sin_rotacion": s > 0 and (dias_desde is None or dias_desde >= dias_sin),
            }
        )
    filas.sort(key=lambda f: (not f["sin_rotacion"], -(f["valor_stock"])))
    return filas


def sugerencias_reposicion(clases: dict[int, str] | None = None) -> list[dict]:
    clases = clases if clases is not None else mapa_clases_abc()
    stock = _stock_por_producto()
    filas = []
    for p in Producto.query.filter_by(activo=True).all():
        s = int(stock.get(p.id, 0) or 0)
        if p.punto_reorden <= 0 or s > p.punto_reorden:
            continue
        objetivo = p.stock_maximo or p.punto_reorden * 2
        sugerido = max(objetivo - s, 0)
        filas.append(
            {
                "producto": p,
                "stock": s,
                "clase": clases.get(p.id, "C"),
                "sugerido": sugerido,
                "costo_estimado": sugerido * float(p.costo_unitario or 0),
                "estado": "agotado" if s <= 0 else ("critico" if s <= p.stock_minimo else "reponer"),
            }
        )
    orden = {"A": 0, "B": 1, "C": 2}
    filas.sort(key=lambda f: (orden[f["clase"]], f["stock"] - f["producto"].punto_reorden))
    return filas


# ---------------------------------------------------------------------------
# Pedidos no atendidos (KPI de la Propuesta 7)
# ---------------------------------------------------------------------------

def serie_pedidos_no_atendidos(meses: int = 12) -> list[dict]:
    """Por mes: líneas vendidas, líneas no atendidas y % no atendido."""
    inicio = (date.today().replace(day=1) - timedelta(days=31 * (meses - 1))).replace(day=1)
    inicio_dt = datetime.combine(inicio, datetime.min.time())

    vendidas = defaultdict(int)
    for fecha, in db.session.query(Venta.fecha).join(VentaDetalle).filter(Venta.fecha >= inicio_dt).all():
        vendidas[(fecha.year, fecha.month)] += 1
    no_atendidas = defaultdict(int)
    for fecha, in db.session.query(PedidoNoAtendido.fecha).filter(PedidoNoAtendido.fecha >= inicio_dt).all():
        no_atendidas[(fecha.year, fecha.month)] += 1

    serie = []
    anio, mes = inicio.year, inicio.month
    hoy = date.today()
    while (anio, mes) <= (hoy.year, hoy.month):
        v, n = vendidas[(anio, mes)], no_atendidas[(anio, mes)]
        total = v + n
        serie.append(
            {
                "etiqueta": etiqueta_mes(anio, mes),
                "vendidas": v,
                "no_atendidas": n,
                "pct": (n / total * 100) if total else None,
            }
        )
        mes += 1
        if mes > 12:
            mes, anio = 1, anio + 1
    return serie


def linea_base_y_actual(serie: list[dict]) -> dict:
    con_datos = [s for s in serie if s["pct"] is not None]
    if not con_datos:
        return {"base": None, "actual": None, "meta": None, "variacion": None}
    base_meses = con_datos[:3]
    base = sum(s["no_atendidas"] for s in base_meses) / max(sum(s["vendidas"] + s["no_atendidas"] for s in base_meses), 1) * 100
    actual = con_datos[-1]["pct"]
    return {
        "base": base,
        "actual": actual,
        "meta": base / 2,
        "variacion": (actual - base) if actual is not None else None,
        "meses_base": ", ".join(s["etiqueta"] for s in base_meses),
    }


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------

def reporte_clientes() -> list[dict]:
    dias_inactivo = current_app.config["DIAS_CLIENTE_INACTIVO"]
    hoy = datetime.utcnow()
    filas_sql = (
        db.session.query(
            Venta.cliente_id,
            func.count(Venta.id),
            func.sum(Venta.total),
            func.min(Venta.fecha),
            func.max(Venta.fecha),
        )
        .filter(Venta.cliente_id.isnot(None), Venta.estado == "confirmada")
        .group_by(Venta.cliente_id)
        .all()
    )
    datos = {f[0]: f for f in filas_sql}
    filas = []
    for c in Cliente.query.order_by(Cliente.nombre).all():
        f = datos.get(c.id)
        compras = int(f[1]) if f else 0
        total = float(f[2] or 0) if f else 0.0
        primera, ultima = (f[3], f[4]) if f else (None, None)
        frecuencia = ((ultima - primera).days / (compras - 1)) if compras > 1 else None
        dias = (hoy - ultima).days if ultima else None
        if compras == 0:
            estado = "sin compras"
        elif dias is not None and dias > dias_inactivo:
            estado = "inactivo"
        else:
            estado = "activo"
        filas.append(
            {
                "cliente": c,
                "compras": compras,
                "total": total,
                "ticket": total / compras if compras else 0,
                "primera": primera,
                "ultima": ultima,
                "frecuencia": frecuencia,
                "dias_sin_comprar": dias,
                "estado": estado,
            }
        )
    filas.sort(key=lambda r: -r["total"])
    return filas


# ---------------------------------------------------------------------------
# Indicadores del plan de marketing (Tabla 14)
# ---------------------------------------------------------------------------

def indicadores_plan() -> list[dict]:
    hoy = datetime.utcnow()
    inicio_mes = hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    ventas_web = Venta.query.filter(Venta.canal == "Página web", Venta.fecha >= inicio_mes).count()
    ventas_wa = Venta.query.filter(Venta.canal == "WhatsApp", Venta.fecha >= inicio_mes).count()

    clientes_visita = Cliente.query.filter(Cliente.canal_origen == "Visita del vendedor").all()
    con_segundo = sum(1 for c in clientes_visita if c.ventas.count() >= 2)
    kits = sum(1 for c in clientes_visita if c.recibio_kit)

    serie = serie_pedidos_no_atendidos(12)
    base = linea_base_y_actual(serie)

    return [
        {
            "propuesta": "1. Identidad de marca MAZA",
            "indicador": "Canales que usan la nueva identidad",
            "valor": "Registro manual",
            "meta": "Los cinco canales desde el mes 3",
            "fuente": "Revisión de la gerencia",
            "estado": "manual",
        },
        {
            "propuesta": "2. Página web",
            "indicador": "Pedidos que llegan desde la página web (mes actual)",
            "valor": str(ventas_web),
            "meta": "Línea base en el mes 3 y luego aumento trimestral",
            "fuente": "Ventas con canal «Página web»",
            "estado": "auto",
        },
        {
            "propuesta": "3. WhatsApp Business",
            "indicador": "Pedidos por WhatsApp (mes actual)",
            "valor": str(ventas_wa),
            "meta": "Respuesta en menos de 2 horas (se mide en WhatsApp Business)",
            "fuente": "Ventas con canal «WhatsApp»",
            "estado": "auto",
        },
        {
            "propuesta": "4. TikTok educativo",
            "indicador": "Videos publicados y consultas desde TikTok",
            "valor": "Registro manual",
            "meta": "Publicación constante",
            "fuente": "Estadísticas de TikTok",
            "estado": "manual",
        },
        {
            "propuesta": "5. Garantía en el empaque",
            "indicador": "Reclamos de garantía sobre unidades vendidas",
            "valor": "Registro manual",
            "meta": "Menos del 2 %",
            "fuente": "Registro de reclamos",
            "estado": "manual",
        },
        {
            "propuesta": "6. Visitas y kit de bienvenida",
            "indicador": "Tiendas captadas por visita con segundo pedido",
            "valor": f"{con_segundo} de {len(clientes_visita)} (kits entregados: {kits})",
            "meta": "20 visitas por mes; 12 tiendas nuevas con segundo pedido",
            "fuente": "Clientes con origen «Visita del vendedor»",
            "estado": "auto",
        },
        {
            "propuesta": "7. Panel interno de gestión",
            "indicador": "% de pedidos no atendidos por falta de stock",
            "valor": (f"{base['actual']:.1f} %".replace(".", ",") if base["actual"] is not None else "Sin datos"),
            "meta": (
                f"Línea base {base['base']:.1f} % → meta {base['meta']:.1f} %".replace(".", ",")
                if base["base"] is not None
                else "Línea base en los meses 1 a 3; reducirlo a la mitad"
            ),
            "fuente": "Ventas y pedidos no atendidos",
            "estado": "auto",
        },
    ]


# ---------------------------------------------------------------------------
# Inicio
# ---------------------------------------------------------------------------

def kpis_inicio() -> dict:
    hoy = datetime.utcnow()
    inicio_mes = hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    mes_anterior = (inicio_mes - timedelta(days=1)).replace(day=1)

    valor_inventario = (
        db.session.query(func.sum(Existencia.cantidad * Producto.costo_unitario))
        .join(Producto, Producto.id == Existencia.producto_id)
        .filter(Existencia.cantidad > 0)
        .scalar()
        or 0
    )
    ventas_mes = db.session.query(func.sum(Venta.total)).filter(Venta.fecha >= inicio_mes).scalar() or 0
    # mismo tramo del mes anterior (del día 1 al día de hoy) para comparar en igualdad
    try:
        corte_ant = mes_anterior.replace(day=hoy.day) + timedelta(hours=hoy.hour, minutes=hoy.minute)
    except ValueError:
        corte_ant = inicio_mes
    ventas_ant = (
        db.session.query(func.sum(Venta.total))
        .filter(Venta.fecha >= mes_anterior, Venta.fecha < min(corte_ant, inicio_mes))
        .scalar()
        or 0
    )
    stock = _stock_por_producto()
    productos = Producto.query.filter_by(activo=True).all()
    agotados = sum(1 for p in productos if int(stock.get(p.id, 0) or 0) <= 0 and p.punto_reorden > 0)
    bajo_minimo = sum(
        1 for p in productos if 0 < int(stock.get(p.id, 0) or 0) <= p.punto_reorden and p.punto_reorden > 0
    )
    serie = serie_pedidos_no_atendidos(12)
    return {
        "valor_inventario": float(valor_inventario),
        "ventas_mes": float(ventas_mes),
        "ventas_variacion": ((float(ventas_mes) - float(ventas_ant)) / float(ventas_ant) * 100) if ventas_ant else None,
        "productos_activos": len(productos),
        "agotados": agotados,
        "bajo_minimo": bajo_minimo,
        "pct_no_atendido": serie[-1]["pct"] if serie else None,
        "serie_no_atendidos": serie,
    }


def ventas_mensuales(meses: int = 12) -> dict:
    inicio = (date.today().replace(day=1) - timedelta(days=31 * (meses - 1))).replace(day=1)
    totales = defaultdict(float)
    for fecha, total in db.session.query(Venta.fecha, Venta.total).filter(
        Venta.fecha >= datetime.combine(inicio, datetime.min.time())
    ):
        totales[(fecha.year, fecha.month)] += float(total or 0)
    etiquetas, datos = [], []
    anio, mes = inicio.year, inicio.month
    hoy = date.today()
    while (anio, mes) <= (hoy.year, hoy.month):
        etiquetas.append(etiqueta_mes(anio, mes))
        datos.append(round(totales[(anio, mes)], 2))
        mes += 1
        if mes > 12:
            mes, anio = 1, anio + 1
    return {"labels": etiquetas, "data": datos}


def ventas_por_categoria(dias: int = 90) -> dict:
    from app.models import Categoria

    desde = datetime.utcnow() - timedelta(days=dias)
    filas = (
        db.session.query(Categoria.nombre, func.sum(VentaDetalle.cantidad * VentaDetalle.precio_unitario))
        .join(Producto, Producto.categoria_id == Categoria.id)
        .join(VentaDetalle, VentaDetalle.producto_id == Producto.id)
        .join(Venta, Venta.id == VentaDetalle.venta_id)
        .filter(Venta.fecha >= desde)
        .group_by(Categoria.nombre)
        .order_by(func.sum(VentaDetalle.cantidad * VentaDetalle.precio_unitario).desc())
        .all()
    )
    return {"labels": [f[0] for f in filas], "data": [round(float(f[1] or 0), 2) for f in filas]}


def almacenes_activos() -> list[Almacen]:
    return Almacen.query.filter_by(activo=True).order_by(Almacen.id).all()
