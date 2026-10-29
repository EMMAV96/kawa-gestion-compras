"""Datos ficticios, exclusivamente en una base de demo aislada y vacía."""
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone
from compras.models import (Marca, Modelo, Sucursal, UsuarioSucursal, Proveedor, Stock,
                            Venta, ListadoFaltantes, SolicitudCotizacion, Compra)
from compras import servicios, servicios_pedidos as pedidos, servicios_compras as compras

MARCADOR = "KAWA_DEMO_V1_COMPLETA"
CLAVES_RETIRADAS_SHA256 = {'2233423932474ac805e11eaad9d21427f2e04e5a5427836ab5791a3918dd3eff', 'f6b558d3ecfa598d83fc7a4d26eb3235b75d84aa5dfcc96df5468fd687e0c54a'}
USUARIOS = {
    "demo_admin": "Administrador", "demo_compras": "Compras", "demo_finanzas": "Finanzas",
    "demo_ventas_rosario": "Ventas", "demo_ventas_mendoza": "Ventas", "demo_ventas_cordoba": "Ventas",
}


def clave(nombre):
    return uuid5(NAMESPACE_URL, "kawa-demo-v1/" + nombre)


class Command(BaseCommand):
    help = "Carga una demo ficticia completa, solo con --settings=config.demo_settings y una base aislada vacía."

    def add_arguments(self, parser):
        parser.add_argument("--confirmar-demo-publica", action="store_true",
                            help="Confirmación manual: base PostgreSQL dedicada y vacía, datos ficticios.")

    def handle(self, *args, **options):
        nombre = str(connection.settings_dict["NAME"])
        en_memoria = nombre == ":memory:" or nombre.startswith("file:memorydb_")
        prueba_pg = (getattr(settings, "KAWA_TEST_DEMO", False)
                     and settings.SETTINGS_MODULE == "config.ci_postgres"
                     and nombre.startswith("test_") and connection.vendor == "postgresql")
        publica = getattr(settings, "KAWA_PUBLIC_DEMO", False)
        passwords = None
        marcador = MARCADOR
        if publica:
            if connection.vendor != "postgresql" or not options["confirmar_demo_publica"]:
                raise CommandError("La demo pública requiere PostgreSQL dedicado y --confirmar-demo-publica.")
            try:
                passwords = json.loads(os.environ.get("KAWA_DEMO_PASSWORDS", ""))
                if not isinstance(passwords, dict) or set(passwords) != set(USUARIOS):
                    raise ValueError
                if any(not isinstance(v, str) or len(v) < 12 or hashlib.sha256(v.encode()).hexdigest() in CLAVES_RETIRADAS_SHA256 for v in passwords.values()) or len(set(passwords.values())) != len(USUARIOS):
                    raise ValueError
                for username, password in passwords.items():
                    validate_password(password, User(username=username))
            except (ValueError, TypeError, ValidationError):
                raise CommandError("KAWA_DEMO_PASSWORDS debe contener seis claves únicas y fuertes, distintas de las locales. No se muestran sus valores.") from None
            marcador = "KAWA_PUBLIC_DEMO_V1_COMPLETA"
        elif (not getattr(settings, "KAWA_DEMO", False)
                or (connection.vendor != "sqlite" and not prueba_pg)
                or (not en_memoria and Path(nombre).resolve() == (settings.BASE_DIR / "db.sqlite3").resolve())):
            raise CommandError("Use --settings=config.demo_settings. No se permite cargar datos ficticios en la base habitual.")
        with transaction.atomic():
            if Group.objects.filter(name=marcador).exists():
                if User.objects.filter(username__in=USUARIOS).count() != len(USUARIOS):
                    raise CommandError("La demo marcada está incompleta. No se reconstruye ni sobrescribe: utilice otra base vacía.")
                self.stdout.write("La demo ya fue cargada. No se modificaron datos, grupos ni contraseñas.")
                return
            if any(modelo.objects.exists() for modelo in (User, Marca, Modelo, Sucursal, Proveedor,
                    Stock, Venta, ListadoFaltantes, SolicitudCotizacion, Compra)):
                raise CommandError("La base contiene información preexistente. Use otra base de demo vacía; no se sobrescribe ni elimina nada.")
            if not publica:
                password = getattr(settings, "KAWA_LOCAL_DEMO_PASSWORD", "") or os.environ.get("KAWA_LOCAL_DEMO_PASSWORD", "")
                if len(password) < 12:
                    raise CommandError("Configure KAWA_LOCAL_DEMO_PASSWORD con una clave exclusiva de al menos 12 caracteres.")
                passwords = {nombre: password for nombre in USUARIOS}
            self._cargar(passwords)
            Group.objects.create(name=marcador)
        self.stdout.write(self.style.SUCCESS("Demo ficticia cargada. Usuarios demo_*; credenciales y recorrido en docs/guia-demostracion-mvp.md."))
        for compra in Compra.objects.order_by("pk"):
            self.stdout.write(f"Compra {compra.pk}: {compra.get_procedimiento_display()} · {compra.get_estado_display()}")

    def _cargar(self, passwords):
        sucursales = {nombre: Sucursal.objects.create(nombre=nombre) for nombre in ("Rosario", "Mendoza", "Córdoba")}
        usuarios = {}
        for nombre, rol in USUARIOS.items():
            usuario = User.objects.create_user(username=nombre, password=passwords[nombre],
                first_name="Usuario ficticio", email=nombre + "@kawa.invalid")
            usuario.groups.add(Group.objects.get_or_create(name=rol)[0])
            usuarios[nombre] = usuario
        for ciudad, sufijo in [("Rosario", "rosario"), ("Mendoza", "mendoza"), ("Córdoba", "cordoba")]:
            UsuarioSucursal.objects.create(usuario=usuarios["demo_ventas_" + sufijo], sucursal=sucursales[ciudad])
        admin, comprador, finanzas = (usuarios[n] for n in ("demo_admin", "demo_compras", "demo_finanzas"))
        rosario, mendoza, cordoba = (usuarios["demo_ventas_" + n] for n in ("rosario", "mendoza", "cordoba"))
        aurora = Marca.objects.create(nombre="Ficticia Aurora")
        viento = Marca.objects.create(nombre="Ficticia Viento")
        urbana = Modelo.objects.create(nombre="Aurora Urbana 125", marca=aurora)
        ruta = Modelo.objects.create(nombre="Aurora Ruta 250", marca=aurora)
        sierra = Modelo.objects.create(nombre="Viento Sierra 200", marca=viento)
        for sucursal in sucursales.values():
            for modelo in [urbana, ruta, sierra]:
                servicios.ajustar_stock(admin, sucursal, modelo, 12, "Carga inicial ficticia de demostración")
        servicios.registrar_venta(rosario, [{"modelo": urbana, "cantidad": 2}], clave("venta-rosario"))
        servicios.registrar_venta(mendoza, [{"modelo": ruta, "cantidad": 1}], clave("venta-mendoza"))
        proveedores = []
        for nombre, email, habitual in [("Distribuidora Ejemplo Habitual", "habitual@proveedor.invalid", True),
                ("Mayorista Ejemplo Norte", "norte@proveedor.invalid", False),
                ("Mayorista Ejemplo Sur", "sur@proveedor.invalid", False)]:
            proveedor = Proveedor.objects.create(razon_social=nombre, email=email, es_fijo=habitual)
            proveedor.marcas.set([aurora, viento])
            proveedores.append(proveedor)
        habitual, norte, sur = proveedores

        def pedido(vendedor, modelo, cantidad):
            return pedidos.registrar_pedido(vendedor, [{"modelo": modelo, "cantidad": cantidad, "motivo": "VENTA"}])

        def respuesta(solicitud, precio, parcial=False):
            return pedidos.registrar_cotizacion(comprador, solicitud, timezone.localdate(), [
                {"detalle_solicitud": d, "cantidad": d.cantidad - 1 if parcial else d.cantidad,
                 "precio_unitario": precio} for d in solicitud.detalles.all()])

        # Cotizaciones primero: su consolidación toma todos los pendientes del
        # modelo. Los pedidos libres para demostrar quedan al final de la carga.
        for etiqueta, cantidad, destino in [("espera", 2, "PENDIENTE_COTIZACIONES"),
                ("evaluacion", 3, "EN_EVALUACION"), ("documentada", 2, "DOCUMENTACION_PREPARADA"),
                ("aprobada", 1, "APROBADA")]:
            pedido(mendoza, ruta, cantidad)
            emision = pedidos.emitir_solicitudes(comprador, [ruta], [norte, sur], "MAIL", clave("solicitud-" + etiqueta))
            solicitud = emision.solicitudes.get(proveedor=norte)
            oferta = None
            if etiqueta != "espera":
                oferta = respuesta(solicitud, "2100000.50")
            if etiqueta == "evaluacion":
                respuesta(emision.solicitudes.get(proveedor=sur), "1900000.00", parcial=True)
            compra = compras.preparar_compra(comprador, "COTIZACION", clave("compra-b-" + etiqueta), solicitud=solicitud)
            compra = compras.evaluar_solicitud(comprador, compra)
            if destino in ("DOCUMENTACION_PREPARADA", "APROBADA"):
                compra = compras.seleccionar_oferta(comprador, compra, oferta)
                compras.generar_documento(comprador, compra)
            if destino == "APROBADA":
                compra = compras.solicitar_aprobacion(comprador, compra)
                compras.decidir_compra(finanzas, compra, "APROBADA", "Ejemplo ficticio aprobado")

        for etiqueta, vendedor, cantidad, destino in [("preparacion", rosario, 1, "EN_PREPARACION"),
                ("pendiente", cordoba, 2, "PENDIENTE_APROBACION"),
                ("aprobada", mendoza, 1, "APROBADA"), ("rechazada", rosario, 3, "RECHAZADA")]:
            origen = pedido(vendedor, urbana, cantidad)
            compra = compras.preparar_compra(comprador, "HABITUAL", clave("compra-a-" + etiqueta),
                proveedor=habitual, items=list(origen.items.all()), precios={urbana.pk: "1500000.25"})
            if destino != "EN_PREPARACION":
                compras.generar_documento(comprador, compra)
                compra = compras.solicitar_aprobacion(comprador, compra)
            if destino in ("APROBADA", "RECHAZADA"):
                compras.decidir_compra(finanzas, compra, destino,
                    "Ejemplo ficticio: presupuesto insuficiente" if destino == "RECHAZADA" else "Ejemplo ficticio aprobado")
        pedido(rosario, urbana, 2)  # Disponible para demostrar procedimiento A.
        pedido(mendoza, ruta, 4)   # Disponible para demostrar procedimiento B.
