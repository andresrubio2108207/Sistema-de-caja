from rest_framework import serializers

from ..models import Empresa


class MiEmpresaSerializer(serializers.ModelSerializer):
    """Configuración de la empresa propia (solo dueño).

    ``siigo_api_access_key`` es de solo escritura: nunca se devuelve el
    secreto. ``siigo_configurado`` indica si ya hay credenciales cargadas.
    """

    siigo_api_access_key = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    siigo_configurado = serializers.SerializerMethodField()
    resolucion_por_vencer = serializers.SerializerMethodField()
    dias_para_vencer_resolucion = serializers.SerializerMethodField()

    class Meta:
        model = Empresa
        fields = [
            "id",
            "razon_social",
            "nombre_comercial",
            "nit",
            "digito_verificacion",
            "regimen_tributario",
            "direccion",
            "ciudad",
            "telefono",
            "email_facturacion",
            "resolucion_prefijo",
            "resolucion_numero",
            "resolucion_rango_desde",
            "resolucion_rango_hasta",
            "resolucion_vigencia_hasta",
            "resolucion_por_vencer",
            "dias_para_vencer_resolucion",
            "siigo_api_username",
            "siigo_api_access_key",
            "siigo_partner_id",
            "siigo_configurado",
            "activa",
            "creada_en",
        ]
        read_only_fields = ["nit", "digito_verificacion", "activa", "creada_en"]

    def get_siigo_configurado(self, obj) -> bool:
        return bool(obj.siigo_api_username and obj.siigo_api_access_key)

    def get_resolucion_por_vencer(self, obj) -> bool:
        return obj.resolucion_por_vencer()

    def get_dias_para_vencer_resolucion(self, obj) -> int | None:
        return obj.dias_para_vencer_resolucion()
