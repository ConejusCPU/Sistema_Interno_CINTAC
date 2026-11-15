import secrets

from django.contrib.auth.hashers import make_password

_MAYUS = "ABCDEFGHJKLMNPQRSTUVWXYZ"
_MINUS = "abcdefghijkmnpqrstuvwxyz"
_DIGITOS = "23456789"
_ESPECIALES = "!@#$%&*"


def generar_temporal():
    """Contraseña temporal aleatoria que cumple todas las reglas de complejidad."""
    elegir = secrets.choice
    chars = [elegir(_MAYUS), elegir(_MAYUS), elegir(_MINUS), elegir(_MINUS), elegir(_MINUS),
             elegir(_DIGITOS), elegir(_DIGITOS), elegir(_ESPECIALES)]
    chars += [elegir(_MAYUS + _MINUS + _DIGITOS) for _ in range(3)]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


_HASH_FALSO = None


def hash_falso():
    """Hash para igualar el tiempo de respuesta cuando el usuario no existe."""
    global _HASH_FALSO
    if _HASH_FALSO is None:
        _HASH_FALSO = make_password(secrets.token_hex(16))
    return _HASH_FALSO
