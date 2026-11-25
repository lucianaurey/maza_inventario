"""Datos base, carga del catálogo y datos de ejemplo.

Los códigos, categorías y aplicaciones vienen de los catálogos reales (MAZA 2026 y AMC 2025).
Los precios, el stock, los clientes y las ventas que genera `generar_demo` son de EJEMPLO:
sirven para probar los reportes y deben reemplazarse por los datos reales de la empresa.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from app import db
from app.models import (
    Almacen,
    Categoria,
    Cliente,
    Compra,
    CompraDetalle,
    Existencia,
    Movimiento,
    PedidoNoAtendido,
    Producto,
    Proveedor,
    Venta,
    VentaDetalle,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

ALMACENES = [
    ("Cochabamba – Supermall", "Cochabamba", "Av. Blanco Galindo, rotonda Perú, centro comercial Supermall, 1er piso of. 33"),
    ("Santa Cruz – Oficina central", "Santa Cruz", "Doble Vía La Guardia entre 4to anillo y calle Jorochito, acera sur"),
]

PROVEEDORES = [
    ("Andina Motor's Company (AMC)", "Perú", 25),
    ("Proveedor de encendido – Asia", "China", 45),
    ("Proveedor de suspensión – Asia", "China", 45),
    ("Fabricante de filtros MAZA Parts", "China", 60),
]

# Rango de precios de EJEMPLO por categoría (costo en Bs)
COSTOS_EJEMPLO = {
    "Bobinas de encendido": (90, 260),
    "Capuchones de bobina": (12, 35),
    "Bujías de encendido": (15, 70),
    "Filtros de aire": (25, 60),
    "Prefiltros": (6, 18),
    "Rotores de distribuidor": (18, 45),
    "Muñones de dirección": (55, 140),
    "Muñones de suspensión": (60, 160),
    "Muñones estabilizadores": (35, 90),
    "Juegos de empaquetaduras": (120, 420),
    "Empaquetaduras de múltiple": (25, 80),
    "Bujes de tijeral": (20, 55),
    "Brazos de cremallera": (80, 190),
    "Mangueras corrugadas": (10, 30),
}

PROVEEDOR_POR_CATEGORIA = {
    "Juegos de empaquetaduras": 0,
    "Empaquetaduras de múltiple": 0,
    "Bobinas de encendido": 1,
    "Capuchones de bobina": 1,
    "Bujías de encendido": 1,
    "Rotores de distribuidor": 1,
    "Muñones de dirección": 2,
    "Muñones de suspensión": 2,
    "Muñones estabilizadores": 2,
    "Bujes de tijeral": 2,
    "Brazos de cremallera": 2,
    "Filtros de aire": 3,
    "Prefiltros": 3,
    "Mangueras corrugadas": 1,
}

NOMBRES_TIENDAS = [
    "Repuestos El Cruce", "Autopartes Quillacollo", "Repuestos San Martín", "Importadora La Cancha",
    "Repuestos Sacaba Motors", "Autorepuestos Tiquipaya", "Repuestos Avenida Petrolera", "Japón Repuestos",
    "Corea Parts Cochabamba", "Repuestos Valle Alto", "Autopartes Blanco Galindo", "Repuestos Cala Cala",
    "Repuestos La Recoleta", "Autorepuestos Colcapirhua", "Repuestos Punata", "China Parts Bolivia",
    "Repuestos Aroma", "Autopartes 6 de Agosto", "Repuestos Vinto", "Repuestos Chimba",
    "Repuestos Santa Cruz Norte", "Autopartes Plan 3000", "Repuestos Los Pozos", "Repuestos Mutualista",
]
NOMBRES_TALLERES = [
    "Taller Mecánico Don Lucho", "Taller Hermanos Rojas", "Taller Express Sacaba", "Servicio Técnico Japonés",
    "Taller El Pistón", "Taller Motor Center",
]
ZONAS = ["Norte", "Sud", "Este", "Oeste", "Centro", "Quillacollo", "Sacaba", "Tiquipaya", "La Cancha"]


def crear_datos_base() -> None:
    for nombre, ciudad, direccion in ALMACENES:
        if not Almacen.query.filter_by(nombre=nombre).first():
            db.session.add(Almacen(nombre=nombre, ciudad=ciudad, direccion=direccion))
    for nombre, pais, dias in PROVEEDORES:
        if not Proveedor.query.filter_by(nombre=nombre).first():
            db.session.add(Proveedor(nombre=nombre, pais=pais, dias_entrega=dias))
    for nombre in COSTOS_EJEMPLO:
        if not Categoria.query.filter_by(nombre=nombre).first():
            db.session.add(Categoria(nombre=nombre))
    db.session.commit()


def cargar_catalogo() -> int:
    crear_datos_base()
    datos = json.loads((DATA_DIR / "productos_catalogo.json").read_text(encoding="utf-8"))
    categorias = {c.nombre: c for c in Categoria.query.all()}
    proveedores = Proveedor.query.order_by(Proveedor.id).all()
    existentes = {codigo for (codigo,) in db.session.query(Producto.codigo).all()}
    nuevos = 0
    for item in datos:
        if item["codigo"] in existentes:
            continue
        categoria = categorias.get(item["categoria"])
        if categoria is None:
            categoria = Categoria(nombre=item["categoria"])
            db.session.add(categoria)
            db.session.flush()
            categorias[categoria.nombre] = categoria
        idx = PROVEEDOR_POR_CATEGORIA.get(item["categoria"])
        db.session.add(
            Producto(
                codigo=item["codigo"],
                codigos_alternos=item.get("codigos_alt") or None,
                nombre=item["nombre"],
                categoria_id=categoria.id,
                marca=item.get("marca") or "Importada",
                marca_vehiculo=item.get("marca_vehiculo"),
                aplicacion=item.get("aplicacion"),
                atributos=item.get("atributos") or None,
                pagina_catalogo=item.get("pagina_catalogo"),
                fuente=item.get("fuente"),
                proveedor_id=proveedores[idx].id if idx is not None and idx < len(proveedores) else None,
            )
        )
        existentes.add(item["codigo"])
        nuevos += 1
    db.session.commit()
    return nuevos


def _limpiar_transacciones() -> None:
    for modelo in (VentaDetalle, Venta, CompraDetalle, Compra, Movimiento, PedidoNoAtendido, Existencia, Cliente):
        db.session.query(modelo).delete()
    db.session.commit()


def generar_demo(meses: int = 12, semilla: int = 2026) -> dict:
    """Simula `meses` de operación para que los reportes tengan datos. TODO ES DE EJEMPLO."""
    rnd = random.Random(semilla)
    cargar_catalogo()
    _limpiar_transacciones()

    almacenes = Almacen.query.order_by(Almacen.id).all()
    cbba, scz = almacenes[0], almacenes[1]
    productos = Producto.query.filter_by(activo=True).all()

    # --- precios de ejemplo y popularidad (Pareto) ---
    popularidad = {}
    for p in productos:
        bajo, alto = COSTOS_EJEMPLO.get(p.categoria.nombre, (20, 100))
        costo = Decimal(str(round(rnd.uniform(bajo, alto), 1)))
        p.costo_unitario = costo
        p.precio_mayorista = (costo * Decimal("1.35")).quantize(Decimal("1"))
        p.precio_sugerido = (costo * Decimal("1.65")).quantize(Decimal("1"))
        r = rnd.random()
        if r < 0.10:
            peso = rnd.uniform(8, 20)      # pocos productos muy pedidos
        elif r < 0.35:
            peso = rnd.uniform(1.5, 5)
        elif r < 0.88:
            peso = rnd.uniform(0.1, 1)
        else:
            peso = 0                       # nunca se vende: stock inmovilizado
        if p.categoria.nombre == "Juegos de empaquetaduras":
            peso *= 0.25  # juegos completos: caros y de menor rotación que el encendido
        if p.marca == "MAZA Parts":
            peso = max(peso, rnd.uniform(3, 10))
        popularidad[p.id] = peso
    db.session.flush()

    # parámetros de stock según la demanda esperada
    dias_total = int(meses * 30.4)
    unidades_dia = 7 * 2.4 * 2.5  # ventas por día x líneas por venta x unidades por línea
    suma_pesos = sum(popularidad.values()) or 1
    demanda_diaria = {pid: unidades_dia * w / suma_pesos for pid, w in popularidad.items()}
    for p in productos:
        d = demanda_diaria[p.id]
        p.stock_minimo = max(int(round(d * 8)), 3 if d > 0 else 0)
        p.punto_reorden = max(int(round(d * 30)), 8 if d > 0 else 0)
        p.stock_maximo = max(int(round(d * 75)), 20 if d > 0 else 0)

    # --- clientes de ejemplo ---
    clientes = []
    hoy = datetime.utcnow().replace(hour=9, minute=0, second=0, microsecond=0)
    anio, mes = hoy.year, hoy.month - meses
    while mes <= 0:
        mes, anio = mes + 12, anio - 1
    inicio = hoy.replace(year=anio, month=mes, day=1)  # el historial empieza un día 1 para que la línea base use meses completos
    dias_total = (hoy - inicio).days
    for i, nombre in enumerate(NOMBRES_TIENDAS):
        ciudad = "Santa Cruz" if "Santa Cruz" in nombre or nombre in ("Autopartes Plan 3000", "Repuestos Los Pozos", "Repuestos Mutualista") else "Cochabamba"
        origen = "Visita del vendedor" if i % 4 == 0 else rnd.choice(["WhatsApp", "Tienda Supermall", "Página web"])
        registro = inicio + timedelta(days=rnd.randint(0, dias_total - 30) if origen == "Visita del vendedor" else rnd.randint(0, 60))
        clientes.append(Cliente(
            nombre=nombre, tipo="Tienda de repuestos", ciudad=ciudad, zona=rnd.choice(ZONAS),
            telefono=f"7{rnd.randint(1000000, 9999999)}", canal_origen=origen,
            registrado_whatsapp=rnd.random() < 0.7, recibio_kit=origen == "Visita del vendedor",
            fecha_registro=registro.date(), notas="Cliente de ejemplo",
        ))
    for nombre in NOMBRES_TALLERES:
        clientes.append(Cliente(
            nombre=nombre, tipo="Taller mecánico", ciudad="Cochabamba", zona=rnd.choice(ZONAS),
            telefono=f"6{rnd.randint(1000000, 9999999)}", canal_origen="Tienda Supermall",
            fecha_registro=(inicio + timedelta(days=rnd.randint(0, 90))).date(), notas="Cliente de ejemplo",
        ))
    db.session.add_all(clientes)
    db.session.flush()

    # --- simulación día a día en memoria ---
    stock = defaultdict(int)  # (producto_id, almacen_id) -> cantidad
    movimientos, ventas, compras, no_atendidos = [], [], [], []
    por_id = {p.id: p for p in productos}
    ids = [p.id for p in productos if popularidad[p.id] > 0]
    pesos = [popularidad[i] for i in ids]
    proveedores = {p.id: p.proveedor_id for p in productos}

    def mov(fecha, pid, alm, cantidad, tipo, motivo, ref, costo):
        stock[(pid, alm)] += cantidad
        movimientos.append(dict(fecha=fecha, producto_id=pid, almacen_id=alm, tipo=tipo, motivo=motivo,
                                cantidad=cantidad, saldo=stock[(pid, alm)], costo_unitario=costo, referencia=ref))

    n_compra = 0
    # stock inicial
    lineas_ini = defaultdict(list)
    for p in productos:
        for alm, factor in ((cbba.id, 0.65), (scz.id, 0.35)):
            if popularidad[p.id] == 0:
                cant = rnd.randint(1, 6) if alm == cbba.id else rnd.randint(0, 3)
            else:
                cant = int(round(p.stock_maximo * factor * rnd.uniform(0.5, 1.0)))
            if cant > 0:
                lineas_ini[alm].append((p.id, cant))
    for alm, lineas in lineas_ini.items():
        n_compra += 1
        numero = f"C-{n_compra:06d}"
        compras.append(dict(numero=numero, fecha=inicio, almacen_id=alm, proveedor_id=None,
                            documento="Inventario inicial", lineas=lineas))
        for pid, cant in lineas:
            mov(inicio, pid, alm, cant, "entrada", "Inventario inicial", numero, por_id[pid].costo_unitario)

    n_venta = 0
    canales_peso = [("WhatsApp", 45), ("Tienda Supermall", 30), ("Visita del vendedor", 12), ("Página web", 6), ("Teléfono", 7)]
    pedidos_pendientes = []  # (fecha_llegada, almacen, [(pid, cant)])
    for dia in range(1, dias_total + 1):
        fecha_dia = inicio + timedelta(days=dia)
        if fecha_dia.weekday() == 6:
            continue
        # llegan compras
        for llegada in [x for x in pedidos_pendientes if x[0] <= fecha_dia]:
            pedidos_pendientes.remove(llegada)
            n_compra += 1
            numero = f"C-{n_compra:06d}"
            compras.append(dict(numero=numero, fecha=llegada[0], almacen_id=llegada[1], proveedor_id=llegada[3],
                                documento=f"Factura {rnd.randint(1000, 9999)}", lineas=llegada[2]))
            for pid, cant in llegada[2]:
                mov(llegada[0], pid, llegada[1], cant, "entrada", "Compra", numero, por_id[pid].costo_unitario)
        # ventas del día
        estacional = 1.15 if fecha_dia.month in (11, 12, 1) else 1.0
        for _ in range(max(1, int(rnd.gauss(7, 2) * estacional))):
            alm = cbba.id if rnd.random() < 0.7 else scz.id
            clientes_ciudad = [c for c in clientes if c.ciudad == ("Cochabamba" if alm == cbba.id else "Santa Cruz")
                               and c.fecha_registro <= fecha_dia.date()]
            cliente = rnd.choice(clientes_ciudad) if clientes_ciudad and rnd.random() < 0.8 else None
            canal = rnd.choices([c for c, _ in canales_peso], [w for _, w in canales_peso])[0]
            fecha_venta = fecha_dia + timedelta(minutes=rnd.randint(0, 540))
            lineas = []
            for pid in set(rnd.choices(ids, pesos, k=rnd.randint(1, 4))):
                cant = rnd.choice([1, 1, 1, 2, 2, 3, 4, 6])
                if stock[(pid, alm)] >= cant:
                    lineas.append((pid, cant))
                else:
                    no_atendidos.append(dict(
                        fecha=fecha_venta, producto_id=pid, cantidad=cant,
                        tipo_cliente=cliente.tipo if cliente else "Conductor",
                        cliente_id=cliente.id if cliente else None, canal=canal,
                        motivo="Sin stock", almacen_id=alm,
                    ))
            if not lineas:
                continue
            n_venta += 1
            numero = f"V-{n_venta:06d}"
            tipo_precio = "minorista" if cliente is None else "mayorista"
            detalle = []
            total = Decimal("0")
            for pid, cant in lineas:
                p = por_id[pid]
                precio = p.precio_sugerido if tipo_precio == "minorista" else p.precio_mayorista
                detalle.append((pid, cant, precio, p.costo_unitario))
                total += precio * cant
                mov(fecha_venta, pid, alm, -cant, "salida", "Venta", numero, p.costo_unitario)
            ventas.append(dict(numero=numero, fecha=fecha_venta, cliente_id=cliente.id if cliente else None,
                               almacen_id=alm, canal=canal, tipo_precio=tipo_precio, total=total, detalle=detalle))
        # pedido de reposición semanal (los lunes). En la primera mitad del año la
        # reposición es irregular; en la segunda se simula el efecto del panel (lista «Siempre Hay»).
        avance = dia / dias_total
        prob_reponer = 0.55 if avance < 0.5 else 0.95
        demora_rango = (15, 45) if avance < 0.5 else (8, 22)
        if fecha_dia.weekday() == 0:
            for alm in (cbba.id, scz.id):
                por_proveedor = defaultdict(list)
                en_camino = {pid for x in pedidos_pendientes if x[1] == alm for pid, _ in x[2]}
                for p in productos:
                    if popularidad[p.id] == 0 or p.id in en_camino:
                        continue
                    factor = 0.65 if alm == cbba.id else 0.35
                    if stock[(p.id, alm)] <= p.punto_reorden * factor and rnd.random() < prob_reponer:
                        cant = max(int(p.stock_maximo * factor) - stock[(p.id, alm)], 1)
                        por_proveedor[proveedores[p.id]].append((p.id, cant))
                for prov_id, lineas in por_proveedor.items():
                    demora = rnd.randint(*demora_rango)
                    pedidos_pendientes.append((fecha_dia + timedelta(days=demora), alm, lineas, prov_id))

    # --- guardar ---
    for c in compras:
        compra = Compra(numero=c["numero"], fecha=c["fecha"], almacen_id=c["almacen_id"], proveedor_id=c["proveedor_id"],
                        documento=c["documento"], nota="Dato de ejemplo")
        total = Decimal("0")
        for pid, cant in c["lineas"]:
            costo = por_id[pid].costo_unitario
            compra.detalles.append(CompraDetalle(producto_id=pid, cantidad=cant, costo_unitario=costo))
            total += costo * cant
        compra.total = total
        db.session.add(compra)
    for v in ventas:
        venta = Venta(numero=v["numero"], fecha=v["fecha"], cliente_id=v["cliente_id"], almacen_id=v["almacen_id"],
                      canal=v["canal"], tipo_precio=v["tipo_precio"], total=v["total"], nota="Dato de ejemplo")
        for pid, cant, precio, costo in v["detalle"]:
            venta.detalles.append(VentaDetalle(producto_id=pid, cantidad=cant, precio_unitario=precio, costo_unitario=costo))
        db.session.add(venta)
    db.session.bulk_insert_mappings(Movimiento, movimientos)
    db.session.bulk_insert_mappings(PedidoNoAtendido, no_atendidos)
    for (pid, alm), cant in stock.items():
        db.session.add(Existencia(producto_id=pid, almacen_id=alm, cantidad=cant,
                                  ubicacion=f"Estante {rnd.choice('ABCDEFG')}-{rnd.randint(1, 12)}"))
    db.session.commit()
    return {
        "productos": len(productos),
        "clientes": len(clientes),
        "ventas": len(ventas),
        "compras": len(compras),
        "movimientos": len(movimientos),
        "pedidos_no_atendidos": len(no_atendidos),
    }
