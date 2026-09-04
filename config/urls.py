from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from apps.cuentas.views import CustomTokenObtainPairView

urlpatterns = [
    path("admin/", admin.site.urls),
    # Documentación OpenAPI
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"
    ),
    # Autenticación JWT
    path(
        "api/auth/token/",
        CustomTokenObtainPairView.as_view(),
        name="token_obtain_pair",
    ),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/token/verify/", TokenVerifyView.as_view(), name="token_verify"),
    # Apps de negocio
    path("api/", include("apps.empresas.urls")),
    path("api/", include("apps.cuentas.urls")),
    path("api/", include("apps.inventario.urls")),
    path("api/", include("apps.terceros.urls")),
    path("api/", include("apps.caja.urls")),
    path("api/", include("apps.ventas.urls")),
]
