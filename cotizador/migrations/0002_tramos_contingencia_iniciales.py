from django.db import migrations

TRAMOS = [(30, "3.00"), (40, "5.00"), (None, "8.00")]   # equivalen a los valores fijos del prototipo


def crear_tramos(apps, schema_editor):
    Tramo = apps.get_model("cotizador", "TramoContingencia")
    if not Tramo.objects.exists():
        for dias_hasta, pct in TRAMOS:
            Tramo.objects.create(dias_hasta=dias_hasta, porcentaje=pct)


class Migration(migrations.Migration):
    dependencies = [("cotizador", "0001_initial")]
    operations = [migrations.RunPython(crear_tramos, migrations.RunPython.noop)]
