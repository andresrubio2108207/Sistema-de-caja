from rest_framework.generics import GenericAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView

from ..serializers import CambiarPasswordSerializer, CustomTokenObtainPairSerializer, MeSerializer
from ..services import cambiar_password


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
        cambiar_password(
            usuario=request.user,
            password_nueva=serializer.validated_data["password_nueva"],
        )
        return Response({"detail": "Contraseña actualizada. Vuelve a iniciar sesión."})
