from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.cuentas.models import Usuario

from ..models import Empresa
from ..services import crear_empresa_y_dueno


class OnboardingEmpresaSerializer(serializers.ModelSerializer):
    """Datos de la empresa en el alta. Resolución DIAN y credenciales Siigo son
    opcionales aquí; se completan luego en /api/mi-empresa/."""

    class Meta:
        model = Empresa
        fields = [
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
            "siigo_api_username",
            "siigo_api_access_key",
            "siigo_partner_id",
        ]


class OnboardingUsuarioSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(
        write_only=True, validators=[validate_password], style={"input_type": "password"}
    )
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_username(self, value):
        if Usuario.objects.filter(username=value).exists():
            raise serializers.ValidationError("Ese nombre de usuario ya existe.")
        return value


class OnboardingSerializer(serializers.Serializer):
    """Crea, en una transacción, la Empresa (tenant) y su primer Usuario
    (rol = dueño)."""

    empresa = OnboardingEmpresaSerializer()
    usuario = OnboardingUsuarioSerializer()

    def create(self, validated_data):
        return crear_empresa_y_dueno(
            datos_empresa=validated_data["empresa"],
            datos_usuario=validated_data["usuario"],
        )
