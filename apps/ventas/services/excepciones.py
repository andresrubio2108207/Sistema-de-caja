class TurnoNoAbierto(Exception):
    """El cajero no tiene un turno abierto: no se puede vender."""


class ProductoInvalido(Exception):
    """Un producto de la venta no es vendible tal cual viene (inactivo, de
    otra empresa, etc.)."""


class PagoInvalido(Exception):
    """Los pagos no cuadran con el total de la venta."""


class VentaYaAnulada(Exception):
    pass


class AnulacionNoPermitida(Exception):
    """El turno de la venta ya cerró: anular a esta altura descuadraría un
    arqueo ya hecho. Para eso está la nota crédito (parcial o total, sin
    importar si el turno sigue abierto)."""


class NotaCreditoInvalida(Exception):
    """La nota crédito no se puede emitir tal cual viene (venta anulada,
    línea ajena, cantidad mayor a la disponible, etc.)."""
