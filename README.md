# KAWA S.R.L. — MVP de gestión

Monolito Python/Django con SQLite, ORM, autenticación nativa y Django Templates
(HTML/CSS). Incluye stock por sucursal, ventas atómicas, pedidos, proveedores,
solicitudes, cotizaciones, compras y decisiones financieras. Aprobar una compra
no incrementa stock. Los documentos son HTML imprimibles.

## Instalación y ejecución local

Desde la carpeta `kawa-django`, donde está `manage.py`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

Abrir http://127.0.0.1:8000/. En una instalación existente usar sus cuentas y claves
actuales: no se crean usuarios automáticamente. En una base nueva común, crear el
primer administrador con `manage.py createsuperuser` usando el mismo intérprete.
El grupo Finanzas debe asignarse explícitamente para decidir compras, incluso
si el usuario es superusuario.

Los scripts locales `iniciar.bat` e `iniciar.sh` preparan dependencias y aplican
migraciones existentes; ya no generan migraciones ni cargan usuarios de ejemplo.
En Linux/Mac puede activarse `.venv/bin/activate` y usar `python manage.py ...`.

## Demostración aislada

Estos comandos utilizan **demo.sqlite3**, no la base habitual **db.sqlite3**:

```powershell
.\.venv\Scripts\python.exe manage.py migrate --settings=config.demo_settings
.\.venv\Scripts\python.exe manage.py cargar_demo --settings=config.demo_settings
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8001 --settings=config.demo_settings
```

Abrir http://127.0.0.1:8001/. Usuarios ficticios:

| Usuario | Rol / sucursal |
| --- | --- |
| demo_admin | Administrador |
| demo_compras | Compras |
| demo_finanzas | Finanzas |
| demo_ventas_rosario | Ventas / Rosario |
| demo_ventas_mendoza | Ventas / Mendoza |
| demo_ventas_cordoba | Ventas / Córdoba |

Para una carga nueva, definí una clave privada mediante `KAWA_LOCAL_DEMO_PASSWORD` antes de ejecutar `cargar_demo`. No hay contraseña predeterminada. Las cuentas existentes conservan su clave.
El comando es manual y transaccional. Repetirlo no restaura ni sobrescribe datos,
contraseñas, roles o estados. Una base con datos preexistentes que no sean esta
demo se rechaza; nunca se vacía automáticamente. Para otra demo, elegir un archivo
nuevo con `KAWA_DEMO_DB_PATH` y ejecutar los mismos comandos con esos settings.

El cargador antiguo `cargar_datos` queda por compatibilidad con pruebas anteriores;
no usarlo para preparar la presentación ni sobre la base habitual.

## Pruebas y verificaciones

```powershell
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py migrate --check
```

La Etapa 5 conserva las 105 pruebas anteriores y agrega pruebas de integración
con inicio de sesión, CSRF y los tres recorridos completos. Los tests usan bases
aisladas; las pruebas concurrentes usan archivos SQLite temporales.

## Documentación

- [Etapa 2: Stock y Ventas](docs/etapa2-stock-ventas.md).
- [Etapa 3: Pedidos y Proveedores](docs/etapa3-pedidos-proveedores.md).
- [Etapa 4: Compras y Aprobaciones](docs/etapa4-gestion-compras.md).
- [Etapa 5: auditoría, arquitectura, pruebas y limitaciones](docs/etapa5-integracion-validacion.md).
- [Guía paso a paso para demostrar el MVP](docs/guia-demostracion-mvp.md).

Los wireframes estáticos de `docs/wireframes/` son referencias, no pantallas
operativas ni documentación académica RF/UML original.

## GitHub y Render (preparación, todavía no publicado)

Producción se configura con `DJANGO_SETTINGS_MODULE=config.production` y usa
PostgreSQL por `DATABASE_URL`, HTTPS, cookies seguras, WhiteNoise y Gunicorn.
El desarrollo conserva SQLite. `.env.example` contiene solo marcadores y no se
lee automáticamente. `render.yaml` utiliza Render Free y deja auto-deploy off; PostgreSQL se configura por una URL de Neon Free.
No se cargan demos ni se crean usuarios al iniciar.

Ver [auditoría Git, variables, comandos de publicación, despliegue y costos](docs/despliegue-github-render.md).
La guía también explica cómo inicializar una demo pública con claves nuevas,
únicas y secretas, sin reutilizar las conocidas localmente. No ejecutar ese paso
sin autorización. No se importan las bases SQLite al servicio público.

PostgreSQL real y el pipeline remoto están pendientes: la verificación local no
constituye una certificación del despliegue. La carpeta actual no tiene Git
inicializado; los comandos de commit/push se entregan solo para aprobación posterior.

## Interfaz modernizada

Sidebar por módulos, navegación responsive y temas claro/oscuro sin cambios de
negocio. Ver [componentes, validación y checklist visual en Chrome](docs/rediseño-frontend-ux-ui.md).


## Publicación y alojamiento gratuito

Repositorio: https://github.com/EMMAV96/kawa-gestion-compras

La configuración vigente no incluye servicios pagos ni migraciones automáticas.
Ver [Render Free + Neon Free, variables e inicialización manual](docs/despliegue-gratuito.md).
La propuesta paga anterior queda como antecedente y no debe aplicarse para esta demo.
No se han creado recursos ni desplegado el servicio.
