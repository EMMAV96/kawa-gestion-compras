from .test_credentials import TEST_PASSWORD
from datetime import date
from io import StringIO
from unittest.mock import patch
from django.conf import settings
from django.contrib.auth.models import User, Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from .models import (Marca, Modelo, Sucursal, UsuarioSucursal, Stock, Venta, ListadoFaltantes,
    ItemFaltante, Proveedor, SolicitudCotizacion, Cotizacion, Compra, OrigenCompra,
    DocumentoCompra, DecisionFinanciera, MovimientoCompra, AjusteStock)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class IntegracionMVPTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rosario = Sucursal.objects.create(nombre="Rosario")
        cls.mendoza = Sucursal.objects.create(nombre="Mendoza")
        cls.marca = Marca.objects.create(nombre="Marca ficticia")
        cls.modelo = Modelo.objects.create(nombre="Moto ficticia", marca=cls.marca)
        for nombre, rol in [("admin", "Administrador"), ("ventas", "Ventas"), ("ventas_mendoza", "Ventas"),
                            ("compras", "Compras"), ("finanzas", "Finanzas")]:
            usuario = User.objects.create_user(nombre, password=TEST_PASSWORD)
            usuario.groups.add(Group.objects.get_or_create(name=rol)[0])
            setattr(cls, nombre, usuario)
        UsuarioSucursal.objects.create(usuario=cls.ventas, sucursal=cls.rosario)
        UsuarioSucursal.objects.create(usuario=cls.ventas_mendoza, sucursal=cls.mendoza)

    def ingresar(self, usuario):
        cliente = Client(enforce_csrf_checks=True)
        cliente.get(reverse("login"))
        respuesta = self.post(cliente, reverse("login"), {"username": usuario.username, "password": TEST_PASSWORD})
        self.assertEqual(respuesta.status_code, 302)
        return cliente

    def post(self, cliente, ruta, datos=None):
        token = cliente.cookies[settings.CSRF_COOKIE_NAME].value
        return cliente.post(ruta, datos or {}, HTTP_X_CSRFTOKEN=token)

    def crear_pedido(self, vendedor, cantidad=3):
        cliente = self.ingresar(vendedor)
        cliente.get(reverse("faltantes_nuevo"))
        datos = {"filas-TOTAL_FORMS": 1, "filas-INITIAL_FORMS": 0,
                 "filas-0-modelo": self.modelo.pk, "filas-0-cantidad": cantidad, "filas-0-motivo": "VENTA"}
        self.assertEqual(self.post(cliente, reverse("faltantes_nuevo"), datos).status_code, 302)
        return ListadoFaltantes.objects.order_by("pk").last()

    def proveedor(self, cliente, nombre, habitual=False):
        datos = {"razon_social": nombre, "email": "ejemplo@proveedor.invalid", "marcas": [self.marca.pk]}
        if habitual:
            datos["es_fijo"] = "on"
        self.assertEqual(self.post(cliente, reverse("proveedor_nuevo"), datos).status_code, 302)
        return Proveedor.objects.get(razon_social=nombre)

    def nueva_compra(self, cliente, datos):
        respuesta = cliente.get(reverse("compra_nueva"))
        datos["clave_operacion"] = respuesta.context["form"]["clave_operacion"].value()
        self.assertEqual(self.post(cliente, reverse("compra_nueva"), datos).status_code, 302)
        return Compra.objects.latest("pk")

    def documentar_y_enviar(self, cliente, compra):
        for accion in ["documentar", "solicitar"]:
            self.assertEqual(self.post(cliente, reverse("compra_accion", args=[compra.pk, accion])).status_code, 302)
        self.assertEqual(cliente.get(reverse("documento_compra", args=[compra.pk])).status_code, 200)
        compra.refresh_from_db()
        self.assertEqual(compra.estado, "PENDIENTE_APROBACION")

    def decidir(self, compra, resultado, motivo=""):
        cliente = self.ingresar(self.finanzas)
        self.assertContains(cliente.get(reverse("finanzas_bandeja")), compra.proveedor_nombre)
        self.assertEqual(cliente.get(reverse("documento_compra", args=[compra.pk])).status_code, 200)
        self.assertEqual(self.post(cliente, reverse("compra_decidir", args=[compra.pk]), {"resultado": resultado, "motivo": motivo}).status_code, 302)
        self.assertContains(cliente.get(reverse("finanzas_historial")), compra.decision.get_resultado_display())

    def test_escenario_a_stock_venta_resumen_y_reenvio(self):
        admin = self.ingresar(self.admin)
        self.assertEqual(self.post(admin, reverse("stock_ajuste"), {"sucursal": self.rosario.pk,
            "modelo": self.modelo.pk, "variacion": 10, "motivo": "Inicial ficticio"}).status_code, 302)
        vendedor = self.ingresar(self.ventas)
        self.assertContains(vendedor.get(reverse("stock_lista")), "Moto ficticia")
        respuesta = vendedor.get(reverse("venta_nueva"))
        datos = {"clave_operacion": respuesta.context["form"]["clave_operacion"].value(),
            "filas-TOTAL_FORMS": 1, "filas-INITIAL_FORMS": 0, "filas-0-modelo": self.modelo.pk, "filas-0-cantidad": 2}
        for _ in range(2):
            self.assertEqual(self.post(vendedor, reverse("venta_nueva"), datos).status_code, 302)
        self.assertEqual(Stock.objects.get().cantidad, 8)
        self.assertEqual(Venta.objects.count(), 1)
        resumen = vendedor.get(reverse("venta_resumen"), {"fecha": timezone.localdate().isoformat()})
        self.assertEqual(list(resumen.context["lineas"])[0]["total"], 2)
        datos["clave_operacion"] = vendedor.get(reverse("venta_nueva")).context["form"]["clave_operacion"].value()
        datos["filas-0-cantidad"] = 99
        self.assertContains(self.post(vendedor, reverse("venta_nueva"), datos), "Stock insuficiente")
        self.assertEqual(Stock.objects.get().cantidad, 8)

    def test_escenario_b_habitual_documento_aprobacion_e_historial(self):
        pedido = self.crear_pedido(self.ventas)
        comprador = self.ingresar(self.compras)
        self.assertContains(comprador.get(reverse("faltantes_detalle", args=[pedido.pk])), "Rosario")
        proveedor = self.proveedor(comprador, "Habitual ficticio", habitual=True)
        compra = self.nueva_compra(comprador, {"procedimiento": "HABITUAL", "proveedor": proveedor.pk,
            "items": [pedido.items.get().pk], "precios-TOTAL_FORMS": 1, "precios-INITIAL_FORMS": 0,
            "precios-0-modelo": self.modelo.pk, "precios-0-precio": "150.25"})
        self.documentar_y_enviar(comprador, compra)
        self.assertEqual(compra.documento.tipo, "NOTA_PEDIDO")
        stock_antes = list(Stock.objects.values())
        self.decidir(compra, "APROBADA")
        compra.refresh_from_db()
        self.assertEqual(compra.estado, "APROBADA")
        self.assertEqual(list(Stock.objects.values()), stock_antes)
        self.assertEqual(compra.movimientos.count(), 4)
        self.assertEqual(compra.origenes.get().pedido_id, pedido.pk)

    def test_escenario_c_cotizaciones_comparacion_orden_y_rechazo(self):
        pedido = self.crear_pedido(self.ventas_mendoza)
        comprador = self.ingresar(self.compras)
        self.assertContains(comprador.get(reverse("faltantes_lista")), "Mendoza")
        a, b = self.proveedor(comprador, "Norte ficticio"), self.proveedor(comprador, "Sur ficticio")
        formulario = comprador.get(reverse("cotizacion_nueva"))
        datos = {"modelos": [self.modelo.pk], "proveedores": [a.pk, b.pk], "medio": "MAIL",
                 "clave_operacion": formulario.context["form"]["clave_operacion"].value()}
        for _ in range(2):
            self.assertEqual(self.post(comprador, reverse("cotizacion_nueva"), datos).status_code, 302)
        self.assertEqual(SolicitudCotizacion.objects.count(), 2)
        for proveedor, cantidad, precio in [(a, 3, "100.10"), (b, 2, "90.00")]:
            solicitud = SolicitudCotizacion.objects.get(proveedor=proveedor)
            self.assertEqual(self.post(comprador, reverse("cotizacion_recibida", args=[solicitud.pk]), {
                "fecha": timezone.localdate().isoformat(), "filas-TOTAL_FORMS": 1, "filas-INITIAL_FORMS": 1,
                "filas-0-detalle_solicitud": solicitud.detalles.get().pk,
                "filas-0-cantidad": cantidad, "filas-0-precio_unitario": precio}).status_code, 302)
        self.assertContains(comprador.get(reverse("cotizacion_comparar")), "subtotal no comparable")
        solicitud = SolicitudCotizacion.objects.get(proveedor=a)
        compra = self.nueva_compra(comprador, {"procedimiento": "COTIZACION", "solicitud": solicitud.pk,
            "precios-TOTAL_FORMS": 0, "precios-INITIAL_FORMS": 0})
        self.post(comprador, reverse("compra_accion", args=[compra.pk, "evaluar"]))
        self.post(comprador, reverse("compra_accion", args=[compra.pk, "seleccionar"]), {"oferta": solicitud.cotizacion.pk})
        self.documentar_y_enviar(comprador, compra)
        self.assertEqual(compra.documento.tipo, "ORDEN_COMPRA")
        self.assertEqual(compra.documento.contenido["cotizacion"], solicitud.cotizacion.pk)
        stock_antes = list(Stock.objects.values())
        self.decidir(compra, "RECHAZADA", "Ejemplo ficticio: presupuesto")
        compra.refresh_from_db()
        self.assertEqual(compra.estado, "RECHAZADA")
        self.assertFalse(compra.origenes.get().vigente)
        self.assertEqual(compra.origenes.get().item_id, pedido.items.get().pk)
        self.assertEqual(list(Stock.objects.values()), stock_antes)

    def test_urls_ajenas_y_csrf_en_recorrido_real(self):
        ajeno = self.crear_pedido(self.ventas_mendoza)
        vendedor = self.ingresar(self.ventas)
        self.assertEqual(vendedor.get(reverse("faltantes_detalle", args=[ajeno.pk])).status_code, 404)
        self.assertEqual(vendedor.get(reverse("compra_nueva")).status_code, 403)
        self.assertEqual(vendedor.post(reverse("venta_nueva"), {}).status_code, 403)
        for usuario in [self.admin, self.compras]:
            cliente = self.ingresar(usuario)
            self.assertEqual(cliente.get(reverse("finanzas_bandeja")).status_code, 403)
            self.assertEqual(self.post(cliente, reverse("compra_decidir", args=[999]), {"resultado": "APROBADA"}).status_code, 403)
        self.assertFalse(DecisionFinanciera.objects.exists())


    def test_roles_multiples_se_muestran_de_forma_estable(self):
        self.compras.groups.add(Group.objects.get(name="Finanzas"))
        cliente = self.ingresar(self.compras)
        respuesta = cliente.get(reverse("panel"))
        self.assertEqual(respuesta.context["rol_usuario"], "Compras, Finanzas")


@override_settings(KAWA_DEMO=True, KAWA_LOCAL_DEMO_PASSWORD=TEST_PASSWORD, PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DatosDemostracionTest(TestCase):
    def cargar(self):
        call_command("cargar_demo", stdout=StringIO())

    def test_demo_completa_idempotente_y_preserva_cambios_posteriores(self):
        self.cargar()
        self.assertEqual(Sucursal.objects.count(), 3)
        self.assertEqual(User.objects.count(), 6)
        self.assertEqual(Stock.objects.count(), 9)
        self.assertEqual(Venta.objects.count(), 2)
        self.assertEqual(Compra.objects.count(), 8)
        self.assertEqual(set(Compra.objects.values_list("estado", flat=True)), set(Compra.Estado.values))
        self.assertTrue(Cotizacion.objects.exists())
        self.assertTrue(any(not c.completa for c in Cotizacion.objects.all()))
        self.assertEqual(DecisionFinanciera.objects.filter(resultado="APROBADA").count(), 2)
        self.assertEqual(DecisionFinanciera.objects.filter(resultado="RECHAZADA").count(), 1)
        self.assertEqual(Stock.objects.get(sucursal__nombre="Rosario", modelo__nombre="Aurora Urbana 125").cantidad, 10)
        usuario = User.objects.get(username="demo_admin")
        usuario.set_password((TEST_PASSWORD + "-cambio"))
        usuario.save()
        usuario.groups.set([Group.objects.get(name="Ventas")])
        antes = {modelo: list(modelo.objects.order_by("pk").values()) for modelo in
            [User, Group, Compra, Stock, Venta, ListadoFaltantes, SolicitudCotizacion, Cotizacion, OrigenCompra, DocumentoCompra, DecisionFinanciera, MovimientoCompra]}
        self.cargar()
        for modelo, registros in antes.items():
            self.assertEqual(registros, list(modelo.objects.order_by("pk").values()))
        self.assertTrue(User.objects.get(pk=usuario.pk).check_password((TEST_PASSWORD + "-cambio")))

    def test_demo_rechaza_base_habitual(self):
        with override_settings(KAWA_DEMO=False), self.assertRaises(CommandError):
            self.cargar()
        self.assertFalse(User.objects.exists())

    def test_demo_rechaza_usuario_o_catalogo_preexistente_sin_tocarlo(self):
        usuario = User.objects.create_user("demo_admin", password=(TEST_PASSWORD + "-original"))
        with self.assertRaises(CommandError):
            self.cargar()
        self.assertTrue(User.objects.get(pk=usuario.pk).check_password((TEST_PASSWORD + "-original")))
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(Compra.objects.exists())

    def test_error_revierte_toda_la_carga(self):
        with patch("compras.management.commands.cargar_demo.compras.decidir_compra", side_effect=RuntimeError("fallo")):
            with self.assertRaises(RuntimeError):
                self.cargar()
        for modelo in [User, Group, Stock, AjusteStock, Compra, Venta, ListadoFaltantes]:
            self.assertFalse(modelo.objects.exists())

    def test_cargador_legacy_no_cambia_roles_claves_o_sucursal(self):
        usuario = User.objects.create_user("ventas01", password=(TEST_PASSWORD + "-existente"))
        grupo = Group.objects.create(name="Finanzas")
        usuario.groups.add(grupo)
        sucursal = Sucursal.objects.create(nombre="Mendoza")
        UsuarioSucursal.objects.create(usuario=usuario, sucursal=sucursal)
        call_command("cargar_datos", stdout=StringIO())
        usuario.refresh_from_db()
        self.assertTrue(usuario.check_password((TEST_PASSWORD + "-existente")))
        self.assertEqual(list(usuario.groups.all()), [grupo])
        self.assertEqual(usuario.asignacion_sucursal.sucursal, sucursal)


    def test_catalogo_preexistente_no_se_mezcla_con_la_demo(self):
        Marca.objects.create(nombre="Existente")
        with self.assertRaises(CommandError):
            self.cargar()
        self.assertEqual(list(Marca.objects.values_list("nombre", flat=True)), ["Existente"])
        self.assertFalse(User.objects.exists())

    def test_bandera_demo_no_permite_apuntar_a_db_habitual(self):
        from django.db import connection
        with patch.dict(connection.settings_dict, {"NAME": settings.BASE_DIR / "db.sqlite3"}):
            with self.assertRaises(CommandError):
                self.cargar()
        self.assertFalse(User.objects.exists())
