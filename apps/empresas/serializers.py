from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from apps.cuentas.models import Usuario

from .models import Empresa


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

    @transaction.atomic
    def create(self, validated_data):
        empresa = Empresa.objects.create(**validated_data["empresa"])
        datos_usuario = validated_data["usuario"]
        usuario = Usuario.objects.create_user(
            username=datos_usuario["username"],
            email=datos_usuario["email"],
            password=datos_usuario["password"],
            first_name=datos_usuario.get("first_name", ""),
            last_name=datos_usuario.get("last_name", ""),
            empresa=empresa,
            rol=Usuario.Rol.DUENO,
        )
        return {"empresa": empresa, "usuario": usuario}


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
