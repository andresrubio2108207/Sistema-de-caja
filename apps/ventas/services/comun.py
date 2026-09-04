"""Helpers compartidos por los services de ventas.

Convención de precios: ``Producto.precio_venta`` YA INCLUYE IVA (es lo que
paga el cliente). La base gravable se calcula hacia atrás por línea:
``base = total_linea / (1 + %iva/100)``, ``iva = total_linea - base``. El
%IVA es el de CADA producto (``producto.porcentaje_iva`` o, ya vendido, el
snapshot en ``DetalleVenta.porcentaje_iva``), nunca uno fijo global — así
conviven gravados a distintas tarifas con exentos/excluidos (0%).
"""
from decimal import ROUND_HALF_UP, Decimal

DOS_DECIMALES = Decimal("0.01")


def _dividir_iva(total_linea: Decimal, porcentaje_iva: Decimal) -> tuple[Decimal, Decimal]:
    """``total_linea`` ya incluye IVA. Devuelve ``(base, iva)`` en 2
    decimales, garantizando ``base + iva == total_linea`` exactamente."""
    base = (total_linea / (Decimal("1") + porcentaje_iva / Decimal("100"))).quantize(
        DOS_DECIMALES, rounding=ROUND_HALF_UP
    )
    iva = total_linea - base
    return base, iva
