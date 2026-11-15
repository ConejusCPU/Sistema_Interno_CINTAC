from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("salud/", views.salud, name="salud"),
    path("api/sesion/", views.sesion),
    path("api/login/", views.login_vista),
    path("api/logout/", views.logout_vista),
    path("api/cambiar-clave/", views.cambiar_clave),
    path("api/cancelar-cambio-clave/", views.cancelar_cambio_clave),
    path("api/cotizar/", views.cotizar),
    path("api/comparar/", views.comparar),
    path("api/tarifas/", views.tarifas),
    path("api/tarifas/restaurar/", views.tarifas_restaurar),
    path("api/tarifas/<int:pk>/", views.tarifa_detalle),
    path("api/usuarios/", views.usuarios),
    path("api/usuarios/restaurar/", views.usuarios_restaurar),
    path("api/usuarios/<int:pk>/", views.usuario_detalle),
    path("api/usuarios/<int:pk>/desbloquear/", views.usuario_desbloquear),
    path("api/usuarios/<int:pk>/restablecer/", views.usuario_restablecer),
]
