# Publicación GitHub y despliegue académico gratuito

Repositorio solicitado: https://github.com/EMMAV96/kawa-gestion-compras.git
Carpeta raíz de Git: kawa-django (donde está manage.py).

## Alcance y gratuidad verificada

Se preparó un Web Service Render Free y PostgreSQL Neon Free. No se crearon
recursos ni se ejecutó un despliegue. No hay planes pagos ni una base Render paga
en render.yaml. La publicación del código no aplica el Blueprint.

Condiciones consultadas el 29/10/2026 en documentación oficial:

- Render Free admite Python/Django y HTTPS. Se duerme tras 15 minutos sin tráfico;
  despertar puede tardar alrededor de un minuto. Su disco local es efímero.
- No incluye shell, SSH, one-off jobs ni pre-deploy. Las migraciones NO pueden
  quedar en preDeployCommand ni depender de una shell del servicio.
- Tiene límites de horas, tráfico y build según workspace. No agregar método de
  pago ni contratar upgrades; si se llega a una cuota, aceptar suspensión o esperar
  la renovación. Revisar la pantalla de costos antes de confirmar cualquier alta.
- Neon Free figura como $0, sin tarjeta ni límite temporal del plan, con 1 GB por
  proyecto, 100 CU-horas mensuales y 5 GB de transferencia pública por proyecto.
  Se suspende por inactividad después de cinco minutos. Las cuotas/condiciones
  pueden cambiar: verificarlas nuevamente antes de crear el proyecto.
- Render PostgreSQL Free no se eligió: sus bases caducan a los 30 días y no son una
  solución persistente para una demo que deba seguir disponible sin pagar.

Fuentes: [Render Free](https://render.com/docs/free),
[Neon pricing](https://neon.com/pricing),
[Neon plans](https://neon.com/docs/introduction/plans).
No se garantiza disponibilidad permanente ni capacidad fuera de las cuotas gratis.

## Configuración preparada

render.yaml ahora contiene solo un servicio plan: free, sin sección databases,
sin preDeployCommand y con autoDeployTrigger: off. DATABASE_URL y DJANGO_SECRET_KEY
se solicitan como secretos, sin valores en el repositorio. No aplicar el Blueprint
ni crear el servicio hasta autorizar el despliegue.

Build: bash build.sh (instalar dependencias, check --deploy, collectstatic).
Start: sh start.sh (Gunicorn). Ningún arranque genera/aplica migraciones, carga
usuarios o ejecuta demos. El perfil config.production mantiene PostgreSQL obligatorio,
TLS, DEBUG=False, cookies seguras, hosts/orígenes explícitos y WhiteNoise.

SQLite continúa en desarrollo local; los archivos SQLite están excluidos de Git
y Docker. No copiar SQLite a Render ni utilizarlo para conservar datos allí.

La URL directa de Neon puede incluir sslmode=require y channel_binding=require;
config/database.py acepta esos parámetros sin aceptar SSL deshabilitado en producción.
Preferir conexión directa (no pooled) para este MVP y para migraciones, evitando
cambios de comportamiento asociados a pooling de transacciones.

## Contraseñas y preparación del commit

Se retiraron las contraseñas operativas de demo del código y documentación. Los
cargadores locales requieren KAWA_LOCAL_DEMO_PASSWORD para una carga nueva. Las
cuentas/bases ya existentes no se sobrescriben. El modo público conserva seis
claves distintas proporcionadas por KAWA_DEMO_PASSWORDS y bloquea las claves locales
retiradas mediante hashes, sin publicar su texto.

Las pruebas conservan sus escenarios y usan credenciales efímeras en sus fixtures,
no contraseñas válidas para cuentas de demo. La clave de desarrollo de Django ya
no está hardcodeada: sin variable se genera una temporal por proceso. Para mantener
sesiones locales entre reinicios, exportar una DJANGO_SECRET_KEY privada y estable.
Producción siempre exige su variable fuerte y no usa ese fallback de desarrollo.

.gitignore y .dockerignore excluyen .env, entornos, SQLite/journals, dumps,
respaldos, claves privadas, logs y artefactos. .env.example contiene solo marcadores.
Se preservan código, migraciones, pruebas, wireframes y documentación técnica.
Antes de subir se revisan los archivos staged y el remoto exacto. No se fuerza
ninguna rama ni se reemplaza historial remoto.

## Variables para el servicio gratuito

| Variable | Valor/origen |
| --- | --- |
| DJANGO_SETTINGS_MODULE | config.production |
| DJANGO_SECRET_KEY | Clave privada fuerte de al menos 50 caracteres |
| DATABASE_URL | URL directa Neon, PostgreSQL con TLS |
| RENDER_EXTERNAL_HOSTNAME | Render la proporciona; se usa como host/origen HTTPS |
| DJANGO_ALLOWED_HOSTS | Solo si se añaden dominios propios, sin esquema |
| DJANGO_CSRF_ORIGINS | Solo para dominios propios, https://dominio sin barra final |
| KAWA_PUBLIC_DEMO | false en funcionamiento normal |
| KAWA_DEMO_PASSWORDS | Solo durante inicialización manual autorizada |

Nunca poner contraseñas en GitHub, comandos con argumentos, capturas o mensajes.
.env no se lee automáticamente: exportar variables o usar el panel de secretos.

## Pasos manuales posteriores: sin ejecutar en esta preparación

1. Confirmar que CI SQLite/PostgreSQL y las verificaciones sean satisfactorias.
   No se certificó aquí PostgreSQL real: el equipo no tiene servidor disponible.
2. En Neon, elegir exclusivamente Free, sin tarjeta/upgrades, una base nueva dedicada
   a datos ficticios y una región cercana a Oregon. Comprobar cuotas actuales.
3. Copiar privadamente la URL directa de conexión con SSL desde Neon. No agregarla
   a un archivo versionado. Configurar un entorno local de administración temporal:

```powershell
$env:DJANGO_SETTINGS_MODULE = "config.production"
$seguro = Read-Host "DATABASE_URL de Neon (privada)" -AsSecureString
$env:DATABASE_URL = [System.Net.NetworkCredential]::new("", $seguro).Password
$seguro = Read-Host "DJANGO_SECRET_KEY privada" -AsSecureString
$env:DJANGO_SECRET_KEY = [System.Net.NetworkCredential]::new("", $seguro).Password
$env:DJANGO_ALLOWED_HOSTS = "localhost"
$env:DJANGO_CSRF_ORIGINS = "https://localhost"
.\.venv\Scripts\python.exe manage.py check --deploy
.\.venv\Scripts\python.exe manage.py showmigrations
.\.venv\Scripts\python.exe manage.py migrate --plan
```

4. Revisar el plan y confirmar que la URL apunta a la base ficticia correcta. Solo
   con autorización para cambiar su esquema:

```powershell
.\.venv\Scripts\python.exe manage.py migrate --noinput
.\.venv\Scripts\python.exe manage.py migrate --check
```

No ejecutar makemigrations ni importar los archivos SQLite locales. Para cambios
futuros, crear y verificar respaldo de Neon antes de migrar datos existentes.

5. Inicializar por UNA alternativa, con autorización y de forma manual:
   - Dataset: base sin usuarios, KAWA_PUBLIC_DEMO=true, KAWA_DEMO_PASSWORDS con seis
     claves nuevas/únicas, y cargar_demo --confirmar-demo-publica. No crear primero
     un superusuario porque el dataset se niega a mezclar información.
   - Sin dataset: createsuperuser interactivo con clave nueva, luego usuarios/roles.
   Los comandos se ejecutan desde este entorno local conectado a Neon, no una shell
   de Render Free. Nunca durante build o arranque. No se ejecutó ninguno ahora.
6. En Render, crear Web Service Python desde el repositorio GitHub, Root Directory
   vacío, elegir explícitamente Free y auto-deploy Off. Usar los comandos build/start
   del YAML y agregar los secretos en el panel. **Este paso despliega: requiere
   autorización posterior y no se ha realizado.** No habilitar discos, jobs o planes
   pagos. No intentar configurar pre-deploy.
7. Revisar URL HTTPS, estáticos, login, CSRF, roles y recorridos con datos ficticios.
   Las migraciones deben estar aplicadas antes del primer acceso a tablas.
8. Si se usó dataset, quitar KAWA_DEMO_PASSWORDS y dejar KAWA_PUBLIC_DEMO=false. No
   compartir credenciales administrativas indiscriminadamente.
9. Quitar las variables del proceso local al terminar, sin borrar datos:

```powershell
Remove-Item Env:DJANGO_SETTINGS_MODULE,Env:DATABASE_URL,Env:DJANGO_SECRET_KEY,Env:DJANGO_ALLOWED_HOSTS,Env:DJANGO_CSRF_ORIGINS,Env:KAWA_PUBLIC_DEMO,Env:KAWA_DEMO_PASSWORDS -ErrorAction SilentlyContinue
```

Esto vuelve al SQLite predeterminado al ejecutar comandos nuevos. No cambia la
configuración o los datos del servicio remoto.

## Demo local sin contraseñas publicadas

Para una carga nueva y aislada:

```powershell
$clave = Read-Host "Clave privada exclusiva para la demo local" -AsSecureString
$env:KAWA_LOCAL_DEMO_PASSWORD = [System.Net.NetworkCredential]::new("", $clave).Password
.\.venv\Scripts\python.exe manage.py migrate --settings=config.demo_settings
.\.venv\Scripts\python.exe manage.py cargar_demo --settings=config.demo_settings
Remove-Item Env:KAWA_LOCAL_DEMO_PASSWORD
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8001 --settings=config.demo_settings
```

Repetir el cargador no cambia las cuentas existentes ni sus claves. Para esas
cuentas usar la clave que ya tengan o el restablecimiento administrativo autorizado.

## Limitaciones y controles

Persistencia: únicamente Neon para datos públicos. Los archivos locales de Render
son descartables; no almacenar allí respaldos o SQLite. No hay tareas programadas,
monitoring de producción ni reset automático de la demo. No usar servicios para
mantener artificialmente despierto el plan gratis.

Cold starts de Render/Neon pueden retrasar la presentación: abrir la URL con tiempo.
Fuera de las cuotas, no aceptar upgrades; utilizar una demo local si el servicio se
suspende. No se activó facturación ni ningún mecanismo de pago.

Se mantienen visibles dos avisos opcionales HSTS (subdominios y preload), sin
relajar HTTPS ni cookies. Una URL pública no vuelve al MVP apto para datos reales.

La guía anterior de despliegue se conserva como antecedente técnico; su propuesta
de planes pagos queda reemplazada para esta publicación por este procedimiento.
