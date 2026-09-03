from django.urls import path

from .views import MiEmpresaView, OnboardingView

urlpatterns = [
    path("onboarding/", OnboardingView.as_view(), name="onboarding"),
    path("mi-empresa/", MiEmpresaView.as_view(), name="mi-empresa"),
]
