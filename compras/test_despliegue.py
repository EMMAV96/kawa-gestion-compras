import json
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from config.database import postgres_database


class ConfiguracionDespliegueTest(SimpleTestCase):
    def test_url_pg_decodifica_y_exige_tls_sin_filtrar_credenciales(self):
        valor = postgres_database("postgresql://u:p%40ss@localhost:5432/kawa?sslmode=require")
        self.assertEqual(valor["PASSWORD"], "p@ss")
        self.assertEqual(valor["OPTIONS"]["sslmode"], "require")
        neon = postgres_database("postgresql://u:p@host/neondb?sslmode=require&channel_binding=require")
        self.assertEqual(neon["OPTIONS"]["channel_binding"], "require")
        for url in ["", "sqlite:///db.sqlite3", "postgresql://u:secreto@host/db?sslmode=disable",
                    "postgresql://u:secreto@host/db?opcion=1", "postgresql://u:secreto@host/db?sslmode=require&sslmode=disable"]:
            with self.assertRaises(ImproperlyConfigured) as error:
                postgres_database(url)
            self.assertNotIn("secreto", str(error.exception))

    def proceso(self, codigo, extras=None):
        ambiente = {k: v for k, v in os.environ.items() if k not in {
            "DJANGO_SETTINGS_MODULE", "DJANGO_SECRET_KEY", "DJANGO_ALLOWED_HOSTS", "DJANGO_CSRF_ORIGINS", "RENDER_EXTERNAL_HOSTNAME", "DATABASE_URL"}}
        ambiente.update(extras or {})
        return subprocess.run([sys.executable, "-c", codigo], cwd=settings.BASE_DIR,
            env=ambiente, capture_output=True, text=True, timeout=60)

    def test_produccion_rechaza_entorno_sin_secretos(self):
        resultado = self.proceso("import os; os.environ['DJANGO_SETTINGS_MODULE']='config.production'; import django; django.setup()")
        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY", resultado.stderr)

    def test_produccion_segura_y_white_noise_sin_conectar_db(self):
        codigo = r"""
import os,secrets,tempfile,json
os.environ.update(DJANGO_SETTINGS_MODULE='config.production',DJANGO_SECRET_KEY=secrets.token_urlsafe(64),
    RENDER_EXTERNAL_HOSTNAME='kawa-example.onrender.com',DATABASE_URL='postgresql://test:test@localhost:5432/test?sslmode=require')
import django
django.setup()
from django.conf import settings
from django.core.management import call_command
from django.test import Client, override_settings
from django.contrib.staticfiles.storage import staticfiles_storage
assert settings.DEBUG is False and settings.DATABASES['default']['ENGINE']=='django.db.backends.postgresql'
assert settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE and settings.SECURE_SSL_REDIRECT
call_command('check', deploy=True, fail_level='ERROR', verbosity=0)
from django.core.checks import run_checks
assert {issue.id for issue in run_checks(include_deployment_checks=True)} <= {'security.W005','security.W021'}
with tempfile.TemporaryDirectory() as carpeta, override_settings(STATIC_ROOT=carpeta):
    call_command('collectstatic', interactive=False, verbosity=0)
    manifest=json.load(open(os.path.join(carpeta,'staticfiles.json')))
    for archivo in ['compras/app.css','compras/app.js','compras/theme-init.js']:
        hashed=manifest['paths'][archivo]
        assert os.path.isfile(os.path.join(carpeta,hashed))
        respuesta=Client().get('/static/'+hashed,secure=True,HTTP_HOST='kawa-example.onrender.com')
        assert respuesta.status_code==200, respuesta.status_code
        respuesta.close()
    assert Client().get('/login/',secure=True,HTTP_HOST='kawa-example.onrender.com').status_code==200
print('Produccion y manifiesto estatico OK, sin conexion a PostgreSQL')
"""
        resultado = self.proceso(codigo)
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)

    def test_produccion_rechaza_comodines_y_sqlite(self):
        codigo = "import os,secrets; os.environ.update(DJANGO_SETTINGS_MODULE='config.production', DJANGO_SECRET_KEY=secrets.token_urlsafe(64)); import django; django.setup()"
        for extras in [{"DJANGO_ALLOWED_HOSTS": "*"}, {"DJANGO_ALLOWED_HOSTS": "site.example", "DJANGO_CSRF_ORIGINS": "https://site.example", "DATABASE_URL": "sqlite:///x"}]:
            self.assertNotEqual(self.proceso(codigo, extras).returncode, 0)

    def test_scripts_no_cargan_cuentas_ni_generan_migraciones(self):
        for nombre in ["build.sh", "start.sh", "Dockerfile", "render.yaml"]:
            contenido = (settings.BASE_DIR / nombre).read_text(encoding="utf-8")
            for prohibido in ["makemigrations", "cargar_demo", "cargar_datos", "createsuperuser"]:
                self.assertNotIn(prohibido, contenido)
        for nombre in ["build.sh", "start.sh"]:
            self.assertNotIn(b"\r", (settings.BASE_DIR / nombre).read_bytes())


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DemoPublicaSeguridadTest(TestCase):
    def test_publica_exige_pg_y_confirmacion_antes_de_escribir(self):
        with override_settings(KAWA_PUBLIC_DEMO=True):
            with self.assertRaises(CommandError):
                call_command('cargar_demo', stdout=StringIO())
        from .models import Compra
        self.assertFalse(Compra.objects.exists())

    def test_publica_no_acepta_claves_locales_y_legacy_se_bloquea(self):
        from django.db import connection
        from .management.commands.cargar_demo import USUARIOS
        with override_settings(KAWA_PUBLIC_DEMO=True), patch.object(type(connection._connections['default']), 'vendor', 'postgresql'):
            import hashlib, secrets
            from .test_credentials import TEST_PASSWORD
            claves = {u: secrets.token_urlsafe(24) for u in USUARIOS}
            claves[next(iter(USUARIOS))] = TEST_PASSWORD
            retiradas = {hashlib.sha256(TEST_PASSWORD.encode()).hexdigest()}
            with patch.dict(os.environ, {"KAWA_DEMO_PASSWORDS": json.dumps(claves)}), patch("compras.management.commands.cargar_demo.CLAVES_RETIRADAS_SHA256", retiradas):
                with self.assertRaises(CommandError):
                    call_command('cargar_demo', confirmar_demo_publica=True, stdout=StringIO())
            with self.assertRaises(CommandError):
                call_command('cargar_datos', stdout=StringIO())


from unittest import skipUnless
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
from django.db import connection, connections
from django.test import TransactionTestCase


@skipUnless(connection.vendor == "postgresql", "Requiere PostgreSQL real; no valida concurrencia PG sobre SQLite")
class ConcurrenciaPostgresTest(TransactionTestCase):
    def test_mismo_uuid_crea_una_compra_y_reserva(self):
        from django.contrib.auth.models import User, Group
        from .models import Marca, Modelo, Sucursal, UsuarioSucursal, Proveedor, Compra, OrigenCompra
        from .servicios_pedidos import registrar_pedido
        from .servicios_compras import preparar_compra
        compras = User.objects.create_user("ci_compras")
        compras.groups.add(Group.objects.create(name="Compras"))
        ventas = User.objects.create_user("ci_ventas")
        ventas.groups.add(Group.objects.create(name="Ventas"))
        sucursal = Sucursal.objects.create(nombre="Rosario")
        UsuarioSucursal.objects.create(usuario=ventas, sucursal=sucursal)
        marca = Marca.objects.create(nombre="CI ficticia")
        modelo = Modelo.objects.create(marca=marca, nombre="CI moto")
        proveedor = Proveedor.objects.create(razon_social="CI", email="ci@ficticio.invalid", es_fijo=True)
        proveedor.marcas.add(marca)
        item = registrar_pedido(ventas, [{"modelo": modelo, "cantidad": 2}]).items.get()
        clave = uuid4()
        barrera = Barrier(2)
        def crear(_):
            usuario = User.objects.get(pk=compras.pk)
            barrera.wait(timeout=10)
            try:
                return preparar_compra(usuario, "HABITUAL", clave, proveedor=proveedor,
                    items=[item], precios={modelo.pk: "100.10"}).pk
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            ids = list(pool.map(crear, [1, 2]))
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(Compra.objects.count(), 1)
        self.assertEqual(OrigenCompra.objects.count(), 1)
