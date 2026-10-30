# Verificación de Neon antes de migrar

Objetivo declarado: proyecto kawa-gestion-compras, rama production, base neondb,
región São Paulo. No se aplican migraciones, crean cuentas, recursos o datos.
No se realizan commit, push ni despliegues. SQLite local no se inspecciona ni cambia.

## Resultado de la revisión local

- config.production exige PostgreSQL mediante DATABASE_URL, sin fallback SQLite.
- Django 5.2.18 y psycopg[binary] 3.3.6 están instalados.
- El parser admite sslmode=require y channel_binding=require sin imprimir la URL.
- Se preparó verificar_neon con controles de destino y sesión read-only.
- No hay DATABASE_URL ni DJANGO_SECRET_KEY disponibles en la sesión del agente.
- No se ha comprobado una conexión real: TLS, versión del servidor, estado de
  migraciones e integridad remota quedan pendientes del resultado del comando.

Las credenciales deben permanecer en el entorno privado. Esta guía no contiene
valores operativos ni resultados privados de conexión.

## Confirmación del destino

En Neon Console → Connect, confirmar explícitamente el proyecto, la rama production
y la base neondb. Desactivar Connection pooling y copiar la URL directa completa
solo a la entrada privada de la terminal. No modificar manualmente el hostname.

La conexión PostgreSQL permite confirmar current_database() y el servidor, pero
neondb existe como nombre predeterminado en muchos proyectos. El nombre por sí
solo no acredita pertenencia a KAWA. El hostname esperado debe cotejarse con la
consola seleccionando ese proyecto/rama. El comando exige coincidencia exacta con
ese hostname y rechaza endpoints -pooler para esta inspección.

## Configuración privada en PowerShell

Ejecutar desde kawa-django. Estas variables solo existen en la terminal actual y
no necesariamente se propagan a una sesión del agente que ya estaba iniciada.
No usar setx ni pegar el URL en un comando, archivo versionado o mensaje.

```powershell
# Ejecutar desde la carpeta del proyecto que contiene manage.py.
$env:DJANGO_SETTINGS_MODULE = "config.production"
# Clave efímera para esta comprobación local; no reemplaza la clave futura de Render.
$env:DJANGO_SECRET_KEY = & .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(64))"
$env:DJANGO_ALLOWED_HOSTS = "localhost"
$env:DJANGO_CSRF_ORIGINS = "https://localhost"
$neonSegura = Read-Host "Pegá la URL DIRECTA nueva de Neon, con TLS" -AsSecureString
$env:DATABASE_URL = [System.Net.NetworkCredential]::new("", $neonSegura).Password
```

Mantener los parámetros sslmode=require y channel_binding=require de Neon. No
imprimir DATABASE_URL, no guardar su valor en el historial y no usar los comandos
anteriores con la clave expuesta. .env no se carga automáticamente en este proyecto.

## Verificar sin migrar

El hostname siguiente es ficticio. Reemplazarlo en la terminal por el destino
confirmado en la consola de KAWA, production y neondb; no publicar el valor real:

```powershell
.\.venv\Scripts\python.exe manage.py check --settings=config.production
.\.venv\Scripts\python.exe manage.py verificar_neon --settings=config.production --expected-host ep-ejemplo.sa-east-1.aws.neon.tech --output .local/neon-tls-verificacion.json
```

El check es de configuración. La comprobación real es el segundo comando:

- Rechaza SQLite, otra base, otro host, pooler o TLS deshabilitado antes de conectar.
- Fuerza default_transaction_read_only=on al abrir la conexión. No confía solamente
  en que el código no llame a métodos de escritura.
- Comprueba current_database()=neondb, versión soportada por Django y TLS del
  cliente mediante libpq.PQsslInUse. Informa pg_stat_ssl por separado como
  backend_tls y backend_tls_version.
- Consulta tablas y el historial de migraciones. Usa MigrationExecutor solo para
  construir el plan, nunca migrate ni ensure_schema.
- Revisa restricciones no validadas e índices inválidos en el esquema actual.
- Muestra un JSON sin URL, usuario ni contraseña y opcionalmente guarda un informe
  local ignorado por Git. No sobrescribe un informe previo; usar otro nombre para
  una repetición. Los errores de conexión se informan sin volcar el DSN.

Compartir únicamente ese JSON o avisar que quedó en .local para su revisión. Si
el agente no hereda las variables de esa terminal, no podrá verificar de forma
independiente una conexión configurada solo allí.

Los campos esperados son status=conexion_verificada, database=neondb, tls=true,
read_only=true y migration_history_consistent=true. Una base nueva puede mostrar
migraciones pendientes y tablas ausentes: es información, no una autorización
para aplicarlas. schema_status e integrity_metadata_status distinguen esas situaciones.

## Límites de compatibilidad e integridad

Una conexión correcta verifica controlador, TLS, versión y lectura del catálogo.
No prueba ventas, reservas, aprobaciones o concurrencia de escritura en PostgreSQL.
No es una auditoría completa de filas ni una certificación de integridad de una
aplicación todavía sin esquema. Las pruebas de escritura deben realizarse en un
entorno aislado autorizado, no mediante manage.py test contra esta base de producción.

No ejecutar migrate, makemigrations, cargar_demo, cargar_datos, createsuperuser,
flush o test contra Neon en este paso. La autorización de migraciones se pedirá
solo después de revisar el destino y el informe. No se ejecutará un cambio de
esquema por el solo hecho de que el comando liste pendientes.

Pooling queda sin cambios. Para la inspección y futuras migraciones se usa la URL
directa. Si se decide utilizar pooling en Render, revisar aparte cursores del
servidor y el modo transaccional; no se habilita automáticamente aquí.

## Limpieza del entorno temporal

Después de la verificación, quitar variables de esta terminal sin borrar datos:

```powershell
Remove-Item Env:DATABASE_URL,Env:DJANGO_SETTINGS_MODULE,Env:DJANGO_SECRET_KEY,Env:DJANGO_ALLOWED_HOSTS,Env:DJANGO_CSRF_ORIGINS -ErrorAction SilentlyContinue
Remove-Variable neonSegura -ErrorAction SilentlyContinue
```

Los siguientes comandos nuevos volverán a usar la configuración local predeterminada.
La URL remota no queda en el código ni se publica.

Fuentes oficiales: [Neon Connect](https://neon.com/docs/connect/connect-from-any-app),
[Django PostgreSQL](https://docs.djangoproject.com/en/5.2/ref/databases/).

## Corrección de la comprobación TLS

Neon sitúa un proxy delante de PostgreSQL, incluso en el endpoint directo sin
pooling. pg_stat_ssl describe la sesión que ve PostgreSQL; no acredita por sí solo
el cifrado del tramo cliente → proxy. Por ello (False, None) no contradice que
libpq haya negociado TLS con Neon. El verificador anterior rechazaba ese caso
incorrectamente.

La evidencia exigida ahora es ssl_in_use=True en la conexión viva de libpq.
También se comprueban host, dbname y sslmode efectivos, y se informan únicamente
host, port, dbname, sslmode y channel_binding mediante una lista permitida.
No se serializan DSN, usuario ni contraseña. Se informan versiones de psycopg y
libpq. La versión TLS del backend no se presenta como versión TLS del cliente.
Si falta la evidencia del cliente o TLS está inactivo, la verificación falla.
sslmode=require confirma cifrado; no equivale a validar certificado y hostname
con verify-full. No se altera la política TLS configurada ni channel_binding.

Fuentes primarias:
- https://neon.com/docs/security/security-overview
- https://www.postgresql.org/docs/current/libpq-status.html
- https://www.psycopg.org/psycopg3/docs/api/pq.html

## Resultado de validación de la corrección

- Controlador local: psycopg 3.3.6, libpq 180004 (18.4).
- Suite local: 144 pruebas ejecutadas, 143 aprobadas y una omitida.
- Las cinco pruebas nuevas cubren evidencia del cliente, parámetros efectivos
  sin secretos, rechazo de TLS inactivo o evidencia ausente y separación de TLS
  del cliente respecto de pg_stat_ssl. Las inspecciones simuladas usan SELECT
  y comprueban que no se invoque migrate.
- La suite usa una base temporal local de pruebas; sus fixtures no se cargan en
  Neon ni en la base SQLite de desarrollo.
- La sesión del agente no tiene DATABASE_URL ni DJANGO_SECRET_KEY. El informe
  anterior solo registra no_verificado. La comprobación remota corregida y la
  lista de migraciones pendientes siguen pendientes del nuevo informe privado.
- No se modificaron config.production, el parser DATABASE_URL, requirements,
  modelos ni migraciones. No se realizaron commit, push ni despliegues.

## Informe remoto revisado el 30 de octubre de 2026

El usuario ejecutó el comando corregido en su terminal con las variables privadas.
Se revisó .local/neon-tls-verificacion.json: status=conexion_verificada.

- Destino efectivo: endpoint privado confirmado, puerto 5432, base neondb.
  El hostname operativo se conserva exclusivamente en el informe local ignorado.
  Su pertenencia al proyecto y rama depende de la
  confirmación del hostname en Neon Console, no del nombre neondb por sí solo.
- PostgreSQL 18.6, psycopg 3.3.6 y libpq 18.4.
- TLS del cliente confirmado por libpq.PQsslInUse: true.
- Parámetros efectivos sslmode=require y channel_binding=require.
- backend_tls=false y backend_tls_version=null: se confirma que ese resultado
  no impedía una conexión TLS activa del cliente a Neon.
- Sesión de solo lectura confirmada; historial de migraciones consistente.
- Hay 23 migraciones pendientes: 5 de compras (0001 a 0005), 12 de auth,
  3 de admin, 2 de contenttypes y 1 de sessions. Faltan las 22 tablas de compras.
- No se detectaron restricciones sin validar ni índices inválidos. Al faltar el
  esquema de la aplicación, esto no certifica integridad de datos de negocio.

La conexión está lista para solicitar autorización de la etapa de migraciones.
No se aplicaron migraciones ni se autoriza su ejecución mediante este informe.
No se cargaron datos ni se desplegó en Render. Los apartados anteriores que
describen la comprobación como pendiente corresponden al estado previo a este
informe remoto.

## Migraciones autorizadas y verificadas el 30 de octubre de 2026

Con autorización expresa del usuario, este ejecutó desde su terminal privada
.local/migrar_neon_autorizado.py. Se revisó el informe local
.local/neon-migracion-resultado.json: status=migracion_verificada, stage=finalizado.

Antes de migrar se verificaron config.production, hostname exacto autorizado,
base neondb y TLS activo del cliente. El plan coincidió con las 23 migraciones
revisadas y sus archivos con las huellas SHA-256 registradas localmente.
La retirada de contenttypes.name es una operación estándar prevista de Django;
no se encontraron eliminaciones inesperadas en el plan. No se modificaron las
migraciones históricas.

Se aplicaron las 23 migraciones: compras 0001–0005, auth 0001–0012,
admin 0001–0003, contenttypes 0001–0002 y sessions 0001. El comando migrate se
ejecutó mediante call_command en el proceso configurado con config.production.

Verificaciones posteriores:

- Django check: correcto.
- Cero migraciones pendientes; historial consistente.
- Todas las tablas de modelos de KAWA presentes, incluidas las relaciones
  intermedias automáticas. La lista exacta está en created_tables del informe.
- TLS activo, sslmode=require y channel_binding=require, tanto antes como después.
- Inspección final y conteos realizados en sesiones de solo lectura.
- Sin restricciones no validadas ni índices inválidos.
- Tablas compras_* vacías y auth_user con cero registros: no se crearon usuarios
  ni datos de demostración. Django creó sus metadatos técnicos habituales.

No se ejecutaron flush, cambios de contraseñas, commit, push ni despliegue.
SQLite local no fue el destino. La validación de metadatos y tablas vacías no
constituye una prueba de los flujos de negocio o concurrencia en PostgreSQL.
La etapa autorizada de migraciones quedó finalizada; Render sigue sin desplegar.
