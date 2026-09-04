from datetime import date

from django.core.validators import MaxLengthValidator
from django.db import models

from ..fields import EncryptedTextField


class Empresa(models.Model):
    """El tenant. Cada empresa opera de forma aislada sobre la misma instalación.

    Nunca se borra físicamente: se marca ``activa = False`` (las facturas
    electrónicas deben conservarse mínimo 5 años por ley).
    """

    class Regimen(models.TextChoices):
        RESPONSABLE_IVA = "responsable_iva", "Responsable de IVA"
        NO_RESPONSABLE_IVA = "no_responsable_iva", "No responsable de IVA"
        REGIMEN_SIMPLE = "regimen_simple", "Régimen simple de tributación"

    razon_social = models.CharField(max_length=255)
    nombre_comercial = models.CharField(max_length=255, blank=True)
    nit = models.CharField(max_length=15, unique=True)
    digito_verificacion = models.CharField(max_length=1)
    regimen_tributario = models.CharField(max_length=25, choices=Regimen.choices)

    direccion = models.CharField(max_length=255, blank=True)
    ciudad = models.CharField(max_length=100, blank=True)
    telefono = models.CharField(max_length=50, blank=True)
    email_facturacion = models.EmailField(max_length=254, blank=True)

    # Resolución de facturación DIAN (el rango se vincula a Siigo desde el
    # portal de la DIAN; aquí solo se guarda para alertar por agotamiento/vencimiento).
    resolucion_prefijo = models.CharField(max_length=10, blank=True)
    resolucion_numero = models.CharField(max_length=50, blank=True)
    resolucion_rango_desde = models.PositiveIntegerField(null=True, blank=True)
    resolucion_rango_hasta = models.PositiveIntegerField(null=True, blank=True)
    resolucion_vigencia_hasta = models.DateField(null=True, blank=True)

    # Credenciales de Siigo propias de ESTA empresa. Cifradas en reposo
    # (Fernet, ver apps.empresas.fields.EncryptedTextField) — nunca en texto
    # plano en la base de datos.
    siigo_api_username = EncryptedTextField(
        blank=True, validators=[MaxLengthValidator(255)]
    )
    siigo_api_access_key = EncryptedTextField(
        blank=True, validators=[MaxLengthValidator(255)]
    )
    siigo_partner_id = EncryptedTextField(
        blank=True, validators=[MaxLengthValidator(100)]
    )

    activa = models.BooleanField(default=True)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "empresa"
        verbose_name_plural = "empresas"
        ordering = ["razon_social"]

    def __str__(self):
        return f"{self.razon_social} ({self.nit})"

    # --- Alertas de resolución DIAN (sección 8 del prompt maestro) ---
    # El rango de numeración se agota según facturas EMITIDAS; eso solo se
    # puede calcular cuando exista el módulo de facturación (diferido). Por
    # ahora la única alerta posible con los datos que hay es la de vigencia.
    DIAS_ALERTA_VIGENCIA_RESOLUCION = 30

    def dias_para_vencer_resolucion(self):
        if not self.resolucion_vigencia_hasta:
            return None
        return (self.resolucion_vigencia_hasta - date.today()).days

    def resolucion_por_vencer(self):
        dias = self.dias_para_vencer_resolucion()
        return dias is not None and dias <= self.DIAS_ALERTA_VIGENCIA_RESOLUCION
