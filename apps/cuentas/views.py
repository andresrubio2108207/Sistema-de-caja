from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.generics import GenericAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.empresas.mixins import EmpresaQuerysetMixin

from .models import Usuario
from .permissions import GestionUsuarios, TieneEmpresaActiva
from .serializers import (
    CambiarPasswordSerializer,
    CustomTokenObtainPairSerializer,
    MeSerializer,
    UsuarioSerializer,
)


class CustomTokenObtainPairView(TokenObtainPairView):
    """Login JWT: devuelve access/refresh + los datos del usuario."""

    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"


class MeView(RetrieveAPIView):
    """Datos del usuario autenticado (incluye su empresa y rol)."""

    serializer_class = MeSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class CambiarPasswordView(GenericAPIView):
    """Un usuario cambia SU PROPIA contraseña. Al hacerlo, se revocan todos
    sus refresh tokens vigentes (cierra sesión en cualquier otro terminal
    donde haya quedado logueado)."""

    serializer_class = CambiarPasswordSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        usuario = request.user
        usuario.set_password(serializer.validated_data["password_nueva"])
        usuario.save(update_fields=["password"])

        for token in OutstandingToken.objects.filter(user=usuario):
            BlacklistedToken.objects.get_or_create(token=token)

        return Response({"detail": "Contraseña actualizada. Vuelve a iniciar sesión."})


class UsuarioViewSet(EmpresaQuerysetMixin, viewsets.ModelViewSet):
    """Gestión del personal de la empresa. Solo el dueño.

    El queryset queda acotado a la empresa del usuario por
    ``EmpresaQuerysetMixin``; nunca aparecen usuarios de otro tenant ni el
    superusuario de plataforma (empresa nula).
    """

    queryset = Usuario.objects.all().order_by("id")
    serializer_class = UsuarioSerializer
    permission_classes = [IsAuthenticated, TieneEmpresaActiva, GestionUsuarios]

    def perform_destroy(self, instance):
        if instance == self.request.user:
            raise ValidationError("No puedes eliminar tu propio usuario.")
        super().perform_destroy(instance)
