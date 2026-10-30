from io import StringIO
from unittest.mock import patch
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings
from .management.commands.verificar_neon import validar_destino


class VerificarNeonTest(SimpleTestCase):
    def config(self):
        return {"ENGINE": "django.db.backends.postgresql", "NAME": "neondb", "HOST": "ep-ejemplo.sa-east-1.aws.neon.tech", "OPTIONS": {"sslmode": "require"}}

    def test_host_base_y_tls_validos(self):
        cfg = self.config()
        self.assertEqual(validar_destino(cfg, cfg["HOST"]), cfg["HOST"])

    def test_destinos_incorrectos_se_rechazan_antes_de_conectar(self):
        casos = [{"ENGINE": "django.db.backends.sqlite3"}, {"NAME": "otra"},
                 {"HOST": "ep-otro.sa-east-1.aws.neon.tech"}, {"OPTIONS": {"sslmode": "disable"}}]
        for cambios in casos:
            cfg = {**self.config(), **cambios}
            with self.assertRaises(CommandError):
                validar_destino(cfg, self.config()["HOST"])

    def test_no_acepta_pooler_o_url_completa(self):
        cfg = self.config()
        cfg["HOST"] = cfg["HOST"].replace("ep-ejemplo.", "ep-ejemplo-pooler.")
        with self.assertRaises(CommandError):
            validar_destino(cfg, cfg["HOST"])
        with self.assertRaises(CommandError):
            validar_destino(self.config(), "postgresql://usuario:privada@" + self.config()["HOST"] + "/neondb")

    def test_comando_local_no_toca_sqlite(self):
        with self.assertRaises(CommandError):
            call_command("verificar_neon", expected_host=self.config()["HOST"], stdout=StringIO())

    @override_settings(SETTINGS_MODULE="config.production")
    def test_sesion_solo_lectura_y_restauracion_de_opciones(self):
        from .management.commands import verificar_neon as modulo
        from unittest.mock import MagicMock
        conexion = MagicMock()
        conexion.settings_dict = self.config()
        inspeccion = {"database": "neondb", "tls": True, "read_only": True, "pending_migrations": ["compras.0001_initial"]}
        def revisar():
            self.assertIn("default_transaction_read_only=on", conexion.settings_dict["OPTIONS"]["options"])
            return inspeccion
        salida = StringIO()
        with patch.object(modulo, "connection", conexion), patch.object(modulo, "inspeccionar", side_effect=revisar):
            call_command("verificar_neon", expected_host=self.config()["HOST"], stdout=salida)
        self.assertEqual(conexion.settings_dict["OPTIONS"], {"sslmode": "require"})
        self.assertNotIn("PASSWORD", salida.getvalue())
        self.assertIn("conexion_verificada", salida.getvalue())


class EvidenciaClienteTest(SimpleTestCase):
    def raw(self, tls=True, **cambios):
        from types import SimpleNamespace
        valores = {"host": "ep-ejemplo.sa-east-1.aws.neon.tech", "dbname": "neondb",
                   "port": "5432", "sslmode": "require", "password": "NO_PUBLICAR",
                   "user": "NO_PUBLICAR", "channel_binding": "require", **cambios}
        return SimpleNamespace(pgconn=SimpleNamespace(ssl_in_use=tls, info=[
            SimpleNamespace(keyword=k.encode(), val=v.encode()) for k, v in valores.items()]))

    def test_evidencia_real_y_parametros_sin_credenciales(self):
        from .management.commands.verificar_neon import evidencia_cliente
        resultado = evidencia_cliente(self.raw(), VerificarNeonTest().config())
        self.assertTrue(resultado["tls"])
        self.assertEqual(resultado["effective_parameters"]["sslmode"], "require")
        self.assertNotIn("NO_PUBLICAR", str(resultado))

    def test_rechaza_tls_inactivo_y_parametros_incorrectos(self):
        from .management.commands.verificar_neon import evidencia_cliente
        for raw in [self.raw(False), self.raw(sslmode="disable"), self.raw(dbname="otra"), self.raw(host="otro")]:
            with self.subTest(raw=raw.pgconn.ssl_in_use), self.assertRaises(CommandError):
                evidencia_cliente(raw, VerificarNeonTest().config())

    def test_sin_evidencia_no_se_acepta_conexion(self):
        from .management.commands.verificar_neon import evidencia_cliente
        with self.assertRaises(AttributeError):
            evidencia_cliente(object(), VerificarNeonTest().config())

    def inspeccionar_simulado(self, tls_cliente, tls_backend):
        from unittest.mock import MagicMock
        from .management.commands import verificar_neon as modulo
        conexion = MagicMock()
        conexion.settings_dict = VerificarNeonTest().config()
        conexion.connection = self.raw(tls_cliente)
        cursor = conexion.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [("neondb", "170000", "on", "on"), (tls_backend, None)]
        cursor.fetchall.return_value = []
        conexion.introspection.table_names.return_value = []
        executor = MagicMock()
        executor.migration_plan.return_value = []
        with patch.object(modulo, "connection", conexion), patch.object(modulo, "MigrationExecutor", return_value=executor):
            return modulo.inspeccionar(), cursor, executor

    def test_proxy_sin_tls_backend_no_invalida_tls_cliente(self):
        resultado, cursor, executor = self.inspeccionar_simulado(True, False)
        self.assertTrue(resultado["tls"])
        self.assertFalse(resultado["backend_tls"])
        executor.migrate.assert_not_called()
        self.assertTrue(all(c.args[0].startswith("SELECT ") for c in cursor.execute.call_args_list))

    def test_tls_backend_no_puede_sustituir_tls_cliente(self):
        with self.assertRaises(CommandError):
            self.inspeccionar_simulado(False, True)
