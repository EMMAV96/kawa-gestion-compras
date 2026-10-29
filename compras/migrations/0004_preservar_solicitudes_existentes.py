from collections import defaultdict
from django.db import migrations


def preservar(apps, schema_editor):
    Solicitud = apps.get_model("compras", "SolicitudCotizacion")
    Detalle = apps.get_model("compras", "DetalleSolicitudCotizacion")
    alias = schema_editor.connection.alias
    for solicitud in Solicitud.objects.using(alias).select_related("proveedor").iterator():
        Solicitud.objects.using(alias).filter(pk=solicitud.pk).update(
            proveedor_nombre=solicitud.proveedor.razon_social, proveedor_email=solicitud.proveedor.email)
        cantidades = defaultdict(int)
        modelos = {}
        for item in solicitud.items.using(alias).select_related("modelo__marca"):
            cantidades[item.modelo_id] += item.cantidad
            modelos[item.modelo_id] = item.modelo
        for modelo_id, cantidad in cantidades.items():
            modelo = modelos[modelo_id]
            Detalle.objects.using(alias).get_or_create(solicitud_id=solicitud.pk, modelo_id=modelo_id,
                defaults={"cantidad": cantidad, "nombre_modelo": modelo.nombre, "nombre_marca": modelo.marca.nombre})


class Migration(migrations.Migration):
    dependencies = [("compras", "0003_solicitudcotizacion_proveedor_email_and_more")]
    operations = [migrations.RunPython(preservar, migrations.RunPython.noop)]
