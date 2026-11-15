# Cotizador Interno de Fletes de Importación · CINTAC (Django)

El prototipo HTML (`cotizador_cintacProto.html`) convertido en una aplicación Django lista para Render.
**El aspecto visual es el mismo:** el CSS es idéntico byte a byte y el HTML solo cambia en dos frases que
decían «se guardan en localStorage» (ahora dicen «en la base de datos del sistema»).

## Qué pasó de navegador a servidor

| Antes (prototipo)                         | Ahora (Django)                                                    |
|-------------------------------------------|-------------------------------------------------------------------|
| Usuarios y tarifas en `localStorage`      | Modelos `Usuario` y `Tarifa` en PostgreSQL                        |
| Hash SHA-256 propio en JavaScript         | PBKDF2 de Django; la clave nunca viaja ni se guarda en texto plano |
| Permisos por rol solo en la pantalla      | Permisos validados en cada endpoint (`/api/...`), no se pueden saltar |
| Bloqueo a los 3 intentos en el navegador  | Bloqueo en el servidor                                             |
| Cálculo de la cotización en JavaScript    | Cálculo en el servidor (`cotizador/services.py`)                   |
| Contingencia fija: 3 % / 5 % / 8 %        | Editable en **Django Admin** (`/admin/` → Márgenes de contingencia) |
| Claves de ejemplo en el código            | Sin claves en el código: el primer Administrador se crea con variables de entorno |

Las reglas de negocio (Decreto 75: 25 t por contenedor, arancel 6 % / TLC 0 %, IVA 19 % sobre CIF, mensajes de
error, flujo de primer ingreso) se conservan. El cálculo del servidor se comparó contra el JavaScript original en
400 casos aleatorios sin diferencias.

## Estructura

```
config/              settings.py, urls.py, wsgi.py
cotizador/
  models.py          Usuario, Tarifa, TramoContingencia
  services.py        motor de cálculo COMEX
  views.py, urls.py  API JSON (/api/...) y página principal
  admin.py           Django Admin (margen de contingencia, tarifas, usuarios)
  templates/         index.html (el HTML del prototipo)
  static/            css/app.css (idéntico) y js/app.js (la lógica de pantalla, ahora llama a la API)
  management/commands/crear_datos_iniciales.py
  tests.py           26 pruebas automáticas
build.sh · render.yaml · requirements.txt · .env.example
```

## Ejecutar en tu computador

```bash
python -m venv .venv && source .venv/bin/activate      # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
export DEBUG=1 ADMIN_INITIAL_PASSWORD='Cambiar#Esta2026'   # en Windows (PowerShell): $env:DEBUG=1
python manage.py migrate
python manage.py crear_datos_iniciales
python manage.py runserver
```

Abre http://127.0.0.1:8000 e ingresa con `admin_cintac` y la clave que definiste; el sistema te pedirá cambiarla.
Pruebas: `DEBUG=1 python manage.py test`.

## Desplegar en Render

1. Sube esta carpeta a un repositorio de GitHub (el archivo `build.sh` debe quedar ejecutable:
   `git update-index --chmod=+x build.sh`).
2. En Render: **New → Blueprint** y elige el repositorio. Render lee `render.yaml` y crea la base PostgreSQL y el servicio web.
3. Cuando lo pida, define `ADMIN_INITIAL_PASSWORD` (clave temporal del primer Administrador).
4. Al terminar el despliegue, abre la URL, ingresa con `admin_cintac` y cambia la clave.
5. Para ajustar el margen de contingencia, entra a `/admin/` con el mismo usuario.

> **Base de datos gratuita:** el plan `free` de PostgreSQL en Render **expira y se borra con sus datos** (revisa el plazo vigente
> en la documentación de Render). Para uso real cambia `plan: free` por un plan de pago en `render.yaml`.
> El servicio web gratuito también se «duerme» tras un rato sin tráfico: la primera carga puede tardar.

## Variables de entorno

| Variable                    | Uso                                                                                   |
|-----------------------------|---------------------------------------------------------------------------------------|
| `SECRET_KEY`                | Obligatoria en producción (Render la genera sola).                                     |
| `DEBUG`                     | `False` en producción.                                                                 |
| `DATABASE_URL`              | La entrega Render desde la base PostgreSQL. Sin ella se usa SQLite local.               |
| `ADMIN_USERNAME`            | Usuario del primer Administrador (por defecto `admin_cintac`).                          |
| `ADMIN_INITIAL_PASSWORD`    | Clave temporal del primer Administrador. Si falta, se genera y se imprime una vez en el log de despliegue. |
| `ALLOW_EXAMPLE_USERS_RESET` | `1` habilita el botón «Restaurar usuarios de ejemplo» (borra todos los usuarios). Por defecto está desactivado. |
| `SESSION_HORAS`             | Duración máxima de la sesión (por defecto 8). La sesión también termina al cerrar el navegador. |

## Notas

- Todo usuario con rol **Administrador** también puede entrar a `/admin/` (Django Admin) con permisos completos.
- «Restaurar tarifas de ejemplo» sigue funcionando. «Restaurar usuarios de ejemplo» queda deshabilitado salvo que lo actives,
  y cuando se activa genera claves temporales aleatorias (no la clave fija `cintac2026` del prototipo).
- Quedan fuera de esta versión, por no existir en el prototipo: importar tarifas desde Excel, carga especial FCL,
  registro de ocupante, historial de simulaciones, edición de tarifas y cambio de rol de un usuario ya creado.
