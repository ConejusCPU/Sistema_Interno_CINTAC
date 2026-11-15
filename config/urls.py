from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Administración CINTAC · Cotizador"
admin.site.site_title = "Cotizador CINTAC"
admin.site.index_title = "Configuración del sistema"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("cotizador.urls")),
]
