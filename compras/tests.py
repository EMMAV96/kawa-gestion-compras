from .test_credentials import TEST_PASSWORD
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import ItemFaltante, ListadoFaltantes, Marca, Modelo, Proveedor, SolicitudCotizacion, Sucursal
from . import servicios


@override_settings(KAWA_LOCAL_DEMO_PASSWORD=TEST_PASSWORD)
class BaseTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_datos", verbosity=0)

    def ingresar(self, usuario):
        self.client.login(username=usuario, password=TEST_PASSWORD)


class LoginTest(BaseTest):
    def test_ingreso_exitoso(self):
        respuesta = self.client.post(reverse("login"), {"username": "compras01", "password": TEST_PASSWORD})
        self.assertRedirects(respuesta, reverse("panel"))

    def test_contrasena_incorrecta(self):
        respuesta = self.client.post(reverse("login"), {"username": "compras01", "password": "incorrecta"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Usuario o contraseña incorrectos")

    def test_sin_sesion_redirige_al_login(self):
        respuesta = self.client.get(reverse("panel"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("login"), respuesta.url)

    def test_ventas_no_accede_a_proveedores(self):
        self.ingresar("ventas01")
        self.assertEqual(self.client.get(reverse("proveedor_lista")).status_code, 403)


class ProveedorTest(BaseTest):
    def test_registra_un_proveedor(self):
        self.ingresar("compras01")
        marca = Marca.objects.first()
        respuesta = self.client.post(reverse("proveedor_nuevo"), {
            "razon_social": "Proveedor de prueba", "email": "prueba@ejemplo.com", "marcas": [marca.pk]})
        self.assertRedirects(respuesta, reverse("proveedor_lista"))
        self.assertTrue(Proveedor.objects.filter(razon_social="Proveedor de prueba").exists())

    def test_proveedor_sin_marcas_es_rechazado(self):
        self.ingresar("compras01")
        respuesta = self.client.post(reverse("proveedor_nuevo"), {
            "razon_social": "Sin marcas", "email": "a@b.com"})
        self.assertContains(respuesta, "Seleccione al menos una marca")
        self.assertFalse(Proveedor.objects.exists())


class FaltantesTest(BaseTest):
    def datos(self, filas=()):
        datos = {"sucursal": Sucursal.objects.first().pk,
                 "filas-TOTAL_FORMS": 8, "filas-INITIAL_FORMS": 0,
                 "filas-MIN_NUM_FORMS": 0, "filas-MAX_NUM_FORMS": 1000}
        for i, (modelo, cantidad, motivo) in enumerate(filas):
            datos[f"filas-{i}-modelo"] = modelo.pk
            datos[f"filas-{i}-cantidad"] = cantidad
            datos[f"filas-{i}-motivo"] = motivo
        return datos

    def test_envio_exitoso_del_listado(self):
        self.ingresar("ventas01")
        modelo = Modelo.objects.first()
        respuesta = self.client.post(
            reverse("faltantes_nuevo"), self.datos([(modelo, 3, "PEDIDO_CLIENTE")]))
        self.assertRedirects(respuesta, reverse("faltantes_lista"))
        listado = ListadoFaltantes.objects.get()
        self.assertEqual(listado.estado, "CARGADO")
        self.assertEqual(listado.items.count(), 1)

    def test_listado_sin_modelos_no_se_envia(self):
        self.ingresar("ventas01")
        respuesta = self.client.post(reverse("faltantes_nuevo"), self.datos())
        self.assertContains(respuesta, "Debe cargar al menos un modelo")
        self.assertFalse(ListadoFaltantes.objects.exists())


class CotizacionTest(BaseTest):
    def setUp(self):
        ventas = User.objects.get(username="ventas01")
        modelo = Modelo.objects.first()
        servicios.crear_listado(Sucursal.objects.first(), ventas, [
            {"modelo": modelo, "cantidad": 2, "motivo": "VENTA"}])
        servicios.crear_listado(Sucursal.objects.last(), ventas, [
            {"modelo": modelo, "cantidad": 3, "motivo": "VENTA"}])
        self.modelo = modelo
        self.proveedor = Proveedor.objects.create(razon_social="Proveedor 1", email="p@e.com")
        self.proveedor.marcas.add(modelo.marca)

    def test_consolida_por_modelo(self):
        lineas = servicios.consolidar()
        self.assertEqual(len(lineas), 1)
        self.assertEqual(lineas[0]["total"], 5)

    def test_genera_la_solicitud_y_marca_los_faltantes(self):
        self.ingresar("compras01")
        respuesta = self.client.post(reverse("cotizacion_nueva"), {
            "modelos": [self.modelo.pk], "proveedores": [self.proveedor.pk], "medio": "MAIL"})
        self.assertRedirects(respuesta, reverse("cotizacion_lista"))
        self.assertEqual(SolicitudCotizacion.objects.count(), 1)
        self.assertFalse(ItemFaltante.objects.filter(solicitado=False).exists())

    def test_sin_modelos_ni_proveedores_muestra_errores(self):
        self.ingresar("compras01")
        respuesta = self.client.post(reverse("cotizacion_nueva"), {"medio": "MAIL"})
        self.assertContains(respuesta, "Seleccione al menos un modelo")
        self.assertContains(respuesta, "Seleccione al menos un proveedor")


class AdministracionTest(BaseTest):
    def test_acceso_admin_permitido_y_ventas_denegado(self):
        self.ingresar("admin01")
        rutas = (
            reverse("admin_dashboard"),
            reverse("admin_usuario_lista"),
            reverse("admin_operaciones"),
            reverse("admin_catalogo_lista", args=["marcas"]),
            reverse("proveedor_lista"),
            reverse("faltantes_lista"),
            reverse("cotizacion_lista"),
            reverse("cotizacion_nueva"),
        )
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(ruta).status_code, 200)

        ventas = self.client_class()
        ventas.login(username="ventas01", password=TEST_PASSWORD)
        self.assertEqual(ventas.get(reverse("admin_dashboard")).status_code, 403)
        self.assertEqual(ventas.get(reverse("admin_usuario_lista")).status_code, 403)
        self.assertEqual(
            ventas.get(reverse("admin_catalogo_lista", args=["marcas"])).status_code, 403)

    def test_crea_usuario_con_un_solo_rol(self):
        self.ingresar("admin01")
        respuesta = self.client.post(reverse("admin_usuario_nuevo"), {
            "username": "usuario_nuevo",
            "first_name": "Nueva",
            "last_name": "Persona",
            "email": "nueva@ejemplo.com",
            "rol": "Compras",
            "password": TEST_PASSWORD,
            "is_active": "on",
        })
        self.assertRedirects(respuesta, reverse("admin_usuario_lista"))
        usuario = User.objects.get(username="usuario_nuevo")
        self.assertEqual(list(usuario.groups.values_list("name", flat=True)), ["Compras"])
        self.assertTrue(usuario.check_password(TEST_PASSWORD))

    def test_crea_marca_modelo_y_sucursal(self):
        self.ingresar("admin01")
        respuesta = self.client.post(reverse("admin_catalogo_nuevo", args=["marcas"]), {
            "nombre": "Marca nueva",
        })
        self.assertRedirects(respuesta, reverse("admin_catalogo_lista", args=["marcas"]))
        marca = Marca.objects.get(nombre="Marca nueva")

        respuesta = self.client.post(reverse("admin_catalogo_nuevo", args=["modelos"]), {
            "nombre": "Modelo nuevo",
            "marca": marca.pk,
        })
        self.assertRedirects(respuesta, reverse("admin_catalogo_lista", args=["modelos"]))
        self.assertTrue(Modelo.objects.filter(nombre="Modelo nuevo", marca=marca).exists())

        respuesta = self.client.post(reverse("admin_catalogo_nuevo", args=["sucursales"]), {
            "nombre": "Sucursal nueva",
        })
        self.assertRedirects(respuesta, reverse("admin_catalogo_lista", args=["sucursales"]))
        self.assertTrue(Sucursal.objects.filter(nombre="Sucursal nueva").exists())

    def test_no_borra_marca_en_uso(self):
        self.ingresar("admin01")
        marca = Marca.objects.first()
        respuesta = self.client.post(
            reverse("admin_catalogo_eliminar", args=["marcas", marca.pk]))
        self.assertRedirects(respuesta, reverse("admin_catalogo_lista", args=["marcas"]))
        self.assertTrue(Marca.objects.filter(pk=marca.pk).exists())

    def test_no_borra_modelo_ni_sucursal_en_uso(self):
        self.ingresar("admin01")
        modelo = Modelo.objects.first()
        sucursal = Sucursal.objects.first()
        ventas = User.objects.get(username="ventas01")
        servicios.crear_listado(sucursal, ventas, [
            {"modelo": modelo, "cantidad": 1, "motivo": "VENTA"},
        ])

        for tipo, registro in (("modelos", modelo), ("sucursales", sucursal)):
            respuesta = self.client.post(
                reverse("admin_catalogo_eliminar", args=[tipo, registro.pk]))
            self.assertEqual(respuesta.status_code, 302)
            self.assertTrue(type(registro).objects.filter(pk=registro.pk).exists())
