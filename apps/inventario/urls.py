from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CategoriaViewSet, MovimientoInventarioViewSet, ProductoViewSet

router = DefaultRouter()
router.register("categorias", CategoriaViewSet, basename="categoria")
router.register("productos", ProductoViewSet, basename="producto")
router.register(
    "movimientos-inventario", MovimientoInventarioViewSet, basename="movimiento-inventario"
)

urlpatterns = [
    path("", include(router.urls)),
]
