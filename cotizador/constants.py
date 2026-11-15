"""Constantes de negocio (equivalentes a la configuración del prototipo)."""

MAX_TON_CONT = 25          # Decreto 75: máx. 25 t por contenedor
TASA_ARANCEL = 0.06        # 6% sobre CIF (sin TLC)
TASA_IVA = 0.19            # 19% sobre CIF
MAX_INTENTOS = 3           # intentos fallidos antes del bloqueo

ROL_ADMIN = "Administrador"
ROL_ANALISTA = "Analista"

# Módulos de la interfaz permitidos por rol (la API aplica las mismas reglas)
PERMISOS = {
    ROL_ADMIN: ["mod1", "mod2", "mod3", "mod4"],
    ROL_ANALISTA: ["mod1", "mod2"],
}

# Tramos de contingencia por defecto: (días hasta, porcentaje). None = sin límite.
TRAMOS_CONTINGENCIA_DEFECTO = [(30, 3), (40, 5), (None, 8)]

TARIFAS_EJEMPLO = [
    ("Maersk", "Shanghai", "San Antonio", "contenedor", 2850, 32),
    ("MSC", "Shanghai", "San Antonio", "contenedor", 2700, 38),
    ("Hapag-Lloyd", "Shanghai", "San Antonio", "contenedor", 3050, 28),
    ("Maersk", "Ningbo", "San Antonio", "contenedor", 2600, 35),
    ("MSC", "Ningbo", "San Antonio", "tonelada", 118, 42),
    ("Hapag-Lloyd", "Ningbo", "San Antonio", "contenedor", 2750, 30),
]

# Duración máxima de un cambio de clave pendiente tras validar la clave temporal
PW_PENDING_SEGUNDOS = 600
