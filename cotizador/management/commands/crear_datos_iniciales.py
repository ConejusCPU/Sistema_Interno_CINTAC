import os

from django.core.management.base import BaseCommand
from django.db import transaction

from cotizador.constants import ROL_ADMIN, ROL_ANALISTA, TARIFAS_EJEMPLO
from cotizador.models import Tarifa, Usuario
from cotizador.seguridad import generar_temporal


class Command(BaseCommand):
    help = ("Crea el primer Administrador (si no existe ninguno) y, si la tabla está vacía, "
            "las tarifas de ejemplo. Es idempotente: se puede ejecutar en cada despliegue.")

    def add_arguments(self, parser):
        parser.add_argument("--sin-tarifas", action="store_true", help="No crear tarifas de ejemplo.")
        parser.add_argument("--usuarios-ejemplo", action="store_true",
                            help="Crear analista1 y analista2 (solo para demostraciones).")

    @transaction.atomic
    def handle(self, *args, **opts):
        if not Usuario.objects.filter(rol=ROL_ADMIN).exists():
            username = os.environ.get("ADMIN_USERNAME", "admin_cintac")
            clave = os.environ.get("ADMIN_INITIAL_PASSWORD") or generar_temporal()
            generada = not os.environ.get("ADMIN_INITIAL_PASSWORD")
            admin = Usuario(username=username, nombre="Administrador CINTAC", rol=ROL_ADMIN,
                            primer_ingreso=True)      # deberá cambiar la clave en su primer ingreso
            admin.set_password(clave)
            admin.save()
            self.stdout.write(self.style.SUCCESS(f"Administrador creado: {username}"))
            if generada:
                self.stdout.write(f"Contraseña temporal (se muestra una sola vez): {clave}")
        else:
            self.stdout.write("Ya existe un Administrador: no se crea otro.")

        if opts["usuarios_ejemplo"]:
            for username, nombre in (("analista1", "Analista de Importaciones 1"),
                                     ("analista2", "Analista de Importaciones 2")):
                if Usuario.objects.filter(username__iexact=username).exists():
                    continue
                temporal = generar_temporal()
                u = Usuario(username=username, nombre=nombre, rol=ROL_ANALISTA, primer_ingreso=True)
                u.set_password(temporal)
                u.save()
                self.stdout.write(f"Usuario {username}: contraseña temporal {temporal}")

        if not opts["sin_tarifas"] and not Tarifa.objects.exists():
            Tarifa.objects.bulk_create([
                Tarifa(embarcador=e, origen=o, destino=d, cobro=c, monto=m, dias=dias)
                for e, o, d, c, m, dias in TARIFAS_EJEMPLO
            ])
            self.stdout.write(self.style.SUCCESS("Tarifas de ejemplo creadas."))
