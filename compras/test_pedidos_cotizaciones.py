from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch

from django.contrib.auth.models import User, Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, SimpleTestCase
from django.urls import reverse
from django.utils import timezone

from . import servicios, servicios_pedidos as negocio
from .models import (Marca, Modelo, Sucursal, UsuarioSucursal, Proveedor, ItemFaltante,
                     ListadoFaltantes, SolicitudCotizacion, DetalleSolicitudCotizacion,
                     EmisionSolicitud, Cotizacion, DetalleCotizacion)


class PedidosCotizacionesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rosario = Sucursal.objects.create(nombre="Rosario")
        cls.mendoza = Sucursal.objects.create(nombre="Mendoza")
        cls.marca = Marca.objects.create(nombre="Marca A")
        cls.otra_marca = Marca.objects.create(nombre="Marca B")
        cls.modelo = Modelo.objects.create(nombre="Moto A", marca=cls.marca)
        cls.otro = Modelo.objects.create(nombre="Moto B", marca=cls.marca)
        cls.incompatible = Modelo.objects.create(nombre="Moto C", marca=cls.otra_marca)
        for nombre, rol in [("ventas", "Ventas"), ("ventas_mendoza", "Ventas"),
                            ("compras", "Compras"), ("finanzas", "Finanzas"),
                            ("admin", "Administrador"), ("sin_rol", None)]:
            usuario = User.objects.create_user(nombre)
            if rol:
                usuario.groups.add(Group.objects.get_or_create(name=rol)[0])
            setattr(cls, nombre, usuario)
        UsuarioSucursal.objects.create(usuario=cls.ventas, sucursal=cls.rosario)
        UsuarioSucursal.objects.create(usuario=cls.ventas_mendoza, sucursal=cls.mendoza)
        cls.proveedor = Proveedor.objects.create(razon_social="Proveedor A", email="a@ejemplo.com", es_fijo=True)
        cls.proveedor.marcas.add(cls.marca)
        cls.proveedor_b = Proveedor.objects.create(razon_social="Proveedor B", email="b@ejemplo.com")
        cls.proveedor_b.marcas.add(cls.marca)

    def pedido(self, usuario=None, modelo=None, cantidad=3, fecha=None):
        pedido = negocio.registrar_pedido(usuario or self.ventas,
            [{"modelo": modelo or self.modelo, "cantidad": cantidad, "motivo": "VENTA"}])
        if fecha:
            ListadoFaltantes.objects.filter(pk=pedido.pk).update(fecha=fecha, quincena=servicios.quincena(fecha))
            pedido.refresh_from_db()
        return pedido

    def emitir(self, modelos=None, proveedores=None, clave=None, periodo=None, usuario=None):
        return negocio.emitir_solicitudes(usuario or self.compras, modelos or [self.modelo],
            proveedores if proveedores is not None else [self.proveedor], "MAIL", clave or uuid4(), periodo)

    def cotizar(self, solicitud, cantidades=None, precio="123.45", fecha=None, usuario=None):
        detalles = list(solicitud.detalles.all())
        if cantidades is None:
            cantidades = {d.pk: d.cantidad for d in detalles}
        filas = [{"detalle_solicitud": d, "cantidad": cantidades[d.pk], "precio_unitario": Decimal(precio)}
                 for d in detalles if d.pk in cantidades]
        return negocio.registrar_cotizacion(usuario or self.compras, solicitud, fecha or timezone.localdate(), filas)

    def solicitud(self):
        self.pedido()
        return self.emitir().solicitudes.get()

    def test_pedidos_sucursal_y_compras_global(self):
        propio = self.pedido()
        ajeno = self.pedido(self.ventas_mendoza)
        self.assertEqual(list(negocio.consultar_pedidos(self.ventas)), [propio])
        self.assertEqual(negocio.consultar_pedidos(self.compras).count(), 2)
        self.client.force_login(self.ventas)
        self.assertEqual(self.client.get(reverse("faltantes_detalle", args=[ajeno.pk])).status_code, 404)
        self.assertContains(self.client.get(reverse("faltantes_detalle", args=[propio.pk])), "Moto A")
        respuesta = self.client.get(reverse("faltantes_lista"), {"sucursal": self.mendoza.pk})
        self.assertTrue(respuesta.context["form"].errors)
        self.assertEqual(len(respuesta.context["listados"]), 0)
        self.client.force_login(self.compras)
        self.assertContains(self.client.get(reverse("faltantes_lista")), "Mendoza")

    def test_registro_ignora_sucursal_cliente_y_servicio_rechaza_ajena(self):
        self.client.force_login(self.ventas)
        respuesta = self.client.post(reverse("faltantes_nuevo"), {"sucursal": self.mendoza.pk,
            "filas-TOTAL_FORMS": 1, "filas-INITIAL_FORMS": 0, "filas-0-modelo": self.modelo.pk,
            "filas-0-cantidad": 2, "filas-0-motivo": "VENTA"})
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(ListadoFaltantes.objects.get().sucursal, self.rosario)
        with self.assertRaises(PermissionDenied):
            negocio.registrar_pedido(self.ventas, [{"modelo": self.modelo, "cantidad": 1}], self.mendoza)
        UsuarioSucursal.objects.filter(usuario=self.ventas).delete()
        with self.assertRaises(PermissionDenied):
            self.pedido()

    def test_pedidos_invalidos_no_crean_cabecera(self):
        for filas in [[], [{"modelo": self.modelo, "cantidad": 0}],
                      [{"modelo": self.modelo, "cantidad": 2, "motivo": "OTRO"}]]:
            with self.assertRaises(ValidationError):
                negocio.registrar_pedido(self.ventas, filas)
        self.assertFalse(ListadoFaltantes.objects.exists())

    def test_consolidacion_limites_quincenales_y_pendientes(self):
        for fecha, cantidad in [(date(2024, 2, 1), 1), (date(2024, 2, 15), 2),
                                 (date(2024, 2, 16), 4), (date(2024, 2, 29), 8), (date(2024, 3, 1), 16)]:
            self.pedido(cantidad=cantidad, fecha=fecha)
        self.pedido(self.ventas_mendoza, cantidad=10, fecha=date(2024, 2, 15))
        self.assertEqual(list(negocio.consolidar_pedidos(self.ventas, quincena=date(2024, 2, 15)))[0]["total"], 3)
        self.assertEqual(list(negocio.consolidar_pedidos(self.compras, quincena=date(2024, 2, 29)))[0]["total"], 12)
        self.assertEqual(list(negocio.consolidar_pedidos(self.compras, fecha=date(2024, 2, 15)))[0]["total"], 12)
        self.emitir(periodo=date(2024, 2, 15))
        self.assertEqual(list(negocio.consolidar_pedidos(self.compras, pendientes=True))[0]["total"], 28)
        self.assertEqual(list(negocio.consolidar_pedidos(self.compras, quincena=date(2024, 2, 1), pendientes=True)), [])

    def test_solicitud_detalle_agregado_y_proveedores_habituales(self):
        self.pedido(cantidad=2)
        self.pedido(self.ventas_mendoza, cantidad=3)
        emision = self.emitir(proveedores=[self.proveedor, self.proveedor_b])
        self.assertEqual(emision.solicitudes.count(), 2)
        for solicitud in emision.solicitudes.all():
            self.assertEqual(solicitud.detalles.get().cantidad, 5)
            self.assertEqual(solicitud.items.count(), 2)
        self.assertFalse(ItemFaltante.objects.filter(solicitado=False).exists())
        self.assertTrue(Proveedor.objects.get(pk=self.proveedor.pk).es_fijo)

    def test_proveedor_inactivo_incompatible_o_vacio_revierte(self):
        self.pedido()
        Proveedor.objects.filter(pk=self.proveedor.pk).update(activo=False)
        with self.assertRaises(ValidationError):
            self.emitir()
        Proveedor.objects.filter(pk=self.proveedor.pk).update(activo=True)
        self.proveedor.marcas.clear()
        with self.assertRaises(ValidationError):
            self.emitir()
        with self.assertRaises(ValidationError):
            self.emitir(proveedores=[])
        self.assertFalse(EmisionSolicitud.objects.exists())
        self.assertFalse(SolicitudCotizacion.objects.exists())
        self.assertFalse(ItemFaltante.objects.get().solicitado)

    def test_reenvio_misma_clave_y_conflicto(self):
        self.pedido()
        clave = uuid4()
        emision = self.emitir(clave=clave)
        self.pedido(cantidad=1)
        self.assertEqual(self.emitir(clave=clave).pk, emision.pk)
        self.assertEqual(SolicitudCotizacion.objects.count(), 1)
        self.assertEqual(ItemFaltante.objects.filter(solicitado=False).count(), 1)
        with self.assertRaises(ValidationError):
            self.emitir(clave=clave, proveedores=[self.proveedor_b])
        with self.assertRaises(ValidationError):
            self.emitir(clave=clave, usuario=self.admin)

    def test_otra_clave_no_repite_faltantes_solicitados(self):
        self.pedido()
        self.emitir()
        with self.assertRaises(ValidationError):
            self.emitir()
        self.assertEqual(SolicitudCotizacion.objects.count(), 1)
        self.assertEqual(EmisionSolicitud.objects.count(), 1)

    def test_error_de_detalles_revierte_emision_y_marcado(self):
        self.pedido()
        with patch("compras.servicios_pedidos.DetalleSolicitudCotizacion.objects.bulk_create", side_effect=RuntimeError("fallo")):
            with self.assertRaises(RuntimeError):
                self.emitir()
        self.assertFalse(ItemFaltante.objects.get().solicitado)
        self.assertFalse(EmisionSolicitud.objects.exists())
        self.assertFalse(SolicitudCotizacion.objects.exists())

    def test_historia_no_cambia_con_modelo_proveedor_o_faltante(self):
        solicitud = self.solicitud()
        ItemFaltante.objects.update(cantidad=99)
        Modelo.objects.filter(pk=self.modelo.pk).update(nombre="Nuevo nombre")
        Marca.objects.filter(pk=self.marca.pk).update(nombre="Nueva marca")
        Proveedor.objects.filter(pk=self.proveedor.pk).update(razon_social="Nuevo proveedor")
        detalle = solicitud.detalles.get()
        self.assertEqual((detalle.nombre_modelo, detalle.nombre_marca, detalle.cantidad), ("Moto A", "Marca A", 3))
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.proveedor_nombre, "Proveedor A")
        self.client.force_login(self.compras)
        respuesta = self.client.get(reverse("solicitud_detalle", args=[solicitud.pk]))
        self.assertContains(respuesta, "Proveedor A")
        self.assertContains(respuesta, "Moto A")
        self.assertNotContains(respuesta, "Nuevo nombre")

    def test_cotizacion_importes_decimales_y_reenvio(self):
        solicitud = self.solicitud()
        oferta = self.cotizar(solicitud, precio="0.10")
        self.assertEqual(oferta.total, Decimal("0.30"))
        self.assertTrue(oferta.completa)
        self.assertEqual(self.cotizar(solicitud, precio="0.10").pk, oferta.pk)
        with self.assertRaises(ValidationError):
            self.cotizar(solicitud, precio="0.20")
        self.assertEqual(Cotizacion.objects.count(), 1)
        self.assertEqual(DetalleCotizacion.objects.count(), 1)

    def test_cotizacion_parcial_y_comparacion_por_cesta(self):
        self.pedido()
        self.pedido(modelo=self.otro, cantidad=2)
        emision = self.emitir(modelos=[self.modelo, self.otro], proveedores=[self.proveedor, self.proveedor_b])
        a, b = list(emision.solicitudes.order_by("pk"))
        completa = self.cotizar(a)
        parcial = self.cotizar(b, cantidades={b.detalles.first().pk: 1})
        self.pedido(cantidad=8)
        diferente = self.cotizar(self.emitir().solicitudes.get())
        grupos = negocio.comparar_cotizaciones(self.compras)
        self.assertEqual(sorted(len(g["ofertas"]) for g in grupos), [1, 2])
        grupo = negocio.comparar_cotizaciones(self.compras, a)[0]
        self.assertEqual({f["cotizacion"].pk for f in grupo["ofertas"]}, {completa.pk, parcial.pk})
        self.assertEqual(sum(f["completa"] for f in grupo["ofertas"]), 1)
        self.assertFalse(parcial.completa)
        self.assertNotIn(diferente.pk, {f["cotizacion"].pk for f in grupo["ofertas"]})
        self.client.force_login(self.compras)
        self.assertContains(self.client.get(reverse("cotizacion_comparar")), "subtotal no comparable")

    def test_validacion_cantidades_precios_y_fecha(self):
        solicitud = self.solicitud()
        detalle = solicitud.detalles.get()
        for cantidad, precio in [(0, "2"), (-1, "2"), (4, "2"), (1, "0"), (1, "-1"),
                                (1, "1.001"), (1, "NaN"), (1, "Infinity"), (1, "10000000000.00")]:
            with self.subTest(cantidad=cantidad, precio=precio), self.assertRaises(ValidationError):
                negocio.registrar_cotizacion(self.compras, solicitud, timezone.localdate(),
                    [{"detalle_solicitud": detalle, "cantidad": cantidad, "precio_unitario": precio}])
        for fecha in [solicitud.fecha - timedelta(days=1), timezone.localdate() + timedelta(days=1)]:
            with self.assertRaises(ValidationError):
                self.cotizar(solicitud, fecha=fecha)
        self.assertFalse(Cotizacion.objects.exists())

    def test_modelos_ajenos_duplicados_y_oferta_vacia(self):
        a = self.solicitud()
        self.pedido(modelo=self.otro)
        b = self.emitir(modelos=[self.otro]).solicitudes.get()
        for filas in [[], [{"detalle_solicitud": b.detalles.get(), "cantidad": 1, "precio_unitario": "2"}],
                      [{"detalle_solicitud": a.detalles.get(), "cantidad": 1, "precio_unitario": "2"}] * 2]:
            with self.assertRaises(ValidationError):
                negocio.registrar_cotizacion(self.compras, a, timezone.localdate(), filas)
        self.assertFalse(Cotizacion.objects.exists())

    def test_error_oferta_revierte_cabecera(self):
        solicitud = self.solicitud()
        with patch("compras.servicios_pedidos.DetalleCotizacion.objects.bulk_create", side_effect=RuntimeError("fallo")):
            with self.assertRaises(RuntimeError):
                self.cotizar(solicitud)
        self.assertFalse(Cotizacion.objects.exists())
        self.assertFalse(DetalleCotizacion.objects.exists())

    def test_baja_posterior_preserva_y_admite_respuesta(self):
        solicitud = self.solicitud()
        negocio.baja_proveedor(self.compras, self.proveedor)
        self.assertTrue(self.cotizar(solicitud).completa)
        self.assertTrue(SolicitudCotizacion.objects.filter(pk=solicitud.pk).exists())

    def test_permisos_servicios(self):
        solicitud = self.solicitud()
        for usuario in [self.ventas, self.ventas_mendoza, self.finanzas, self.sin_rol]:
            for operacion in [lambda: self.emitir(usuario=usuario),
                              lambda: self.cotizar(solicitud, usuario=usuario),
                              lambda: negocio.comparar_cotizaciones(usuario),
                              lambda: negocio.consultar_proveedores(usuario),
                              lambda: negocio.baja_proveedor(usuario, self.proveedor)]:
                with self.assertRaises(PermissionDenied):
                    operacion()
        with self.assertRaises(PermissionDenied):
            negocio.consultar_pedidos(self.finanzas)
        with self.assertRaises(PermissionDenied):
            negocio.registrar_pedido(self.compras, [{"modelo": self.modelo, "cantidad": 1}], self.rosario)

    def test_permisos_rutas_y_solicitudes_sin_autenticacion(self):
        solicitud = self.solicitud()
        oferta = self.cotizar(solicitud)
        rutas = [reverse("cotizacion_lista"), reverse("cotizacion_nueva"), reverse("cotizacion_comparar"),
                 reverse("solicitud_detalle", args=[solicitud.pk]), reverse("cotizacion_recibida", args=[solicitud.pk]),
                 reverse("cotizacion_detalle", args=[oferta.pk])]
        for ruta in rutas:
            self.assertEqual(self.client.get(ruta).status_code, 302)
        for usuario in [self.ventas, self.finanzas, self.sin_rol]:
            self.client.force_login(usuario)
            for ruta in rutas:
                self.assertEqual(self.client.get(ruta).status_code, 403)
        self.client.force_login(self.compras)
        for ruta in rutas:
            self.assertIn(self.client.get(ruta).status_code, [200, 302])

    def test_post_emision_y_reenvio_desde_formulario(self):
        self.pedido()
        self.client.force_login(self.compras)
        datos = {"modelos": [self.modelo.pk], "proveedores": [self.proveedor.pk], "medio": "MAIL", "clave_operacion": uuid4()}
        for _ in range(2):
            self.assertRedirects(self.client.post(reverse("cotizacion_nueva"), datos), reverse("cotizacion_lista"))
        self.assertEqual(SolicitudCotizacion.objects.count(), 1)

    def test_post_cotizacion_y_errores_visibles(self):
        solicitud = self.solicitud()
        self.client.force_login(self.compras)
        ruta = reverse("cotizacion_recibida", args=[solicitud.pk])
        self.assertContains(self.client.get(ruta), "Moto A")
        datos = {"fecha": timezone.localdate().isoformat(), "filas-TOTAL_FORMS": 1, "filas-INITIAL_FORMS": 1,
                 "filas-0-detalle_solicitud": solicitud.detalles.get().pk, "filas-0-cantidad": 3,
                 "filas-0-precio_unitario": "12.50"}
        self.assertEqual(self.client.post(ruta, datos).status_code, 302)
        self.assertEqual(self.client.post(ruta, datos).status_code, 302)
        self.assertEqual(Cotizacion.objects.get().total, Decimal("37.50"))
        datos["filas-0-cantidad"] = 99
        self.assertContains(self.client.post(ruta, datos), "La cantidad supera la solicitada")

    def test_restricciones_de_base_y_admin_solo_lectura(self):
        solicitud = self.solicitud()
        detalle = solicitud.detalles.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            DetalleSolicitudCotizacion.objects.create(solicitud=solicitud, modelo=self.modelo,
                cantidad=1, nombre_modelo="A", nombre_marca="A")
        oferta = self.cotizar(solicitud)
        with self.assertRaises(IntegrityError), transaction.atomic():
            oferta.detalles.update(precio_unitario=-1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cotizacion.objects.create(solicitud=solicitud, usuario=self.compras, fecha=timezone.localdate())
        from django.contrib import admin
        from django.test import RequestFactory
        request = RequestFactory().get("/admin/")
        request.user = self.admin
        for modelo in [SolicitudCotizacion, EmisionSolicitud, DetalleSolicitudCotizacion, Cotizacion, DetalleCotizacion]:
            configuracion = admin.site._registry[modelo]
            self.assertFalse(configuracion.has_add_permission(request))
            self.assertFalse(configuracion.has_change_permission(request))
            self.assertFalse(configuracion.has_delete_permission(request))


    def test_centavos_en_importes_grandes_sqlite_y_limite_explicito(self):
        self.pedido(cantidad=100)
        solicitud = self.emitir().solicitudes.get()
        oferta = self.cotizar(solicitud, precio="9999999999.99")
        oferta.refresh_from_db()
        self.assertEqual(oferta.detalles.get().importe, Decimal("999999999999.00"))
        self.pedido(cantidad=101)
        solicitud = self.emitir().solicitudes.get()
        with self.assertRaises(ValidationError):
            self.cotizar(solicitud, precio="9999999999.99")
        self.assertEqual(Cotizacion.objects.count(), 1)

    def test_filtro_solicitud_quincenal_no_incluye_otro_periodo(self):
        primero = self.pedido(cantidad=2, fecha=date(2024, 2, 15))
        segundo = self.pedido(cantidad=7, fecha=date(2024, 2, 16))
        solicitud = self.emitir(periodo=date(2024, 2, 1)).solicitudes.get()
        self.assertEqual(solicitud.detalles.get().cantidad, 2)
        self.assertTrue(primero.items.get().solicitado)
        self.assertFalse(segundo.items.get().solicitado)
        self.client.force_login(self.compras)
        respuesta = self.client.get(reverse("cotizacion_nueva"), {"quincena": "2024-02-16"})
        self.assertEqual(list(respuesta.context["lineas"])[0]["total"], 7)

    def test_formulario_rechaza_proveedor_inactivo_y_datos_incompletos(self):
        self.pedido()
        self.client.force_login(self.compras)
        Proveedor.objects.filter(pk=self.proveedor.pk).update(activo=False)
        respuesta = self.client.post(reverse("cotizacion_nueva"), {"modelos": [self.modelo.pk],
            "proveedores": [self.proveedor.pk], "medio": "MAIL", "clave_operacion": uuid4()})
        self.assertTrue(respuesta.context["form"].errors)
        self.assertFalse(SolicitudCotizacion.objects.exists())
        Proveedor.objects.filter(pk=self.proveedor.pk).update(activo=True)
        solicitud = self.emitir().solicitudes.get()
        respuesta = self.client.post(reverse("cotizacion_recibida", args=[solicitud.pk]), {
            "fecha": timezone.localdate().isoformat(), "filas-TOTAL_FORMS": 1, "filas-INITIAL_FORMS": 1,
            "filas-0-detalle_solicitud": solicitud.detalles.get().pk, "filas-0-cantidad": 1})
        self.assertContains(respuesta, "Complete cantidad y precio")
        self.assertFalse(Cotizacion.objects.exists())


    def test_fecha_solicitud_usa_calendario_local(self):
        self.pedido()
        with patch("compras.servicios_pedidos.timezone.localdate", return_value=date(2024, 2, 15)):
            solicitud = self.emitir().solicitudes.get()
            self.assertEqual(solicitud.fecha, date(2024, 2, 15))
            self.assertTrue(self.cotizar(solicitud, fecha=date(2024, 2, 15)).completa)


class SQLitePedidosTest(SimpleTestCase):
    def ejecutar_aislado(self, codigo):
        import subprocess
        import sys
        import tempfile
        from pathlib import Path
        cabecera = r"""
import os, sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
from django.conf import settings
settings.DATABASES['default']['NAME'] = sys.argv[1]
import django
django.setup()
"""
        with tempfile.TemporaryDirectory() as carpeta:
            resultado = subprocess.run([sys.executable, '-c', cabecera + codigo,
                str(Path(carpeta) / 'pedidos.sqlite3')], capture_output=True, text=True, timeout=60)
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)

    def test_migracion_preserva_solicitudes_anteriores(self):
        self.ejecutar_aislado(r"""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
executor = MigrationExecutor(connection)
anterior = [('compras', '0002_stock_ajustestock_usuariosucursal_venta_detalleventa_and_more')]
executor.migrate(anterior)
apps = executor.loader.project_state(anterior).apps
User = apps.get_model('auth', 'User')
Marca = apps.get_model('compras', 'Marca')
Modelo = apps.get_model('compras', 'Modelo')
Sucursal = apps.get_model('compras', 'Sucursal')
Listado = apps.get_model('compras', 'ListadoFaltantes')
Item = apps.get_model('compras', 'ItemFaltante')
Proveedor = apps.get_model('compras', 'Proveedor')
Solicitud = apps.get_model('compras', 'SolicitudCotizacion')
from datetime import date
u = User.objects.create(username='historico')
s = Sucursal.objects.create(nombre='Rosario')
m = Modelo.objects.create(nombre='Modelo viejo', marca=Marca.objects.create(nombre='Marca vieja'))
otro = Modelo.objects.create(nombre='Modelo cero', marca=m.marca)
l = Listado.objects.create(usuario=u, sucursal=s, fecha=date(2024, 2, 15), quincena='historica')
p = Proveedor.objects.create(razon_social='Proveedor viejo', email='p@e.com')
solicitud = Solicitud.objects.create(proveedor=p, medio='FAX')
items = [Item.objects.create(listado=l, modelo=m, cantidad=2, solicitado=True),
         Item.objects.create(listado=l, modelo=m, cantidad=3, solicitado=True),
         Item.objects.create(listado=l, modelo=otro, cantidad=0, solicitado=True)]
solicitud.items.set(items)
executor = MigrationExecutor(connection)
executor.migrate(executor.loader.graph.leaf_nodes())
from compras.models import SolicitudCotizacion, DetalleSolicitudCotizacion, ItemFaltante, Modelo as ModeloActual
actual = SolicitudCotizacion.objects.get(pk=solicitud.pk)
assert actual.items.count() == 3 and ItemFaltante.objects.count() == 3
assert actual.proveedor_nombre == 'Proveedor viejo' and actual.medio == 'FAX'
assert actual.emision_id is None
assert dict(actual.detalles.values_list('modelo_id', 'cantidad')) == {m.pk: 5, otro.pk: 0}
ItemFaltante.objects.update(cantidad=77)
ModeloActual.objects.filter(pk=m.pk).update(nombre='Renombrado')
detalle = actual.detalles.get(modelo_id=m.pk)
assert detalle.cantidad == 5 and detalle.nombre_modelo == 'Modelo viejo'
print('Migracion de historia y cantidades cero preservadas')
""")

    def test_emision_y_respuesta_concurrentes_sqlite_archivo(self):
        self.ejecutar_aislado(r"""
import time
from threading import Barrier
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from django.core.management import call_command
from django.contrib.auth.models import User, Group
from django.db import connections, OperationalError
from django.core.exceptions import ValidationError
from django.utils import timezone
from compras.models import Marca, Modelo, Sucursal, UsuarioSucursal, Proveedor, ItemFaltante, SolicitudCotizacion, Cotizacion
from compras.servicios_pedidos import registrar_pedido, emitir_solicitudes, registrar_cotizacion
call_command('migrate', verbosity=0)
u = User.objects.create_user('compras')
u.groups.add(Group.objects.create(name='Compras'))
v = User.objects.create_user('ventas')
v.groups.add(Group.objects.create(name='Ventas'))
s = Sucursal.objects.create(nombre='Rosario')
UsuarioSucursal.objects.create(usuario=v, sucursal=s)
m = Modelo.objects.create(nombre='A', marca=Marca.objects.create(nombre='K'))
p = Proveedor.objects.create(razon_social='P', email='p@e.com')
p.marcas.add(m.marca)
registrar_pedido(v, [{'modelo': m, 'cantidad': 3}])
def competir(claves, operacion):
    barrera = Barrier(2)
    def ejecutar(clave):
        usuario = User.objects.get(pk=u.pk)
        barrera.wait(timeout=10)
        try:
            for intento in range(100):
                try:
                    if operacion == 'emision':
                        resultado = emitir_solicitudes(usuario, [m], [p], 'MAIL', clave)
                    else:
                        solicitud = SolicitudCotizacion.objects.order_by("pk").first()
                        resultado = registrar_cotizacion(usuario, solicitud, timezone.localdate(),
                            [{'detalle_solicitud': solicitud.detalles.get(), 'cantidad': 3, 'precio_unitario': '2.10'}])
                    return ('ok', resultado.pk)
                except OperationalError as error:
                    if 'locked' not in str(error).lower():
                        raise
                    time.sleep(0.02)
                except ValidationError:
                    return ('rechazada', None)
            raise AssertionError('SQLite permanecio bloqueado')
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        return list(pool.map(ejecutar, claves))
clave = uuid4()
resultados = competir([clave, clave], 'emision')
assert resultados[0] == resultados[1] and resultados[0][0] == 'ok', resultados
assert SolicitudCotizacion.objects.count() == 1
registrar_pedido(v, [{'modelo': m, 'cantidad': 1}])
resultados = competir([uuid4(), uuid4()], 'emision')
assert sorted(r[0] for r in resultados) == ['ok', 'rechazada'], resultados
assert SolicitudCotizacion.objects.count() == 2
assert not ItemFaltante.objects.filter(solicitado=False).exists()
resultados = competir([None, None], 'respuesta')
assert resultados[0] == resultados[1] and resultados[0][0] == 'ok', resultados
assert Cotizacion.objects.count() == 1
assert Cotizacion.objects.get().total == __import__('decimal').Decimal('6.30')
print('Emisiones y cotizaciones concurrentes sin duplicados')
""")
