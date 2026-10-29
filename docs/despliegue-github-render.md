> ANTECEDENTE TÉCNICO (no aplicar): la propuesta de planes pagos de este documento no es la
> configuración vigente. Para esta publicación exclusivamente gratuita seguir
> [despliegue-gratuito.md](despliegue-gratuito.md). No aplicar los planes pagos.

# Preparación de GitHub y Render — KAWA

## Estado y límites de la intervención

Se prepararon archivos locales. No se inicializó Git en el proyecto, no se creó
un repositorio remoto, no se ejecutaron commit/push, no se aplicó un Blueprint,
no se crearon cuentas públicas y no se desplegó ni contrató infraestructura.
Todos los pasos de publicación de esta guía requieren autorización posterior.

## A. Auditoría del repositorio

La carpeta kawa-django y su directorio padre no tienen .git. Git informa que no
son un repositorio. Por lo tanto no existe rama activa, lista de archivos ya
rastreados, commits, remotos ni historial local que se pueda auditar. No es correcto
asegurar que un eventual repositorio remoto esté libre de secretos sin revisarlo.
No se reescribió ni eliminó historial alguno.

Archivos locales sensibles identificados: db.sqlite3 y demo.sqlite3. También hay
.venv, cachés y staticfiles. No se encontraron archivos .env, claves privadas o
respaldos dentro del árbol de publicación inspeccionado. La búsqueda por patrones
comunes de tokens/claves privadas no encontró coincidencias fuera de artefactos
excluidos. Esta búsqueda no es una certificación exhaustiva de ausencia de secretos.

El código y pruebas contienen credenciales ficticias de la demo local y fixtures,
no credenciales reales de producción. Se conservan por compatibilidad. Nunca deben
utilizarse como claves públicas. El entorno desplegado bloquea el cargador antiguo
y exige credenciales nuevas por usuario para una demo pública.

.gitignore ahora excluye .env*, entornos, SQLite/journals, dumps, respaldos,
claves privadas, logs, temporales y archivos recopilados. Conserva .env.example,
código, pruebas y migraciones. Sus reglas se verificaron con git check-ignore en
un repositorio temporal, sin inicializar el proyecto real. .dockerignore evita
incluir esos datos en COPY. .gitattributes conserva LF en scripts shell.

Si se recupera un repositorio anterior, revisar antes de agregar/push: git status,
git ls-files, git log --all y git rev-list --objects --all. .gitignore no elimina
archivos previamente rastreados ni borra secretos del historial. Si aparece una
clave real, detener la publicación y rotarla; cualquier eliminación/rewrite de
historial requiere autorización y un procedimiento separado.

## B. Instalación local y arquitectura

Se conserva el monolito Django: config para configuración; compras para modelos,
servicios, formularios, vistas, Templates y estáticos. Los cinco módulos funcionales
no cambian. SQLite sigue en config.settings, y la demo local en config.demo_settings.
No se alteraron modelos ni migraciones.

Desde la carpeta que contiene manage.py:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
.\.venv\Scripts\python.exe manage.py test
```

Las cuatro dependencias directas se fijaron a las versiones instaladas/verificadas:
Django 5.2.18, Gunicorn 26.2.0, WhiteNoise 6.12.0 y psycopg[binary] 3.3.6.
Actualizar versiones exige revisar advisories y repetir pruebas; pip check solo
comprueba compatibilidad de dependencias, no ausencia de vulnerabilidades.
PyYAML se usó localmente para inspección y no es dependencia de la aplicación.

.env.example contiene únicamente ejemplos sin secretos reales. Django no lo lee
automáticamente: exportar variables o configurarlas en Render. No copiar valores
de ejemplo como credenciales válidas ni publicar el archivo .env resultante.

## C. Configuración de producción

DJANGO_SETTINGS_MODULE=config.production activa:

- DEBUG=False, sin depender de un valor de desarrollo.
- DJANGO_SECRET_KEY obligatoria, aleatoria y de al menos 50 caracteres. No utiliza
  la clave de desarrollo. Generarla una vez con secrets.token_urlsafe(64), guardarla
  en el gestor de secretos y no rotarla automáticamente en cada arranque.
- Hosts explícitos y orígenes HTTPS. RENDER_EXTERNAL_HOSTNAME se incorpora tanto
  a ALLOWED_HOSTS como a CSRF_TRUSTED_ORIGINS; no se permiten comodines.
- DATABASE_URL exclusivamente PostgreSQL, sin fallback SQLite. El parser no expone
  el URL/contraseña al informar errores. TLS require por defecto; no admite disable
  en producción. La URL interna de Render evita tráfico público entre servicios.
- Redirección HTTPS, cookies Secure, sesión HttpOnly, X-Frame-Options DENY,
  Content-Type nosniff y validadores de contraseña.
- SECURE_PROXY_SSL_HEADER para la terminación HTTPS de Render. Esta confianza solo
  es correcta detrás de un proxy que reemplace/controle X-Forwarded-Proto; no exponer
  Gunicorn directamente a Internet con ese encabezado bajo control del cliente.
- WhiteNoise CompressedManifestStaticFilesStorage: archivos versionados y comprimidos.

### Variables

| Variable | Uso |
| --- | --- |
| DJANGO_SETTINGS_MODULE | config.production |
| DJANGO_SECRET_KEY | Secreto fuerte obligatorio, introducido en Render |
| DATABASE_URL | URL interna de la base PostgreSQL, suministrada por Blueprint |
| RENDER_EXTERNAL_HOSTNAME | Render la proporciona; hostname público asignado |
| DJANGO_ALLOWED_HOSTS | Opcional: dominios propios adicionales, separados por coma |
| DJANGO_CSRF_ORIGINS | Opcional: orígenes https://dominio, sin barra final |
| PORT | Render la proporciona a Gunicorn |
| KAWA_PUBLIC_DEMO | false por defecto; true solo para inicialización autorizada |
| KAWA_DEMO_PASSWORDS | JSON secreto de seis claves únicas para la demo pública |

HSTS se configura inicialmente por una hora. Se mantienen sin activar
includeSubDomains y preload, porque no se comprobó el dominio definitivo y no se
solicita inscripción en listas preload. check --deploy mantiene visibles W005 y
W021. No se silencian ni se activa una política persistente de subdominios para
hacer desaparecer esos avisos. Deben decidirse después de validar HTTPS y todos
los subdominios. Las seis advertencias locales iniciales de DEBUG, clave, cookies,
HTTPS y ausencia de HSTS están resueltas en el perfil de producción.

Los scripts usan --fail-level ERROR; las pruebas de configuración verifican que
no aparezcan advertencias distintas de esas dos decisiones de HSTS. La configuración
local sigue siendo local y no debe usarse para publicar.

## D. Render preparado

render.yaml define, sin aplicarlo:

- Web Service Python, plan starter, región Oregon, despliegue automático off.
- PostgreSQL 16 dedicado, misma región, plan 0.1c-256mb y disco inicial 1 GB.
- ipAllowList vacío: sin acceso público externo a PostgreSQL; la app usa red interna.
- .python-version=3.12: Render selecciona el parche disponible de esa rama.
- Build: bash build.sh → instalación, check de seguridad y collectstatic.
- Pre-deploy: python manage.py migrate --noinput.
- Inicio: sh start.sh → Gunicorn en 0.0.0.0:$PORT, logs a salida estándar.
- Health check /login/; no agrega una ruta al dominio de negocio.

SECRET_KEY se solicita con sync:false. No se usa generateValue de Render, cuyo
valor base64 de 256 bits puede ser más corto que la validación mínima elegida.

No hay makemigrations, cargadores ni createsuperuser en build/pre-deploy/start.
Las migraciones de esquema se revisan en Git antes de desplegar, se ejecutan una
vez en pre-deploy y nunca se generan desde el código que arranca. No se importan
SQLite ni cuentas locales a PostgreSQL. Los respaldos existentes no se eliminan.
Antes de futuras migraciones con datos, crear/verificar un respaldo PostgreSQL.

El Dockerfile también se corrigió: usuario no root y sin carga automática ni
migraciones. Recopila estáticos con variables de runtime, no con secretos grabados
en una capa. Su operador debe ejecutar migrate explícitamente en un paso controlado.
Render preparado usa runtime Python, no Docker. No se pudo ejecutar Docker local:
no hay daemon accesible. No se afirma que su build se haya ejecutado aquí.

### Después de autorizar la publicación: GitHub

Se eligió como raíz del repositorio la carpeta kawa-django, que ya contiene
.github, render.yaml y requirements. No inicializar el directorio superior salvo
que se adapten todos los paths de CI/Render.

Comandos NO ejecutados; reemplazar USUARIO por la cuenta real:

```powershell
Set-Location "C:\Users\pc\Downloads\kawa-compras-django\kawa-django"
git init -b main
git add .
git status --short
git diff --cached --check
git diff --cached --name-only
git ls-files -- "*.sqlite*" "*.db*" ".env" "*.pem" "*.key" "*.sql" "*.dump" "*.bak"
```

La última lista debe estar vacía. Revisar además el contenido staged y posibles
secretos antes del commit. Si Git requiere identidad, configurar user.name y
user.email para este repositorio con datos propios; no se configuraron globalmente.

Crear en GitHub un repositorio **vacío**, inicialmente privado, llamado kawa-mvp.
No agregar README, licencia o gitignore remotos para evitar historiales divergentes.
No crear todavía el servicio Render antes de revisar CI. Solo tras aprobar:

```powershell
git commit -m "Prepara MVP KAWA para Render y PostgreSQL"
git remote add origin https://github.com/USUARIO/kawa-mvp.git
git push -u origin main
```

La autenticación debe hacerse con el flujo de GitHub/SSH o un gestor de credenciales;
no incluir un token en la URL del remoto ni pegarlo en scripts. Se pueden cambiar
visibilidad y licencia después de revisar qué se está publicando.

### Después de autorizar el despliegue: Render

1. Revisar resultados de GitHub Actions: SQLite, PostgreSQL, configuración segura y
   Docker. No interpretar este archivo CI como una ejecución ya aprobada.
2. Elegir New → Blueprint, conectar el repositorio y seleccionar render.yaml en la
   raíz. Revisar planes, región y costo ANTES de aplicar: crear el Blueprint puede
   iniciar el primer despliegue y generar cargos aunque autoDeployTrigger sea off.
3. Proporcionar DJANGO_SECRET_KEY fuerte cuando Render lo solicite. No pegar secretos
   en GitHub, screenshots, documentación o el chat. La base provee DATABASE_URL por
   referencia interna. Para dominio propio agregar hosts/orígenes reales.
4. Confirmar PostgreSQL 16 y la misma región. El archivo no reutiliza bases locales.
5. Revisar el build, la salida del check (solo los dos avisos HSTS documentados),
   collectstatic y la aplicación controlada de migraciones en pre-deploy.
6. Revisar el arranque de Gunicorn y abrir la URL HTTPS de Render. Confirmar login,
   CSS/JS en modo claro/oscuro, CSRF y redirección HTTP→HTTPS. No enviar datos reales.
7. Inicializar cuentas por UNA de las alternativas de la sección E. No se crean
   cuentas durante el arranque. Probar permisos y ambos procedimientos con datos
   ficticios, además de que aprobar no aumenta stock.
8. Mantener auto-deploy desactivado y aplicar cambios futuros de forma revisada.

Si se configura manualmente en lugar de Blueprint, usar exactamente sus comandos,
variables y PostgreSQL dedicado. Root Directory vacío si se siguió esta guía de
Git. No seleccionar Docker por detectar el Dockerfile existente.

## E. Inicialización pública: manual y separada

Nunca publicar demo.sqlite3. cargar_demo conserva su modo local anterior y agrega
un modo público protegido por PostgreSQL, KAWA_PUBLIC_DEMO y confirmación manual.
La base debe estar vacía de usuarios y datos comerciales. Un marcador propio de
la demo pública impide duplicados; no se reutiliza la marca local. La carga es
atómica y no cambia contraseñas ni sobrescribe cuentas existentes.

### Alternativa 1: demo académica completa

Solo tras autorización, sobre PostgreSQL dedicado/vacío y desde la Shell del
servicio Render (con entorno de producción):

1. Generar seis contraseñas distintas de al menos 12 caracteres, idealmente con
   secrets.token_urlsafe(24). Guardarlas en un gestor privado. No usar [clave local privada],
   [clave local privada] ni claves reales utilizadas localmente. La validación Django también
   comprueba longitud, similitud y contraseñas comunes.
2. Configurar temporalmente KAWA_PUBLIC_DEMO=true y KAWA_DEMO_PASSWORDS con este
   esquema JSON; los VALOR_* son marcadores, no contraseñas para utilizar:

```json
{"demo_admin":"VALOR_ADMIN","demo_compras":"VALOR_COMPRAS","demo_finanzas":"VALOR_FINANZAS","demo_ventas_rosario":"VALOR_ROSARIO","demo_ventas_mendoza":"VALOR_MENDOZA","demo_ventas_cordoba":"VALOR_CORDOBA"}
```

3. Ejecutar manualmente, NO realizado durante esta preparación:

```sh
python manage.py cargar_demo --settings=config.production --confirmar-demo-publica
```

4. Guardar las credenciales fuera del repositorio, quitar KAWA_DEMO_PASSWORDS y
   volver KAWA_PUBLIC_DEMO=false. No enviar las claves de Administrador/Finanzas a
   una audiencia pública indiscriminada. Las cuentas son operativas de grupos
   Django, no superusuarios nativos. No se debe ejecutar createsuperuser antes de
   la carga: un usuario existente hace que el comando se niegue a mezclar datos.

Repetir la inicialización con banderas/credenciales válidas no restaura estados ni
claves. Sin esas variables el comando se niega antes de escribir. No existe un
reset automático. Si se necesita otra demo, preparar otra base dedicada con
respaldo y autorización; no borrar información para conseguir que la carga pase.

### Alternativa 2: cuentas manuales sin dataset

En una base nueva, y SOLO tras autorizar la creación de cuentas:

```sh
python manage.py createsuperuser --settings=config.production
```

Ingresar una contraseña nueva por el flujo interactivo, no en argumentos o Git.
Luego asignar usuarios, roles y sucursales desde Administración. Un superusuario
sin el grupo Finanzas no puede aprobar. Esta alternativa no permite cargar luego
el dataset sobre los usuarios existentes: son caminos de inicialización distintos.

El cargador legacy cargar_datos se bloquea en config.production. No hay ninguna
llamada automática a ambos cargadores en scripts de despliegue.

## F. Validación y diferencias de base

Localmente se verificaron las pruebas SQLite, parsing de URL PG, rechazo de
configuración insegura, políticas de demo pública, manifiesto/compression WhiteNoise,
respuesta HTTP de los tres estáticos principales y renderizado de login HTTPS.
El check de producción y collectstatic usan secretos efímeros y una URL ficticia,
sin conectarse a ninguna base PostgreSQL. pip check no informa dependencias rotas.

La suite final descubre 134 pruebas: 133 pasan y una se omite por requerir un
PostgreSQL real. Las 126 anteriores se conservan. No hay cambios de migraciones.
YAML fue parseado localmente y contrastado con documentación; no se aplicó ni se
validó contra una cuenta/API de Render. Build.sh no se ejecutó en un runtime Linux
local; sus comandos Django equivalentes se verificaron por las pruebas.

No hay servidor PostgreSQL local accesible y Docker no tiene daemon activo. Por
tanto NO se afirma compatibilidad PostgreSQL validada. CI incluye un servicio
PostgreSQL 16 efímero, la suite completa con config.ci_postgres y una prueba real
de concurrencia de creación de compras. Esa ejecución queda pendiente de publicar
el repo con autorización. No usar la base desplegada como base de pruebas.

Diferencias revisadas:

- SQLite serializa escritores y puede devolver locked. PostgreSQL permite lectores
  concurrentes y espera por filas/índices únicos. No sirven como prueba PG los
  subprocesos que crean archivos SQLite: siguen verificando solo SQLite.
- Se adaptó crear Compra a get_or_create sobre el UUID único. Mantiene la regla
  existente de idempotencia y conflicto de parámetros, también cuando dos inserts
  PG llegan a la vez. No cambia cantidades, precios, roles ni estados de negocio.
- Reservas usan índice único parcial; decisiones/documentos tienen unicidad; las
  transiciones actualizan condicionalmente estados. Deben validarse sobre PG real.
- Decimal, JSON, collations/orden, constraints y transacciones se ejercitan en el
  job PostgreSQL. Los importes mantienen sus límites anteriores por compatibilidad.
- El dataset local solo se habilita en PG de pruebas bajo config.ci_postgres y
  nombre test_*, nunca por ese bypass en config.production.

Para repetir con un PostgreSQL de pruebas dedicado:

```powershell
$env:DATABASE_URL = "postgresql://USUARIO:CLAVE@HOST:5432/kawa_ci?sslmode=require"
.\.venv\Scripts\python.exe manage.py test --settings=config.ci_postgres
```

El usuario necesita permiso para crear la base test_*. No utilizar una URL real de
producción. En el servicio efímero de CI se permite sslmode=disable expresamente;
el parser de producción siempre lo rechaza.

## Costos y riesgos

El Blueprint propone planes PAGOS porque el pre-deploy de Render lo requiere.
Web, compute PostgreSQL y almacenamiento se facturan por separado, con posibles
cargos de tráfico, minutos de pipeline, workspace y respaldos según plan. No se
fija un presupuesto ni se contrata nada sin revisión del precio vigente.

La opción Free puede servir para una prueba temporal, pero el PostgreSQL Free
caduca a los 30 días y hay límites de capacidad, suspensión/arranque y operación.
No se configuró una variante Free que ejecute migraciones ocultas en cada arranque.
Para usar Free se necesita definir y autorizar un procedimiento manual compatible
con sus restricciones; este Blueprint no lo hace.

Antes de publicar: verificar PostgreSQL/CI, autorización y costo, respaldos y
restauración, HTTPS/dominio, claves únicas, permisos de cada rol y contenido
exclusivamente ficticio. El MVP no incorpora rate limiting de login ni hardening
operativo completo; no exponer datos reales. La demo compartida puede ser modificada
por los usuarios operativos y no se reinicia automáticamente.

## Fuentes oficiales consultadas

- https://render.com/docs/deploy-django
- https://render.com/docs/deploys (pre-deploy disponible en planes pagos)
- https://render.com/docs/blueprint-spec
- https://render.com/docs/python-version
- https://render.com/docs/postgresql-creating-connecting (TLS require interno)
- https://render.com/docs/free (duración y límites Free)
- https://render.com/pricing y https://render.com/docs/compute-plans
- https://www.psycopg.org/psycopg3/docs/basic/install.html
- https://whitenoise.readthedocs.io/en/stable/django.html
- https://docs.djangoproject.com/en/5.2/ref/databases/

## Archivos preparados

Nuevos: .dockerignore, .gitattributes, .python-version, .env.example, render.yaml,
build.sh, start.sh, config/database.py, config/production.py, config/ci_postgres.py,
compras/test_despliegue.py y esta guía.

Modificados: .gitignore, requirements.txt, Dockerfile, .github/workflows/ci.yml,
README.md, compras/management/commands/cargar_demo.py, cargar_datos.py y
compras/servicios_compras.py (adaptación técnica de idempotencia, sin nueva regla).

No se cambiaron modelos ni migraciones y no se cargaron datos o cuentas públicas.
La preparación local termina aquí, con PostgreSQL real, CI remoto, publicación y
despliegue pendientes de verificación/autorización.
