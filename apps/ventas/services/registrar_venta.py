"""Registro de una venta: crea Venta + DetalleVenta + PagoVenta, calcula
totales y descuenta stock vía el kardex — todo en una sola transacción.

Pagos: una venta admite uno o más ``PagoVenta`` (ej. $20.000 efectivo +
$30.000 tarjeta). La suma de los pagos debe ser exactamente igual al total
de la venta. ``Venta.medio_pago`` lo calcula el servidor: el único medio si
hay un solo pago, o ``MIXTO`` si hay dos o más.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from apps.caja.models import TurnoCaja
from apps.inventario.models import MovimientoInventario, Producto
from apps.inventario.services import aplicar_movimiento

from ..models import DetalleVenta, PagoVenta, Venta
from .comun import DOS_DECIMALES, _dividir_iva
from .excepciones import PagoInvalido, ProductoInvalido, TurnoNoAbierto


@transaction.atomic
def registrar_venta(*, empresa, cajero, cliente, es_de_contado, lineas, pagos):
    if not lineas:
        raise ProductoInvalido("La venta debe tener al menos una línea.")
    if not pagos:
        raise PagoInvalido("La venta debe tener al menos un pago.")

    turno = (
        TurnoCaja.objects.select_for_update()
        .filter(empresa=empresa, cajero=cajero, estado=TurnoCaja.Estado.ABIERTO)
        .first()
    )
    if turno is None:
        raise TurnoNoAbierto("Debes abrir un turno de caja antes de registrar ventas.")

    # Se bloquean TODOS los productos involucrados de una vez, en un orden
    # determinístico (por pk). Evita interbloqueos entre dos checkouts
    # concurrentes que comparten productos pero los procesan en orden distinto.
    ids_producto = sorted({linea["producto"].pk for linea in lineas})
    productos = {
        p.pk: p
        for p in Producto.objects.select_for_update().filter(pk__in=ids_producto).order_by("pk")
    }
    for pk in ids_producto:
        if pk not in productos or productos[pk].empresa_id != empresa.id:
            raise ProductoInvalido(f"El producto {pk} no pertenece a tu empresa.")
        if not productos[pk].activo:
            raise ProductoInvalido(f"El producto {productos[pk].codigo} está inactivo.")

    venta = Venta.objects.create(
        empresa=empresa,
        turno=turno,
        cajero=cajero,
        cliente=cliente,
        medio_pago=Venta.MedioPago.EFECTIVO,  # placeholder; se fija abajo con los pagos reales
        es_de_contado=es_de_contado,
    )

    subtotal = Decimal("0")
    total_iva = Decimal("0")
    total = Decimal("0")

    for linea in lineas:
        producto = productos[linea["producto"].pk]
        cantidad = linea["cantidad"]

        precio_unitario = producto.precio_venta  # foto del catálogo, IVA incluido
        total_linea = (cantidad * precio_unitario).quantize(
            DOS_DECIMALES, rounding=ROUND_HALF_UP
        )
        base_linea, iva_linea = _dividir_iva(total_linea, producto.porcentaje_iva)

        DetalleVenta.objects.create(
            venta=venta,
            producto=producto,
            cantidad=cantidad,
            precio_unitario=precio_unitario,
            porcentaje_iva=producto.porcentaje_iva,
        )

        if producto.controla_stock:
            aplicar_movimiento(
                producto=producto,
                tipo=MovimientoInventario.Tipo.VENTA,
                cantidad=-cantidad,
                venta=venta,
                usuario=cajero,
                motivo=f"Venta #{venta.pk}",
            )

        subtotal += base_linea
        total_iva += iva_linea
        total += total_linea

    total_pagado = sum((p["monto"] for p in pagos), Decimal("0"))
    if total_pagado != total:
        raise PagoInvalido(
            f"Los pagos suman {total_pagado} pero la venta es {total}."
        )

    for pago in pagos:
        PagoVenta.objects.create(
            venta=venta, medio_pago=pago["medio_pago"], monto=pago["monto"]
        )

    venta.subtotal = subtotal
    venta.total_iva = total_iva
    venta.total = total
    venta.medio_pago = (
        pagos[0]["medio_pago"] if len(pagos) == 1 else Venta.MedioPago.MIXTO
    )
    venta.save(update_fields=["subtotal", "total_iva", "total", "medio_pago"])
    return venta
