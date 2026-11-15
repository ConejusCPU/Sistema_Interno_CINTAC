import json
import math
import re
import time
from functools import wraps

from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.hashers import check_password
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from .auditoria import registrar
    
from .constants import (
    MAX_INTENTOS, MAX_TON_CONT, PERMISOS, PW_PENDING_SEGUNDOS, ROL_ADMIN, ROL_ANALISTA,
    TARIFAS_EJEMPLO,
)
from .models import Tarifa, Usuario
from .seguridad import generar_temporal, hash_falso
from .services import calcular, cargar_tramos
from .validators import reglas_incumplidas

BACKEND = "django.contrib.auth.backends.ModelBackend"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# --------------------------------------------------------------------------- utilidades
def error(mensaje, status=400, **extra):
    return JsonResponse({"error": mensaje, **extra}, status=status)


def cuerpo(request):
    try:
        datos = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return {}
    return datos if isinstance(datos, dict) else {}


def api(*metodos, auth=True):
    """Valida método y sesión activa. Todas las respuestas llevan Cache-Control: no-store."""
    def decorador(vista):
        @wraps(vista)
        @never_cache
        def envoltura(request, *args, **kwargs):
            if request.method not in metodos:
                return error("Método no permitido.", 405)
            if auth:
                u = request.user
                if not u.is_authenticated or not u.is_active or u.bloqueado or u.primer_ingreso:
                    return error("Tu sesión no está activa. Vuelve a iniciar sesión.", 401)
            return vista(request, *args, **kwargs)
        return envoltura
    return decorador


def exigir_admin(request):
    if not request.user.es_admin:
        return error("Acción restringida: requiere rol Administrador.", 403, codigo="solo_admin")
    return None


def numero(datos, clave, etiqueta, minimo=0.0, maximo=1e12):
    valor = datos.get(clave, 0)
    if isinstance(valor, bool) or valor in (None, ""):
        valor = 0
    try:
        f = float(valor)
    except (TypeError, ValueError):
        raise ValueError(f"Valor inválido en {etiqueta}.")
    if not math.isfinite(f) or f < minimo or f > maximo:
        raise ValueError(f"Valor fuera de rango en {etiqueta}.")
    return f


def texto(valor):
    return valor.strip() if isinstance(valor, str) else ""


def serializar_usuario(u):
    return {"id": u.pk, "nombre": u.nombre, "usuario": u.username, "rol": u.rol,
            "estado": u.estado, "primerIngreso": u.primer_ingreso,
            "intentosFallidos": u.intentos_fallidos}


def serializar_tarifa(t):
    return {"id": t.pk, "embarcador": t.embarcador, "origen": t.origen, "destino": t.destino,
            "cobro": t.cobro, "monto": float(t.monto), "dias": t.dias}


def lista_usuarios():
    return [serializar_usuario(u) for u in Usuario.objects.all()]


def lista_tarifas():
    return [serializar_tarifa(t) for t in Tarifa.objects.all()]


def configuracion():
    return {"maxTonCont": MAX_TON_CONT, "maxIntentos": MAX_INTENTOS, "permisos": PERMISOS,
            "restaurarUsuariosHabilitado": settings.PERMITIR_RESTAURAR_USUARIOS_EJEMPLO}


# --------------------------------------------------------------------------- páginas
@ensure_csrf_cookie
def index(request):
    return render(request, "cotizador/index.html")


def salud(request):
    return HttpResponse("ok", content_type="text/plain")


# --------------------------------------------------------------------------- sesión
@api("GET", auth=False)
def sesion(request):
    u = request.user
    activo = u.is_authenticated and u.is_active and not u.bloqueado and not u.primer_ingreso
    return JsonResponse({"autenticado": activo, "usuario": serializar_usuario(u) if activo else None,
                         "config": configuracion()})


@api("POST", auth=False)
def login_vista(request):
    d = cuerpo(request)
    nombre = texto(d.get("usuario")).lower()
    clave = d.get("clave") if isinstance(d.get("clave"), str) else ""
    if not nombre or not clave:
        return error("Ingresa tu usuario y contraseña.", 400)

    with transaction.atomic():
        u = Usuario.objects.select_for_update().filter(username__iexact=nombre).first()
        if u is None or not u.is_active:
            check_password(clave, hash_falso())            # tiempo de respuesta parejo
            registrar(request, "LOGIN_FALLIDO", f"usuario inexistente: {nombre}")
            return error("Usuario o contraseña incorrectos.", 401)

        if u.bloqueado:
            registrar(request, "LOGIN_CUENTA_BLOQUEADA", usuario=u)
            return error("Cuenta bloqueada por intentos fallidos. Contacta a un Administrador "
                         "para desbloquearla.", 423, aviso=True)

        if not u.check_password(clave):
            u.intentos_fallidos += 1
            if u.intentos_fallidos >= MAX_INTENTOS:
                u.bloqueado = True
                msg = (f"Contraseña incorrecta. Superaste los {MAX_INTENTOS} intentos permitidos: "
                       "la cuenta fue bloqueada. Contacta a un Administrador.")
            else:
                quedan = MAX_INTENTOS - u.intentos_fallidos
                msg = ("Contraseña incorrecta. Te "
                       + ("queda 1 intento" if quedan == 1 else f"quedan {quedan} intentos")
                       + " antes del bloqueo.")
            u.save(update_fields=["intentos_fallidos", "bloqueado"])
            registrar(request, "LOGIN_FALLIDO", f"intento {u.intentos_fallidos} de {MAX_INTENTOS}", usuario=u)

            return error(msg, 401, aviso=True)

        u.intentos_fallidos = 0
        u.save(update_fields=["intentos_fallidos"])

    if u.primer_ingreso:
        # No hay sesión de trabajo hasta que cambie la clave temporal
        logout(request)
        request.session.cycle_key()
        request.session["pw_pendiente"] = {"id": u.pk, "ts": time.time()}
        registrar(request, "LOGIN_CLAVE_TEMPORAL", "debe cambiar su contraseña", usuario=u)
        return JsonResponse({"ok": True, "requiereCambioClave": True, "nombre": u.nombre})

    login(request, u, backend=BACKEND)
    return JsonResponse({"ok": True, "usuario": serializar_usuario(u), "config": configuracion()})


@api("POST", auth=False)
def logout_vista(request):
    registrar(request, "LOGOUT")
    logout(request)
    return JsonResponse({"ok": True})
#----------------------------------------------------------------------------------------------

def _usuario_pendiente(request):
    p = request.session.get("pw_pendiente")
    if not isinstance(p, dict) or time.time() - p.get("ts", 0) > PW_PENDING_SEGUNDOS:
        request.session.pop("pw_pendiente", None)
        return None
    return Usuario.objects.filter(pk=p.get("id"), is_active=True, bloqueado=False,
                                  primer_ingreso=True).first()


@api("POST", auth=False)
def cambiar_clave(request):
    u = _usuario_pendiente(request)
    if u is None:
        return error("La solicitud de cambio de contraseña expiró. Vuelve a iniciar sesión.", 401,
                     expirada=True)
    d = cuerpo(request)
    p1 = d.get("clave1") if isinstance(d.get("clave1"), str) else ""
    p2 = d.get("clave2") if isinstance(d.get("clave2"), str) else ""

    faltan = reglas_incumplidas(p1)
    if faltan:
        return error("La contraseña no cumple el estándar. Falta: "
                     + "; ".join(t[0].lower() + t[1:] for t in faltan) + ".")
    if p1 != p2:
        return error("Las contraseñas no coinciden. Repítela exactamente igual.")
    if u.check_password(p1):
        return error("La nueva contraseña debe ser distinta de la contraseña temporal.")

    u.set_password(p1)
    u.primer_ingreso = False
    u.intentos_fallidos = 0
    u.save()
    request.session.pop("pw_pendiente", None)
    login(request, u, backend=BACKEND)
    registrar(request, "CLAVE_CAMBIADA", usuario=u)
    return JsonResponse({"ok": True, "usuario": serializar_usuario(u), "config": configuracion(),
                         "mensaje": "Contraseña actualizada correctamente."})


@api("POST", auth=False)
def cancelar_cambio_clave(request):
    request.session.pop("pw_pendiente", None)
    return JsonResponse({"ok": True})


# --------------------------------------------------------------------------- cálculo
@api("POST")
def cotizar(request):
    d = cuerpo(request)
    try:
        toneladas = numero(d, "toneladas", "toneladas")
        contenedores = numero(d, "contenedores", "contenedores")
        fob = numero(d, "fob", "valor FOB")
        dias = numero(d, "dias", "días de tránsito")
        tc = numero(d, "tc", "tipo de cambio") or 1
    except ValueError as e:
        return error(str(e))
    try:
        tarifa = Tarifa.objects.filter(pk=int(d.get("tarifaId"))).first()
    except (TypeError, ValueError):
        tarifa = None
    if tarifa is None:
        return error("La tarifa seleccionada no existe.", 404)
    resultado = calcular(tarifa, toneladas, contenedores, fob, dias, bool(d.get("tlc")), tc)
    return JsonResponse({"resultado": resultado})


@api("POST")
def comparar(request):
    d = cuerpo(request)
    try:
        toneladas = numero(d, "toneladas", "toneladas")
        fob = numero(d, "fob", "valor FOB")
        tc = numero(d, "tc", "tipo de cambio") or 1
    except ValueError as e:
        return error(str(e))
    ruta = texto(d.get("ruta"))
    tarifas = [t for t in Tarifa.objects.all() if t.ruta == ruta]
    if not tarifas or toneladas <= 0:
        return error("Selecciona una ruta e ingresa las toneladas para comparar.")
    tramos = cargar_tramos()
    resultados = []
    for t in tarifas:
        r = calcular(t, toneladas, 0, fob, t.dias, bool(d.get("tlc")), tc, tramos)
        r["tarifa"] = serializar_tarifa(t)
        resultados.append(r)
    resultados.sort(key=lambda r: r["totalUSD"])
    return JsonResponse({"resultados": resultados})


# --------------------------------------------------------------------------- tarifas
@api("GET", "POST")
def tarifas(request):
    if request.method == "GET":
        return JsonResponse({"tarifas": lista_tarifas()})

    denegado = exigir_admin(request)
    if denegado:
        return denegado
    d = cuerpo(request)
    msg = "Completa todos los campos con valores válidos (tarifa y días mayores a 0)."
    emb, ori, des = texto(d.get("embarcador")), texto(d.get("origen")), texto(d.get("destino"))
    cobro = d.get("cobro")
    try:
        monto = numero(d, "monto", "tarifa", minimo=0.0, maximo=1e9)
        dias = numero(d, "dias", "tránsito", minimo=0.0, maximo=3650)
    except ValueError:
        return error(msg)
    if (not emb or not ori or not des or max(len(emb), len(ori), len(des)) > 100
            or cobro not in (Tarifa.COBRO_CONTENEDOR, Tarifa.COBRO_TONELADA)
            or round(monto, 2) <= 0 or int(dias) <= 0):
        return error(msg)
    Tarifa.objects.create(embarcador=emb, origen=ori, destino=des, cobro=cobro,
                          monto=round(monto, 2), dias=int(dias))
    registrar(request, "TARIFA_CREADA", f"{emb}: {ori} → {des} ({cobro}, US$ {round(monto, 2)})")   # <--auditoria
    return JsonResponse({"tarifas": lista_tarifas(), "mensaje": "Tarifa agregada"})


@api("DELETE")
def tarifa_detalle(request, pk):
    denegado = exigir_admin(request)
    if denegado:
        return denegado
    t = Tarifa.objects.filter(pk=pk).first()
    if t:
        registrar(request, "TARIFA_ELIMINADA", f"{t.embarcador}: {t.origen} → {t.destino}")
        t.delete()
    return JsonResponse({"tarifas": lista_tarifas(), "mensaje": "Tarifa eliminada"})


@api("POST")
def tarifas_restaurar(request):
    denegado = exigir_admin(request)
    if denegado:
        return denegado
    with transaction.atomic():
        Tarifa.objects.all().delete()
        Tarifa.objects.bulk_create([
            Tarifa(embarcador=e, origen=o, destino=d, cobro=c, monto=m, dias=dias)
            for e, o, d, c, m, dias in TARIFAS_EJEMPLO
        ])
    registrar(request, "TARIFAS_RESTAURADAS", "se restauraron las tarifas de ejemplo")
    return JsonResponse({"tarifas": lista_tarifas(), "mensaje": "Tarifas restauradas"})


# --------------------------------------------------------------------------- usuarios
@api("GET", "POST")
def usuarios(request):
    denegado = exigir_admin(request)
    if denegado:
        return denegado
    if request.method == "GET":
        return JsonResponse({"usuarios": lista_usuarios()})

    d = cuerpo(request)
    nombre, usuario, rol = texto(d.get("nombre")), texto(d.get("usuario")), d.get("rol")
    if not nombre or not usuario:
        return error("Completa el nombre completo y el correo / usuario.")
    if len(nombre) > 150 or len(usuario) > 150:
        return error("El nombre y el correo / usuario no pueden superar los 150 caracteres.")
    if re.search(r"\s", usuario):
        return error("El correo / usuario no puede contener espacios.")
    if "@" in usuario and not EMAIL_RE.match(usuario):
        return error("El correo ingresado no tiene un formato válido.")
    if rol not in PERMISOS:
        return error("Selecciona un rol válido.")
    duplicado = f'El usuario "{usuario}" ya existe.'
    if Usuario.objects.filter(username__iexact=usuario).exists():
        return error(duplicado)

    temporal = generar_temporal()
    nuevo = Usuario(username=usuario, nombre=nombre, rol=rol, primer_ingreso=True)
    nuevo.set_password(temporal)
    try:
        with transaction.atomic():
            nuevo.save()
    except IntegrityError:
        return error(duplicado)
    registrar(request, "USUARIO_CREADO", f"{usuario} ({rol})")
    return JsonResponse({"usuarios": lista_usuarios(),
                         "temporal": {"usuario": usuario, "clave": temporal}})


@api("DELETE")
def usuario_detalle(request, pk):
    denegado = exigir_admin(request)
    if denegado:
        return denegado
    u = Usuario.objects.filter(pk=pk).first()
    if u is None:
        return error("Usuario no encontrado.", 404)
    if u.pk == request.user.pk:
        return error("No puedes eliminar tu propio usuario con la sesión activa.")
    if u.rol == ROL_ADMIN and Usuario.objects.filter(rol=ROL_ADMIN).count() <= 1:
        return error("Debe existir al menos un Administrador.")
    registrar(request, "USUARIO_ELIMINADO", f"{u.username} ({u.rol})")
    u.delete()
    return JsonResponse({"usuarios": lista_usuarios(), "mensaje": "Usuario eliminado"})


@api("POST")
def usuario_desbloquear(request, pk):
    denegado = exigir_admin(request)
    if denegado:
        return denegado
    u = Usuario.objects.filter(pk=pk).first()
    if u is None:
        return error("Usuario no encontrado.", 404)
    u.bloqueado = False
    u.intentos_fallidos = 0
    u.save(update_fields=["bloqueado", "intentos_fallidos"])
    registrar(request, "USUARIO_DESBLOQUEADO", u.username)
    return JsonResponse({"usuarios": lista_usuarios(),
                         "mensaje": f'Usuario "{u.username}" desbloqueado.'})


@api("POST")
def usuario_restablecer(request, pk):
    denegado = exigir_admin(request)
    if denegado:
        return denegado
    u = Usuario.objects.filter(pk=pk).first()
    if u is None:
        return error("Usuario no encontrado.", 404)
    if u.pk == request.user.pk:
        return error("No puedes restablecer tu propia clave con la sesión activa.")
    temporal = generar_temporal()
    u.set_password(temporal)
    u.primer_ingreso = True
    u.intentos_fallidos = 0
    u.save()
    registrar(request, "CLAVE_RESTABLECIDA", u.username)
    return JsonResponse({"usuarios": lista_usuarios(),
                         "temporal": {"usuario": u.username, "clave": temporal}})