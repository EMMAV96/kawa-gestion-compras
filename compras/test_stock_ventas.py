from .test_credentials import TEST_PASSWORD
from datetime import date
from uuid import uuid4
from unittest.mock import patch

from django.contrib.auth.models import User, Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, SimpleTestCase
from django.urls import reverse

from . import servicios
from .forms import AdminUserForm
from .models import (Marca, Modelo, Sucursal, UsuarioSucursal, Stock, Venta,
                     DetalleVenta, AjusteStock)


class StockVentasTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rosario = Sucursal.objects.create(nombre="Rosario")
        cls.mendoza = Sucursal.objects.create(nombre="Mendoza")
        cls.cordoba = Sucursal.objects.create(nombre="Cordoba")
        marca = Marca.objects.create(nombre="Kawa")
        cls.modelo = Modelo.objects.create(nombre="A", marca=marca)
        cls.otro = Modelo.objects.create(nombre="B", marca=marca)
        for nombre, rol in [("ventas", "Ventas"), ("otras_ventas", "Ventas"),
                            ("compras", "Compras"), ("finanzas", "Finanzas"),
                            ("admin", "Administrador"), ("sin_rol", None)]:
            usuario = User.objects.create_user(nombre)
            if rol:
                usuario.groups.add(Group.objects.get_or_create(name=rol)[0])
            setattr(cls, nombre, usuario)
        UsuarioSucursal.objects.create(usuario=cls.ventas, sucursal=cls.rosario)
        UsuarioSucursal.objects.create(usuario=cls.otras_ventas, sucursal=cls.mendoza)
        Stock.objects.create(sucursal=cls.rosario, modelo=cls.modelo, cantidad=10)
        Stock.objects.create(sucursal=cls.rosario, modelo=cls.otro, cantidad=3)
        Stock.objects.create(sucursal=cls.mendoza, modelo=cls.modelo, cantidad=5)

    def vender(self, cantidad=2, clave=None, filas=None, usuario=None):
        return servicios.registrar_venta(usuario or self.ventas,
            filas if filas is not None else [{"modelo": self.modelo, "cantidad": cantidad}], clave or uuid4())

    def cantidad(self, modelo=None):
        return Stock.objects.get(sucursal=self.rosario, modelo=modelo or self.modelo).cantidad

    def test_stock_unico_y_no_negativo_en_base(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Stock.objects.create(sucursal=self.rosario, modelo=self.modelo)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Stock.objects.filter(sucursal=self.rosario).update(cantidad=-1)

    def test_ajuste_inicial_incremento_y_disminucion(self):
        servicios.ajustar_stock(self.admin, self.cordoba, self.modelo, 4, "Inicial")
        servicios.ajustar_stock(self.admin, self.rosario, self.modelo, -2, "Correccion")
        self.assertEqual(self.cantidad(), 8)
        self.assertEqual(AjusteStock.objects.count(), 2)
        self.assertEqual(Stock.objects.get(sucursal=self.cordoba).cantidad, 4)

    def test_ajuste_invalido_no_deja_registro(self):
        for variacion, motivo in [(0, "X"), (1.5, "X"), (True, "X"), (2, " "), (-11, "X")]:
            with self.subTest(variacion=variacion), self.assertRaises(ValidationError):
                servicios.ajustar_stock(self.admin, self.rosario, self.modelo, variacion, motivo)
        self.assertEqual(self.cantidad(), 10)
        self.assertFalse(AjusteStock.objects.exists())
        with self.assertRaises(ValidationError):
            servicios.ajustar_stock(self.admin, self.cordoba, self.modelo, -1, "X")
        self.assertFalse(Stock.objects.filter(sucursal=self.cordoba).exists())

    def test_ajuste_exclusivo_admin_en_servicio_y_vista(self):
        for usuario in [self.ventas, self.compras, self.finanzas, self.sin_rol]:
            with self.assertRaises(PermissionDenied):
                servicios.ajustar_stock(usuario, self.rosario, self.modelo, 1, "X")
            self.client.force_login(usuario)
            self.assertEqual(self.client.post(reverse("stock_ajuste"), {}).status_code, 403)

    def test_venta_descuenta_y_asocia_usuario_y_sucursal(self):
        venta = self.vender()
        self.assertEqual(venta.usuario, self.ventas)
        self.assertEqual(venta.sucursal, self.rosario)
        self.assertEqual(venta.detalles.get().cantidad, 2)
        self.assertEqual(self.cantidad(), 8)
        self.assertEqual(Stock.objects.get(sucursal=self.mendoza).cantidad, 5)

    def test_varios_modelos_y_filas_repetidas(self):
        venta = self.vender(filas=[{"modelo": self.modelo, "cantidad": 2},
                                  {"modelo": self.otro, "cantidad": 3},
                                  {"modelo": self.modelo, "cantidad": 1}])
        self.assertEqual(venta.detalles.count(), 2)
        self.assertEqual(self.cantidad(), 7)
        self.assertEqual(self.cantidad(self.otro), 0)

    def test_cantidades_invalidas_y_venta_vacia(self):
        for cantidad in [0, -1, True, 1.5, "2", None]:
            with self.subTest(cantidad=cantidad), self.assertRaises(ValidationError):
                self.vender(cantidad)
        with self.assertRaises(ValidationError):
            self.vender(filas=[])
        self.assertFalse(Venta.objects.exists())
        self.assertEqual(self.cantidad(), 10)

    def test_faltante_y_stock_insuficiente_revierten_toda_la_venta(self):
        for cantidad in [4, 99]:
            with self.assertRaises(ValidationError):
                self.vender(filas=[{"modelo": self.modelo, "cantidad": 2},
                                  {"modelo": self.otro, "cantidad": cantidad}])
            self.assertEqual(self.cantidad(), 10)
            self.assertFalse(Venta.objects.exists())
            self.assertFalse(DetalleVenta.objects.exists())
        Stock.objects.filter(sucursal=self.rosario, modelo=self.otro).delete()
        with self.assertRaises(ValidationError):
            self.vender(filas=[{"modelo": self.otro, "cantidad": 1}])

    def test_error_inesperado_revierte_stock_y_cabecera(self):
        with patch("compras.servicios.DetalleVenta.objects.create", side_effect=RuntimeError("fallo")):
            with self.assertRaises(RuntimeError):
                self.vender()
        self.assertFalse(Venta.objects.exists())
        self.assertEqual(self.cantidad(), 10)

    def test_reenvio_no_duplica_descuento_y_conflicto_se_rechaza(self):
        clave = uuid4()
        venta = self.vender(clave=clave)
        self.assertEqual(self.vender(clave=clave).pk, venta.pk)
        self.assertEqual(self.cantidad(), 8)
        self.assertEqual(Venta.objects.count(), 1)
        with self.assertRaises(ValidationError):
            self.vender(cantidad=3, clave=clave)
        with self.assertRaises(ValidationError):
            self.vender(usuario=self.otras_ventas, clave=clave)
        self.assertEqual(self.cantidad(), 8)

    def test_clave_invalida_y_usuario_sin_sucursal(self):
        with self.assertRaises(ValidationError):
            servicios.registrar_venta(self.ventas, [{"modelo": self.modelo, "cantidad": 1}], "invalida")
        UsuarioSucursal.objects.filter(usuario=self.ventas).delete()
        with self.assertRaises(PermissionDenied):
            self.vender()
        self.client.force_login(self.ventas)
        self.assertEqual(self.client.get(reverse("venta_nueva")).status_code, 403)

    def test_roles_no_pueden_vender_por_servicio(self):
        for usuario in [self.compras, self.finanzas, self.admin, self.sin_rol]:
            with self.assertRaises(PermissionDenied):
                self.vender(usuario=usuario)
        self.ventas.is_active = False
        with self.assertRaises(PermissionDenied):
            self.vender()

    def datos_venta(self, clave=None):
        return {"clave_operacion": str(clave or uuid4()), "filas-TOTAL_FORMS": 1,
                "filas-INITIAL_FORMS": 0, "filas-0-modelo": self.modelo.pk, "filas-0-cantidad": 2}

    def test_post_venta_reenvio_y_detalle(self):
        self.client.force_login(self.ventas)
        datos = self.datos_venta()
        respuesta = self.client.post(reverse("venta_nueva"), datos)
        venta = Venta.objects.get()
        self.assertRedirects(respuesta, reverse("venta_detalle", args=[venta.pk]))
        self.assertRedirects(self.client.post(reverse("venta_nueva"), datos), respuesta.url)
        self.assertEqual(self.cantidad(), 8)
        self.assertContains(self.client.get(respuesta.url), "Rosario")

    def test_no_puede_inyectar_otra_sucursal(self):
        self.client.force_login(self.ventas)
        datos = self.datos_venta()
        datos["sucursal"] = self.mendoza.pk
        self.assertEqual(self.client.post(reverse("venta_nueva"), datos).status_code, 403)
        self.assertFalse(Venta.objects.exists())

    def test_consultas_se_limitan_a_sucursal(self):
        venta = self.vender()
        otra = self.vender(usuario=self.otras_ventas)
        self.client.force_login(self.ventas)
        self.assertEqual(self.client.get(reverse("venta_detalle", args=[otra.pk])).status_code, 404)
        self.assertEqual(list(servicios.consultar_ventas(self.ventas)), [venta])
        self.assertFalse(servicios.consultar_stock(self.ventas).filter(sucursal=self.mendoza).exists())
        respuesta = self.client.get(reverse("stock_lista"), {"sucursal": self.mendoza.pk})
        self.assertTrue(respuesta.context["form"].errors)
        self.assertEqual(len(respuesta.context["stock"]), 0)
        for usuario in [self.compras, self.finanzas, self.admin]:
            self.assertEqual(servicios.consultar_ventas(usuario).count(), 2)

    def test_permisos_de_pantallas_y_autenticacion(self):
        consultas = ["stock_lista", "venta_lista", "venta_resumen"]
        for ruta in consultas + ["stock_ajuste", "venta_nueva"]:
            self.assertEqual(self.client.get(reverse(ruta)).status_code, 302)
        for usuario in [self.ventas, self.compras, self.finanzas, self.admin]:
            self.client.force_login(usuario)
            for ruta in consultas:
                self.assertEqual(self.client.get(reverse(ruta)).status_code, 200)
            if usuario != self.ventas:
                self.assertEqual(self.client.post(reverse("venta_nueva"), self.datos_venta()).status_code, 403)
        self.client.force_login(self.sin_rol)
        for ruta in consultas:
            self.assertEqual(self.client.get(reverse(ruta)).status_code, 403)

    def test_admin_asigna_sucursal_y_ventas_la_requiere(self):
        datos = {"username": "nueva", "rol": "Ventas", "password": TEST_PASSWORD}
        form = AdminUserForm(datos)
        self.assertFalse(form.is_valid())
        self.assertIn("sucursal", form.errors)
        datos["sucursal"] = self.cordoba.pk
        form = AdminUserForm(datos)
        self.assertTrue(form.is_valid(), form.errors)
        usuario = form.save()
        self.assertEqual(usuario.asignacion_sucursal.sucursal, self.cordoba)

    def test_resumen_limites_quincenales_y_sucursal(self):
        fechas = [date(2024, 2, 1), date(2024, 2, 15), date(2024, 2, 16), date(2024, 2, 29), date(2024, 3, 1)]
        for fecha in fechas:
            venta = self.vender(cantidad=1)
            Venta.objects.filter(pk=venta.pk).update(fecha=fecha)
        venta = self.vender(usuario=self.otras_ventas)
        Venta.objects.filter(pk=venta.pk).update(fecha=date(2024, 2, 15))
        for fecha in [date(2024, 2, 15), date(2024, 2, 29)]:
            filas = list(servicios.resumen_ventas(self.ventas, fecha))
            self.assertEqual(len(filas), 1)
            self.assertEqual(filas[0]["total"], 2)
        self.assertEqual(len(list(servicios.resumen_ventas(self.finanzas, date(2024, 2, 15)))), 2)
        self.assertEqual(len(list(servicios.resumen_ventas(self.finanzas, date(2024, 2, 15), self.mendoza))), 1)

    def test_detalle_cantidad_positiva_en_base(self):
        venta = self.vender()
        with self.assertRaises(IntegrityError), transaction.atomic():
            venta.detalles.update(cantidad=0)


    def test_ajuste_por_pantalla_y_catalogos_protegidos(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post(reverse("stock_ajuste"), {
            "sucursal": self.cordoba.pk, "modelo": self.modelo.pk,
            "variacion": 7, "motivo": "Carga inicial"})
        self.assertRedirects(respuesta, reverse("stock_lista"))
        self.assertEqual(Stock.objects.get(sucursal=self.cordoba).cantidad, 7)
        for tipo, registro in [("modelos", self.modelo), ("sucursales", self.rosario)]:
            respuesta = self.client.post(reverse("admin_catalogo_eliminar", args=[tipo, registro.pk]))
            self.assertEqual(respuesta.status_code, 302)
            self.assertTrue(type(registro).objects.filter(pk=registro.pk).exists())

    def test_formulario_muestra_errores_y_conserva_token(self):
        self.client.force_login(self.ventas)
        self.assertEqual(self.client.get(reverse("venta_nueva")).status_code, 200)
        datos = self.datos_venta()
        datos["filas-0-cantidad"] = 99
        respuesta = self.client.post(reverse("venta_nueva"), datos)
        self.assertContains(respuesta, "Stock insuficiente")
        self.assertEqual(str(respuesta.context["form"]["clave_operacion"].value()), datos["clave_operacion"])
        self.assertFalse(Venta.objects.exists())

    def test_bloqueo_sqlite_informa_reintento_sin_cambiar_token(self):
        from django.db import OperationalError
        self.client.force_login(self.ventas)
        datos = self.datos_venta()
        with patch("compras.views.servicios.registrar_venta", side_effect=OperationalError("database is locked")):
            respuesta = self.client.post(reverse("venta_nueva"), datos)
        self.assertContains(respuesta, "Reintente el mismo formulario")
        self.assertEqual(str(respuesta.context["form"]["clave_operacion"].value()), datos["clave_operacion"])
        self.assertEqual(self.cantidad(), 10)

    def test_admin_nativo_no_permite_editar_stock_ni_ventas(self):
        from django.contrib import admin
        from django.test import RequestFactory
        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser("super", password=TEST_PASSWORD)
        for modelo in [Stock, Venta, DetalleVenta, AjusteStock]:
            configuracion = admin.site._registry[modelo]
            self.assertFalse(configuracion.has_add_permission(request))
            self.assertFalse(configuracion.has_change_permission(request))
            self.assertFalse(configuracion.has_delete_permission(request))


class SQLiteConcurrenciaTest(SimpleTestCase):
    def test_escritores_concurrentes_en_archivo_sqlite(self):
        # Proceso y archivo aislados: no modifica db.sqlite3 ni depende de los
        # bloqueos particulares de la base en memoria del runner de Django.
        import subprocess
        import sys
        import tempfile
        from pathlib import Path
        script = r"""
import os, sys, time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
from django.conf import settings
settings.DATABASES['default']['NAME'] = sys.argv[1]
import django
django.setup()
from django.core.management import call_command
from django.contrib.auth.models import User, Group
from django.db import connections, OperationalError
from django.core.exceptions import ValidationError
from compras.models import Marca, Modelo, Sucursal, UsuarioSucursal, Stock, Venta
from compras.servicios import registrar_venta
call_command('migrate', verbosity=0)
u = User.objects.create_user('v')
u.groups.add(Group.objects.create(name='Ventas'))
s = Sucursal.objects.create(nombre='Rosario')
UsuarioSucursal.objects.create(usuario=u, sucursal=s)
m = Modelo.objects.create(nombre='A', marca=Marca.objects.create(nombre='K'))
stock = Stock.objects.create(sucursal=s, modelo=m, cantidad=5)
def ejecutar(claves, cantidad):
    barrera = Barrier(2)
    def escritor(clave):
        usuario = User.objects.get(pk=u.pk)
        modelo = Modelo.objects.get(pk=m.pk)
        barrera.wait(timeout=10)
        try:
            for intento in range(100):
                try:
                    return ('ok', registrar_venta(usuario, [{'modelo': modelo, 'cantidad': cantidad}], clave).pk)
                except OperationalError as error:
                    if 'locked' not in str(error).lower():
                        raise
                    # Mismo token, transaccion nueva; simula reenvio del formulario.
                    time.sleep(0.02)
                except ValidationError:
                    return ('insuficiente', None)
            raise AssertionError('SQLite permanecio bloqueado')
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as executor:
        return list(executor.map(escritor, claves))
clave = uuid4()
resultados = ejecutar([clave, clave], 2)
assert resultados[0] == resultados[1] and resultados[0][0] == 'ok', resultados
stock.refresh_from_db()
assert stock.cantidad == 3 and Venta.objects.count() == 1
resultados = ejecutar([uuid4(), uuid4()], 2)
assert sorted(r[0] for r in resultados) == ['insuficiente', 'ok'], resultados
stock.refresh_from_db()
assert stock.cantidad == 1 and Venta.objects.count() == 2
assert sum(Venta.objects.values_list('detalles__cantidad', flat=True)) == 4
print('SQLite archivo: duplicados y competencia por stock verificados')
"""
        with tempfile.TemporaryDirectory() as carpeta:
            resultado = subprocess.run([sys.executable, '-c', script, str(Path(carpeta) / 'prueba.sqlite3')],
                                       capture_output=True, text=True, timeout=60)
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
