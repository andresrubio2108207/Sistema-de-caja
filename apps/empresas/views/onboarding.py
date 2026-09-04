from rest_framework import status
from rest_framework.generics import CreateAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.cuentas.serializers import CustomTokenObtainPairSerializer, MeSerializer

from ..serializers import OnboardingSerializer


class OnboardingView(CreateAPIView):
    """Alta pública de una empresa nueva + su usuario dueño.

    Devuelve tokens JWT listos para entrar (con claims rol y empresa_id).
    """

    serializer_class = OnboardingSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "onboarding"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resultado = serializer.save()
        usuario = resultado["usuario"]

        refresh = CustomTokenObtainPairSerializer.get_token(usuario)
        return Response(
            {
                "usuario": MeSerializer(usuario).data,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_201_CREATED,
        )
