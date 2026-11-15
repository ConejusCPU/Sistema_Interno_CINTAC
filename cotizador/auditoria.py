from .models import RegistroAccion

def registrar(request, accion, detalle="", usuario=None):
    u = usuario or (request.user if request.user.is_authenticated else None)
    ip = (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
          or request.META.get("REMOTE_ADDR"))
    RegistroAccion.objects.create(
        usuario=u, usuario_texto=u.username if u else "",
        accion=accion, detalle=detalle[:500], ip=ip or None)