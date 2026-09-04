from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import NotaCreditoViewSet, VentaViewSet

router = DefaultRouter()
router.register("ventas", VentaViewSet, basename="venta")
router.register("notas-credito", NotaCreditoViewSet, basename="nota-credito")

urlpatterns = [
    path("", include(router.urls)),
]
