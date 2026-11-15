from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F
from django.db.models.functions import Lower

from .constants import ROL_ADMIN, ROL_ANALISTA
from .validators import validar_usuario_sin_espacios


class Rol(models.TextChoices):
    ADMINISTRADOR = ROL_ADMIN, "Administrador"
    ANALISTA = ROL_ANALISTA, "Analista"


class UsuarioManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("rol", Rol.ADMINISTRADOR)
        extra_fields.setdefault("nombre", username)
        return super().create_superuser(username, email, password, **extra_fields)


class Usuario(AbstractUser):
    """Usuario del sistema: el campo `username` es el «Correo / Usuario» del prototipo."""

    username = models.CharField(
        "correo / usuario", max_length=150, unique=True,
        validators=[validar_usuario_sin_espacios],
        error_messages={"unique": "El usuario ya existe."},
    )
    first_name = None
    last_name = None

    nombre = models.CharField("nombre completo", max_length=150)
    rol = models.CharField(max_length=20, choices=Rol.choices, default=Rol.ANALISTA)
    primer_ingreso = models.BooleanField(
        "clave temporal (debe cambiarla)", default=False,
        help_text="Si está marcado, el usuario debe reemplazar su clave en el próximo ingreso.",
    )
    intentos_fallidos = models.PositiveSmallIntegerField("intentos fallidos", default=0)
    bloqueado = models.BooleanField("cuenta bloqueada", default=False)

    objects = UsuarioManager()
    REQUIRED_FIELDS = ["nombre"]

    class Meta:
        ordering = ["id"]
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        constraints = [
            models.UniqueConstraint(Lower("username"), name="usuario_username_ci_unico"),
        ]

    def __str__(self):
        return f"{self.username} ({self.rol})"

    def get_full_name(self):
        return self.nombre

    def get_short_name(self):
        return self.nombre

    @property
    def es_admin(self):
        return self.rol == Rol.ADMINISTRADOR

    @property
    def estado(self):
        return "Bloqueado" if self.bloqueado else "Activo"

    def save(self, *args, **kwargs):
        # El rol Administrador da acceso a Django Admin (margen de contingencia, etc.)
        self.is_staff = self.is_superuser = self.es_admin
        super().save(*args, **kwargs)


class Tarifa(models.Model):
    COBRO_CONTENEDOR = "contenedor"
    COBRO_TONELADA = "tonelada"
    COBROS = [(COBRO_CONTENEDOR, "Por contenedor"), (COBRO_TONELADA, "Por tonelada")]

    embarcador = models.CharField(max_length=100)
    origen = models.CharField("puerto origen", max_length=100)
    destino = models.CharField("puerto destino", max_length=100)
    cobro = models.CharField("tipo de cobro", max_length=12, choices=COBROS)
    monto = models.DecimalField(
        "tarifa (USD)", max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    dias = models.PositiveIntegerField("tránsito (días)", validators=[MinValueValidator(1)])

    class Meta:
        ordering = ["id"]
        verbose_name = "tarifa"
        verbose_name_plural = "tarifas"

    def __str__(self):
        return f"{self.embarcador}: {self.origen} → {self.destino}"

    @property
    def ruta(self):
        return f"{self.origen} → {self.destino}"


class TramoContingencia(models.Model):
    """Margen de contingencia logística según los días de tránsito.

    Se aplica el primer tramo (de menor a mayor) cuyo «días hasta» sea mayor o igual
    a los días de tránsito. El tramo sin «días hasta» cubre todo lo que exceda.
    """

    dias_hasta = models.PositiveIntegerField(
        "días de tránsito hasta", null=True, blank=True, unique=True,
        help_text="Tránsito máximo (inclusive) al que aplica este margen. "
                  "Déjalo vacío para el tramo «más de…» (sin límite superior).",
    )
    porcentaje = models.DecimalField(
        "margen de contingencia (%)", max_digits=5, decimal_places=2,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="Porcentaje que se suma al flete base. Ejemplo: 3 equivale a 3%.",
    )

    class Meta:
        ordering = [F("dias_hasta").asc(nulls_last=True)]
        verbose_name = "margen de contingencia"
        verbose_name_plural = "márgenes de contingencia"

    def __str__(self):
        rango = f"hasta {self.dias_hasta} días" if self.dias_hasta is not None else "más allá del último tramo"
        return f"{rango}: {self.porcentaje}%"

    def clean(self):
        if self.dias_hasta is None:
            otros = TramoContingencia.objects.filter(dias_hasta__isnull=True).exclude(pk=self.pk)
            if otros.exists():
                raise ValidationError("Ya existe un tramo sin límite de días. Solo puede haber uno.")

class RegistroAccion(models.Model):
    fecha = models.DateTimeField("fecha y hora", auto_now_add=True, db_index=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="acciones")
    usuario_texto = models.CharField("usuario", max_length=150, blank=True)  # se conserva aunque borren la cuenta
    accion = models.CharField("acción", max_length=40, db_index=True)
    detalle = models.CharField(max_length=500, blank=True)
    ip = models.GenericIPAddressField("IP", null=True, blank=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "registro de acción"
        verbose_name_plural = "registro de acciones"
