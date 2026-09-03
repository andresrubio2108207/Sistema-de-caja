from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import MeView, UsuarioViewSet

router = DefaultRouter()
router.register("usuarios", UsuarioViewSet, basename="usuario")

urlpatterns = [
    path("auth/me/", MeView.as_view(), name="me"),
    path("", include(router.urls)),
]
