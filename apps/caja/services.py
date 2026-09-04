"""Reglas de negocio de apertura/cierre de turno."""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.cuentas.models import Usuario

from .models import Caja, TurnoCaja


class CajaOcupada(Exception):
    """La caja ya tiene un turno abierto."""


class TurnoYaAbierto(Exception):
    """El usuario ya tiene un turno abierto en otra caja."""


class TurnoYaCerrado(Exception):
    pass


@transaction.atomic
def abrir_turno(*, empresa, caja: Caja, cajero, saldo_inicial: Decimal) -> TurnoCaja:
    # Se bloquean caja Y cajero: sin el lock del cajero, dos peticiones casi
    # simultáneas del mismo usuario (doble clic) podrían pasar ambas el
    # `.exists()` de abajo antes de que la primera confirme, y abrir dos
    # turnos igual. El lock serializa esas dos peticiones.
    Usuario.objects.select_for_update().get(pk=cajero.pk)
    caja = Caja.objects.select_for_update().get(pk=caja.pk)

    if TurnoCaja.objects.filter(
        empresa=empresa, cajero=cajero, estado=TurnoCaja.Estado.ABIERTO
    ).exists():
        raise TurnoYaAbierto("Ya tienes un turno de caja abierto.")

    if TurnoCaja.objects.filter(caja=caja, estado=TurnoCaja.Estado.ABIERTO).exists():
        raise CajaOcupada("Esa caja ya tiene un turno abierto por otro usuario.")

    return TurnoCaja.objects.create(
        empresa=empresa,
        caja=caja,
        cajero=cajero,
        estado=TurnoCaja.Estado.ABIERTO,
        saldo_inicial=saldo_inicial,
    )


@transaction.atomic
def cerrar_turno(turno: TurnoCaja, saldo_final_declarado: Decimal) -> TurnoCaja:
    from apps.ventas.models import PagoVenta, Venta  # evita import circular a nivel de módulo

    turno = TurnoCaja.objects.select_for_update().get(pk=turno.pk)
    if turno.estado == TurnoCaja.Estado.CERRADO:
        raise TurnoYaCerrado("Este turno ya está cerrado.")

    # El efectivo esperado sale de los PAGOS en efectivo, no de
    # Venta.medio_pago: una venta MIXTO (ej. mitad efectivo, mitad tarjeta)
    # solo debe sumar a caja física la parte que realmente fue en efectivo.
    total_efectivo = (
        PagoVenta.objects.filter(
            venta__turno=turno,
            venta__estado=Venta.Estado.COMPLETADA,
            medio_pago=Venta.MedioPago.EFECTIVO,
        ).aggregate(t=Sum("monto"))["t"]
        or Decimal("0")
    )
    turno.saldo_final_calculado = turno.saldo_inicial + total_efectivo
    turno.saldo_final_declarado = saldo_final_declarado
    turno.estado = TurnoCaja.Estado.CERRADO
    turno.cerrado_en = timezone.now()
    turno.save(
        update_fields=[
            "saldo_final_calculado",
            "saldo_final_declarado",
            "estado",
            "cerrado_en",
        ]
    )
    return turno


def resumen_ventas(turno: TurnoCaja) -> dict:
    from apps.ventas.services import resumen_de_ventas  # evita import circular

    return resumen_de_ventas(turno.ventas.all())
