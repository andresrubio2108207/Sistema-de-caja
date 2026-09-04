from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ClienteViewSet

router = DefaultRouter()
router.register("clientes", ClienteViewSet, basename="cliente")

urlpatterns = [
    path("", include(router.urls)),
]
