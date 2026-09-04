"""Entorno para `manage.py test`.

Uso: ``manage.py test --settings=config.settings.test`` (o
``DJANGO_SETTINGS_MODULE=config.settings.test`` en el shell).

No es una elección automática de manage.py: si se corre `manage.py test`
sin --settings se usa dev.py (con throttling real), lo cual puede volver la
suite flaky si corre muchas peticiones a /token/ u /onboarding/ en poco
tiempo real. Por eso este archivo existe aparte, para que "correr los
tests" y "correr el servidor local" no compartan límites pensados para
producción.
"""
from .dev import *  # noqa: F401,F403
from .dev import REST_FRAMEWORK

# El throttling (onboarding/login) está pensado para producción: en tests,
# muchas peticiones legítimas caen en la misma ventana de tiempo real y no
# hay "cajeros distintos" que lo justifiquen. OnboardingView/CustomToken...
# fijan throttle_classes directo en la vista (no leen DEFAULT_THROTTLE_
# CLASSES), así que la única forma de apagarlos de verdad es poner su tasa
# en None (mecanismo estándar de DRF) — no se toca el límite real de dev/prod.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {"onboarding": None, "login": None},
}

# PBKDF2 (el hasher por defecto) es deliberadamente lento; con decenas de
# usuarios creados por test eso es la mayor parte del tiempo de la suite.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
