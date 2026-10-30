"""Read-only Neon verification. Does not apply migrations or create tables."""
import json
from pathlib import Path
from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


def validar_destino(config, esperado):
    if config.get("ENGINE") != "django.db.backends.postgresql":
        raise CommandError("Verificación cancelada: se requiere PostgreSQL; no se accede a SQLite.")
    if config.get("NAME") != "neondb":
        raise CommandError("Verificación cancelada: la base configurada no es neondb.")
    host = str(config.get("HOST", "")).lower().rstrip(".")
    esperado = str(esperado).lower().rstrip(".")
    if not esperado.endswith(".neon.tech") or not esperado.startswith("ep-") or any(c in esperado for c in ("/", "@", ":", " ")):
        raise CommandError("Ingrese solo el hostname directo ep-…neon.tech copiado de Neon Connect.")
    if host != esperado:
        raise CommandError("Verificación cancelada: el hostname no coincide con el confirmado en Neon.")
    if "-pooler." in host:
        raise CommandError("Use la URL directa, con Connection pooling desactivado para esta inspección.")
    if config.get("OPTIONS", {}).get("sslmode") not in {"require", "verify-ca", "verify-full"}:
        raise CommandError("Verificación cancelada: se exige TLS.")
    return host


def evidencia_cliente(raw, config):
    """Inspect the live libpq connection, never serialize a DSN or credentials."""
    import psycopg
    if raw.pgconn.ssl_in_use is not True:
        raise CommandError("libpq no confirma TLS en la conexión del cliente; no se continúa.")
    permitidos = {b"host", b"port", b"dbname", b"sslmode", b"channel_binding"}
    parametros = {
        opcion.keyword.decode("ascii"): opcion.val.decode("utf-8")
        for opcion in raw.pgconn.info
        if opcion.keyword in permitidos and opcion.val is not None
    }
    if (parametros.get("host", "").lower().rstrip(".") != config["HOST"].lower().rstrip(".")
            or parametros.get("dbname") != "neondb"
            or parametros.get("sslmode") not in {"require", "verify-ca", "verify-full"}):
        raise CommandError("Los parámetros efectivos no confirman el destino y TLS requeridos.")
    return {"tls": True, "tls_evidence": "libpq.PQsslInUse / psycopg.pgconn.ssl_in_use",
            "effective_parameters": parametros, "driver": "psycopg",
            "driver_version": psycopg.__version__, "libpq_version": psycopg.pq.version()}


def inspeccionar():
    with connection.cursor() as cursor:
        cliente = evidencia_cliente(connection.connection, connection.settings_dict)
        cursor.execute("SELECT current_database(), current_setting('server_version_num'), current_setting('transaction_read_only'), current_setting('default_transaction_read_only')")
        database, version_num, solo_lectura, defecto_lectura = cursor.fetchone()
        if database != "neondb" or solo_lectura != "on" or defecto_lectura != "on":
            raise CommandError("La base conectada o el modo de solo lectura no coinciden con lo solicitado.")
        cursor.execute("SELECT ssl, version FROM pg_stat_ssl WHERE pid = pg_backend_pid()")
        tls = cursor.fetchone()
        connection.check_database_version_supported()
        tablas = set(connection.introspection.table_names(cursor))
        esperadas = {modelo._meta.db_table for modelo in apps.get_app_config("compras").get_models()}
        cursor.execute("SELECT conname FROM pg_constraint WHERE connamespace = current_schema()::regnamespace AND contype IN ('f','c') AND NOT convalidated ORDER BY conname")
        restricciones = [r[0] for r in cursor.fetchall()]
        cursor.execute("SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = current_schema() AND (NOT i.indisvalid OR NOT i.indisready) ORDER BY c.relname")
        indices = [r[0] for r in cursor.fetchall()]
    # Constructor/plan/history are read-only. Never call migrate or ensure_schema.
    executor = MigrationExecutor(connection)
    executor.loader.check_consistent_history(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    return {"database": database, "postgres_version_num": int(version_num),
        **cliente, "backend_tls": bool(tls[0]) if tls else None,
        "backend_tls_version": tls[1] if tls else None, "read_only": True,
        "migration_history_consistent": True,
        "schema_status": "pendiente_migraciones" if plan or (esperadas - tablas) else "tablas_y_migraciones_presentes",
        "integrity_metadata_status": "advertencias" if restricciones or indices else "sin_anomalias_en_metadatos",
        "pending_migrations": [f"{m.app_label}.{m.name}" for m, backwards in plan],
        "missing_app_tables": sorted(esperadas - tablas),
        "unvalidated_constraints": restricciones, "invalid_indexes": indices,
        "scope": "metadatos y esquema; sin pruebas de escritura ni auditoría completa de filas"}


class Command(BaseCommand):
    help = "Comprueba Neon neondb con TLS y sesión read-only. No migra, no crea cuentas ni tablas."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--expected-host", required=True, help="Hostname directo confirmado en el proyecto/rama de Neon; sin credenciales.")
        parser.add_argument("--output", help="Archivo JSON de resultado sin URL, usuario ni contraseña.")

    def handle(self, *args, **options):
        if settings.SETTINGS_MODULE != "config.production":
            raise CommandError("Use --settings=config.production; no se inspecciona la base local.")
        config = connection.settings_dict
        host = validar_destino(config, options["expected_host"])
        originales = dict(config.get("OPTIONS", {}))
        connection.close()
        config["OPTIONS"] = {**originales, "options": "-c default_transaction_read_only=on"}
        resultado = {"status": "no_verificado", "expected_host": host}
        try:
            resultado.update(inspeccionar())
            resultado["status"] = "conexion_verificada"
        except CommandError as error:
            resultado["error"] = str(error)
        except Exception as error:
            # Do not expose connection exceptions/DSNs, usernames or passwords.
            resultado["error_type"] = type(error).__name__
            resultado["error"] = "No se completó la inspección. Revisar red, credenciales, TLS y permisos de lectura. No se aplicaron migraciones."
        finally:
            connection.close()
            config["OPTIONS"] = originales
        texto = json.dumps(resultado, ensure_ascii=False, indent=2)
        if options.get("output"):
            destino = Path(options["output"])
            if destino.exists():
                raise CommandError("El archivo de resultado ya existe. Elija otro nombre; no se sobrescribe.")
            destino.parent.mkdir(parents=True, exist_ok=True)
            with destino.open("x", encoding="utf-8") as archivo:
                archivo.write(texto + "\n")
        self.stdout.write(texto)
        if resultado["status"] != "conexion_verificada":
            raise CommandError("Inspección incompleta. Consulte el resultado sin incluir credenciales.")
