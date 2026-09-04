from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CajaViewSet, TurnoCajaViewSet

router = DefaultRouter()
router.register("cajas", CajaViewSet, basename="caja")
router.register("turnos", TurnoCajaViewSet, basename="turno")

urlpatterns = [
    path("", include(router.urls)),
]
