from .test_credentials import TEST_PASSWORD
from html.parser import HTMLParser
from io import StringIO
from urllib.parse import urlsplit
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.template.loader import render_to_string
from .models import Compra, Cotizacion, SolicitudCotizacion, ListadoFaltantes, Venta, Marca


class NavegacionParser(HTMLParser):
    def __init__(self, texto):
        super().__init__()
        self.groups = {}
        self.links = []
        self.labels = []
        self.inputs = []
        self.feed(texto)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "details" and "data-nav-group" in attrs:
            self.groups[attrs["id"]] = attrs
        if tag == "a" and "data-nav-link" in attrs:
            self.links.append(attrs)
        if tag == "label":
            self.labels.append(attrs)
        if tag == "input":
            self.inputs.append(attrs)


@override_settings(KAWA_DEMO=True, KAWA_LOCAL_DEMO_PASSWORD=TEST_PASSWORD, PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FrontendTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_demo", stdout=StringIO())

    def ingresar(self, nombre):
        self.client.force_login(User.objects.get(username=nombre))

    def test_sidebar_por_rol_y_enlaces_autorizados(self):
        casos = {
            "demo_ventas_rosario": {"inicio", "ventas", "inventario", "pedidos"},
            "demo_compras": {"inicio", "ventas", "inventario", "pedidos", "proveedores", "compras"},
            "demo_finanzas": {"inicio", "ventas", "inventario", "compras", "finanzas"},
            "demo_admin": {"inicio", "ventas", "inventario", "pedidos", "proveedores", "compras", "administracion"},
        }
        for usuario, grupos in casos.items():
            self.ingresar(usuario)
            respuesta = self.client.get(reverse("panel"))
            nav = NavegacionParser(respuesta.content.decode())
            self.assertEqual(set(nav.groups), {"nav-" + g for g in grupos})
            for enlace in nav.links:
                ruta = urlsplit(enlace["href"]).path
                self.assertEqual(self.client.get(ruta).status_code, 200, (usuario, ruta))

    def test_pagina_activa_abre_su_grupo_y_tiene_un_enlace_actual(self):
        self.ingresar("demo_compras")
        casos = [(reverse("venta_detalle", args=[Venta.objects.first().pk]), "ventas"),
                 (reverse("faltantes_detalle", args=[ListadoFaltantes.objects.first().pk]), "pedidos"),
                 (reverse("cotizacion_detalle", args=[Cotizacion.objects.first().pk]), "proveedores"),
                 (reverse("compra_detalle", args=[Compra.objects.first().pk]), "compras")]
        for ruta, grupo in casos:
            nav = NavegacionParser(self.client.get(ruta).content.decode())
            self.assertIn("open", nav.groups["nav-" + grupo])
            self.assertEqual(len([a for a in nav.links if a.get("aria-current") == "page"]), 1, ruta)

    def test_cotizaciones_recibidas_reutilizan_la_lista_sin_nueva_ruta(self):
        self.ingresar("demo_compras")
        respuesta = self.client.get(reverse("cotizacion_lista"))
        self.assertContains(respuesta, 'id="cotizaciones-recibidas"')
        self.assertContains(respuesta, reverse("cotizacion_lista") + "#cotizaciones-recibidas")
        self.assertContains(respuesta, reverse("cotizacion_detalle", args=[Cotizacion.objects.first().pk]))
        nav = NavegacionParser(respuesta.content.decode())
        self.assertEqual(len([a for a in nav.links if a.get("aria-current") == "page"]), 1)

    def test_shell_tema_accesibilidad_y_archivos_compartidos(self):
        self.ingresar("demo_admin")
        respuesta = self.client.get(reverse("panel"))
        html = respuesta.content.decode()
        self.assertLess(html.index("theme-init.js"), html.index("app.css"))
        for contenido in ['app.js', 'Saltar al contenido', 'aria-controls="app-sidebar"',
                          'data-theme-toggle', 'data-menu-close', 'aria-label="Módulos del sistema"']:
            self.assertIn(contenido, html)
        self.assertNotIn("cdn.", html)
        self.assertContains(respuesta, 'name="csrfmiddlewaretoken"')

    def test_login_y_documento_incluyen_tema_y_conservan_datos(self):
        login = self.client.get(reverse("login"))
        for texto in ['name="username"', 'name="password"', 'name="next"', 'csrfmiddlewaretoken', 'theme-init.js', 'data-theme-toggle']:
            self.assertContains(login, texto)
        self.ingresar("demo_finanzas")
        compra = Compra.objects.filter(documento__isnull=False).first()
        documento = self.client.get(reverse("documento_compra", args=[compra.pk]))
        for texto in [compra.documento.numero, compra.documento.contenido["proveedor"], 'window.print()', 'app.css', 'theme-init.js']:
            self.assertContains(documento, texto)
        self.assertNotContains(documento, '<style>')

    def test_formulario_compartido_conserva_etiquetas_errores_y_campos(self):
        self.ingresar("demo_admin")
        ruta = reverse("admin_catalogo_nuevo", args=["marcas"])
        respuesta = self.client.post(ruta, {"nombre": ""})
        self.assertEqual(respuesta.status_code, 200)
        nav = NavegacionParser(respuesta.content.decode())
        self.assertTrue(any(label.get("for") == "id_nombre" for label in nav.labels))
        self.assertTrue(any(control.get("name") == "nombre" for control in nav.inputs))
        self.assertContains(respuesta, 'required-mark')
        self.assertContains(respuesta, 'errorlist')
        self.assertContains(respuesta, 'csrfmiddlewaretoken')

    def test_renderizado_de_todas_las_pantallas_administrativas_y_operativas(self):
        self.ingresar("demo_admin")
        pedido, venta, solicitud, cotizacion, compra = (modelo.objects.first() for modelo in [ListadoFaltantes, Venta, SolicitudCotizacion, Cotizacion, Compra])
        rutas = ["stock_lista", "stock_ajuste", "venta_lista", "venta_resumen", "faltantes_lista", "faltantes_nuevo", "faltantes_consolidado", "proveedor_lista", "proveedor_nuevo", "cotizacion_lista", "cotizacion_nueva", "cotizacion_comparar", "compra_lista", "compra_nueva", "admin_dashboard", "admin_usuario_lista", "admin_usuario_nuevo", "admin_operaciones"]
        urls = [reverse(ruta) for ruta in rutas] + [reverse("venta_detalle", args=[venta.pk]), reverse("faltantes_detalle", args=[pedido.pk]),
            reverse("solicitud_detalle", args=[solicitud.pk]), reverse("cotizacion_detalle", args=[cotizacion.pk]), reverse("compra_detalle", args=[compra.pk]),
            reverse("admin_usuario_editar", args=[User.objects.get(username="demo_compras").pk]), reverse("admin_usuario_password", args=[User.objects.get(username="demo_compras").pk])]
        for tipo in ["marcas", "modelos", "sucursales"]:
            urls += [reverse("admin_catalogo_lista", args=[tipo]), reverse("admin_catalogo_nuevo", args=[tipo])]
        for url in urls:
            respuesta = self.client.get(url)
            self.assertEqual(respuesta.status_code, 200, url)
            self.assertContains(respuesta, "app.css")
            self.assertContains(respuesta, 'id="main-content"')
        self.ingresar("demo_finanzas")
        for ruta in ["finanzas_bandeja", "finanzas_historial"]:
            self.assertEqual(self.client.get(reverse(ruta)).status_code, 200)

    def test_finanzas_y_admin_conservan_sus_restricciones(self):
        self.ingresar("demo_admin")
        self.assertEqual(self.client.get(reverse("finanzas_bandeja")).status_code, 403)
        self.assertNotContains(self.client.get(reverse("panel")), "Aprobaciones pendientes")
        self.ingresar("demo_finanzas")
        nav = NavegacionParser(self.client.get(reverse("panel")).content.decode())
        self.assertFalse(any(a["href"] == reverse("compra_nueva") for a in nav.links))
        self.assertFalse(any(a["href"] == reverse("stock_ajuste") for a in nav.links))

    def test_componentes_de_panel_no_agregan_estadisticas(self):
        self.ingresar("demo_ventas_rosario")
        respuesta = self.client.get(reverse("panel"))
        self.assertContains(respuesta, "Registrar venta")
        self.assertContains(respuesta, "Consultar stock")
        self.assertNotContains(respuesta, 'class="stat-card"')
