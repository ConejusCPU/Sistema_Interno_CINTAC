from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm

from .models import Tarifa, TramoContingencia, Usuario
from .models import RegistroAccion

@admin.register(RegistroAccion)
class RegistroAccionAdmin(admin.ModelAdmin):
    list_display = ("fecha", "usuario_texto", "accion", "detalle", "ip")
    list_filter = ("accion", "fecha")
    search_fields = ("usuario_texto", "detalle")
    date_hierarchy = "fecha"

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

class UsuarioCreationForm(AdminUserCreationForm):
    class Meta(AdminUserCreationForm.Meta):
        model = Usuario
        fields = ("username", "nombre", "rol", "primer_ingreso")


class UsuarioChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = Usuario
        fields = "__all__"


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    form = UsuarioChangeForm
    add_form = UsuarioCreationForm
    list_display = ("username", "nombre", "rol", "estado", "primer_ingreso", "intentos_fallidos")
    list_filter = ("rol", "bloqueado", "primer_ingreso")
    search_fields = ("username", "nombre")
    ordering = ("id",)
    filter_horizontal = ()
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Datos", {"fields": ("nombre", "rol", "email")}),
        ("Estado de la cuenta", {"fields": ("bloqueado", "intentos_fallidos", "primer_ingreso", "is_active")}),
        ("Registro", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",),
                "fields": ("username", "nombre", "rol", "primer_ingreso", "usable_password",
                           "password1", "password2")}),
    )
    actions = ["desbloquear"]

    @admin.action(description="Desbloquear cuentas seleccionadas")
    def desbloquear(self, request, queryset):
        n = queryset.update(bloqueado=False, intentos_fallidos=0)
        self.message_user(request, f"{n} cuenta(s) desbloqueada(s).", messages.SUCCESS)


@admin.register(Tarifa)
class TarifaAdmin(admin.ModelAdmin):
    list_display = ("embarcador", "origen", "destino", "cobro", "monto", "dias")
    list_filter = ("embarcador", "origen", "cobro")
    search_fields = ("embarcador", "origen", "destino")


@admin.register(TramoContingencia)
class TramoContingenciaAdmin(admin.ModelAdmin):
    """Margen de contingencia logística editable (reemplaza los valores fijos del prototipo)."""
    list_display = ("descripcion", "porcentaje")
    list_editable = ("porcentaje",)
    ordering = ("dias_hasta",)

    @admin.display(description="Días de tránsito", ordering="dias_hasta")
    def descripcion(self, obj):
        return f"Hasta {obj.dias_hasta} días" if obj.dias_hasta is not None else "Más de los tramos anteriores"
