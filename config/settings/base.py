"""
Configuración común a todos los entornos.

Los valores sensibles o que cambian por entorno se leen de variables de entorno
(archivo .env en local) mediante django-environ. No pongas secretos aquí.
"""
from datetime import timedelta
from pathlib import Path

import environ

# BASE_DIR apunta a la raíz del proyecto (donde vive manage.py).
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")

# --------------------------------------------------------------------------- #
# Núcleo
# --------------------------------------------------------------------------- #
SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Terceros
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "corsheaders",
    "django_celery_results",
    "django_celery_beat",
    # Apps del proyecto (bajo apps/)
    "apps.empresas",
    "apps.cuentas",
    "apps.inventario",
    "apps.terceros",
    "apps.caja",
    "apps.ventas",
    "apps.facturacion",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --------------------------------------------------------------------------- #
# Base de datos — MySQL 8, shared schema multi-tenant
# --------------------------------------------------------------------------- #
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD", default=""),
        "HOST": env("DB_HOST", default="127.0.0.1"),
        "PORT": env("DB_PORT", default="3306"),
        "CONN_MAX_AGE": env.int("DB_CONN_MAX_AGE", default=60),
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }
}

# --------------------------------------------------------------------------- #
# Autenticación
# --------------------------------------------------------------------------- #
AUTH_USER_MODEL = "cuentas.Usuario"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------------------------------------------------------- #
# Internacionalización
# --------------------------------------------------------------------------- #
LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------- #
# Estáticos
# --------------------------------------------------------------------------- #
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------- #
# Django REST Framework + JWT
# --------------------------------------------------------------------------- #
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    # Sin throttle global: se aplica por vista (ver onboarding/login) donde
    # el costo de un abuso es alto (fuerza bruta, alta masiva de tenants).
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {
        "onboarding": "5/hour",
        # Ojo: para el login el throttle es por IP (aún no hay usuario
        # autenticado). Varios cajeros de la MISMA tienda comparten IP
        # pública, así que el límite debe tolerar un cambio de turno con
        # varias terminales entrando casi a la vez, no solo un usuario.
        "login": "20/min",
    },
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "POS DIAN API",
    "DESCRIPTION": (
        "API del POS multi-tenant. Todo endpoint de negocio requiere JWT "
        "(Authorization: Bearer <access>) salvo /api/onboarding/ y "
        "/api/auth/token/."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # Los ViewSets acotan el queryset por empresa en tiempo de request
    # (EmpresaQuerysetMixin); en el arranque (sin request) no hay empresa,
    # así que el esquema se genera igual mostrando el queryset "base".
    "COMPONENT_SPLIT_REQUEST": True,
}

# --------------------------------------------------------------------------- #
# Celery / Redis
# --------------------------------------------------------------------------- #
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="django-db")
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_TASK_TRACK_STARTED = True
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)

# --------------------------------------------------------------------------- #
# Facturación electrónica (reintentos / contingencia)
# --------------------------------------------------------------------------- #
FACTURACION_MAX_REINTENTOS = env.int("FACTURACION_MAX_REINTENTOS", default=5)
FACTURACION_BACKOFF_BASE_SEGUNDOS = env.int(
    "FACTURACION_BACKOFF_BASE_SEGUNDOS", default=60
)

# --------------------------------------------------------------------------- #
# Siigo — Proveedor Tecnológico único
# --------------------------------------------------------------------------- #
SIIGO_AUTH_URL = env("SIIGO_AUTH_URL", default="https://api.siigo.com/auth")
SIIGO_API_BASE_URL = env("SIIGO_API_BASE_URL", default="https://api.siigo.com")

# --------------------------------------------------------------------------- #
# Cifrado de campos en reposo (credenciales Siigo) — apps.empresas.fields
# --------------------------------------------------------------------------- #
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY")
