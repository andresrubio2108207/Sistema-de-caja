from ..models import TurnoCaja


def resumen_ventas(turno: TurnoCaja) -> dict:
    from apps.ventas.services import resumen_de_ventas  # evita import circular

    return resumen_de_ventas(turno.ventas.all())
