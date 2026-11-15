import re

from django.core.exceptions import ValidationError

# Mismas reglas de complejidad del prototipo (id, texto, prueba)
REGLAS_CLAVE = [
    ("len", "Mínimo 8 caracteres", lambda p: len(p) >= 8),
    ("upper", "Al menos 1 letra mayúscula (A-Z)", lambda p: re.search(r"[A-Z]", p) is not None),
    ("lower", "Al menos 1 letra minúscula (a-z)", lambda p: re.search(r"[a-z]", p) is not None),
    ("digit", "Al menos 1 número (0-9)", lambda p: re.search(r"[0-9]", p) is not None),
    (
        "special",
        "Al menos 1 carácter especial (!@#$%^&*)",
        lambda p: re.search(r"""[!@#$%^&*()_+\-=\[\]{};:'",.<>/?\\|~`]""", p) is not None,
    ),
]


def reglas_incumplidas(clave):
    return [texto for _id, texto, prueba in REGLAS_CLAVE if not prueba(clave)]


class ComplejidadClaveValidator:
    """Aplica la política de contraseñas también en Django Admin."""

    def validate(self, password, user=None):
        faltan = reglas_incumplidas(password)
        if faltan:
            raise ValidationError(
                "La contraseña no cumple el estándar. Falta: "
                + "; ".join(t[0].lower() + t[1:] for t in faltan) + ".",
                code="password_complejidad",
            )

    def get_help_text(self):
        return "Mínimo 8 caracteres, con mayúscula, minúscula, número y carácter especial."


def validar_usuario_sin_espacios(valor):
    if re.search(r"\s", valor or ""):
        raise ValidationError("El correo / usuario no puede contener espacios.")
