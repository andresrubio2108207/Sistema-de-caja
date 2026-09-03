from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from apps.cuentas.views import CustomTokenObtainPairView

urlpatterns = [
    path("admin/", admin.site.urls),
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
]
