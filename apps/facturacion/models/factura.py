from django.db import models


class Factura(models.Model):
    """Factura electrónica de una venta, emitida ante la DIAN a través de Siigo.

    1 factura por venta (``venta`` es OneOne). El envío real ocurre en una
    tarea Celery con reintentos; si se agotan, pasa a ``en_contingencia`` y una
    tarea periódica la reconsulta más tarde.
    """

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        ACEPTADA = "aceptada", "Aceptada"
        RECHAZADA = "rechazada", "Rechazada"
        EN_CONTINGENCIA = "en_contingencia", "En contingencia"
        ANULADA = "anulada", "Anulada"

    empresa = models.ForeignKey(
        "empresas.Empresa", on_delete=models.PROTECT, related_name="facturas"
    )
    venta = models.OneToOneField(
        "ventas.Venta", on_delete=models.PROTECT, related_name="factura"
    )
    estado = models.CharField(
        max_length=20, choices=Estado.choices, default=Estado.PENDIENTE
    )

    cufe = models.CharField(
        max_length=200, blank=True, help_text="Lo asigna la DIAN vía el PT."
    )
    numero_factura = models.CharField(max_length=50, blank=True)
    url_pdf = models.URLField(max_length=200, blank=True)
    url_xml = models.URLField(max_length=200, blank=True)
    codigo_qr = models.TextField(blank=True)
    motivo_rechazo = models.TextField(blank=True)

    respuesta_proveedor = models.JSONField(
        null=True, blank=True, help_text="Payload crudo del PT, para auditoría."
    )
    proveedor_usado = models.CharField(
        max_length=20,
        blank=True,
        default="siigo",
        help_text="Histórico: con qué proveedor se facturó esta venta.",
    )

    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "factura electrónica"
        verbose_name_plural = "facturas electrónicas"
        ordering = ["-creada_en"]
        indexes = [
            models.Index(
                fields=["empresa", "estado"], name="ix_factura_empresa_estado"
            ),
        ]

    def __str__(self):
        return self.numero_factura or f"Factura pendiente (venta {self.venta_id})"
