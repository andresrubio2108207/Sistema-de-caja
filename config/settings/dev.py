"""Entorno de desarrollo local."""
from .base import *  # noqa: F401,F403
from .base import env

DEBUG = True

ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "[::1]"]
)

# En local se permite cualquier origen para facilitar el trabajo con el front.
CORS_ALLOW_ALL_ORIGINS = True

# Emails a consola en desarrollo.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
