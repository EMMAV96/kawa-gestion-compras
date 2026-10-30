# Preparación de GitHub y Render Free — 30/10/2026

Repositorio: https://github.com/EMMAV96/kawa-gestion-compras.git
Rama main. Último commit existente: 3a40f96 (feat: implement KAWA Django MVP).
Esta revisión no realiza commit, push, despliegue ni consultas a Neon.

## Archivos pendientes respecto del último commit

- .gitignore: excluye .local/ con informes y scripts privados.
- .dockerignore: agrega .local para excluir esos artefactos del contexto Docker.
- compras/management/commands/verificar_neon.py: inspección controlada de solo
  lectura; comprueba TLS del cliente con libpq, sin confundirlo con pg_stat_ssl.
- compras/test_verificar_neon.py: pruebas del verificador.
- compras/test_despliegue.py: controles de exclusiones, ausencia de migraciones
  en build/start y Blueprint gratuito sin recursos adicionales.
- docs/verificacion-neon.md: evidencia y límites de las verificaciones anteriores.
- docs/despliegue-gratuito.md: distingue la instancia existente de los pasos
  históricos de inicialización.
- docs/preparacion-render.md: este informe.

Los archivos .local, las bases SQLite, .env, entornos virtuales, respaldos,
certificados privados y credenciales no forman parte del conjunto publicable.
La revisión de archivos rastreados y nuevos no ignorados no detectó secretos
reales: las URLs con credenciales identificadas son marcadores o fixtures de CI
y pruebas con destino ficticio/local. Esto no reemplaza la protección continua
de secretos de GitHub ni acredita credenciales fuera del conjunto revisado.

## Configuración verificada

- render.yaml define un solo Web Service Python, plan free, auto-deploy desactivado,
  sin bases Render, discos persistentes ni pre-deploy.
- Python 3.12 y dependencias fijadas: Django, Gunicorn, WhiteNoise y psycopg binary.
- build.sh instala dependencias, ejecuta check --deploy y collectstatic.
- start.sh exige config.production e inicia Gunicorn en 0.0.0.0:$PORT.
- Producción exige DATABASE_URL PostgreSQL con TLS; no admite SQLite ni fallback.
- RENDER_EXTERNAL_HOSTNAME se incorpora a ALLOWED_HOSTS y al origen CSRF HTTPS.
  Dominios propios deben configurarse explícitamente, sin comodines.
- DEBUG=False, redirección HTTPS, cookies seguras y cabecera proxy HTTPS.
- WhiteNoise después de SecurityMiddleware; estáticos con manifiesto y compresión.
- Dos avisos HSTS deliberados: security.W005 y security.W021 (sin includeSubDomains
  ni preload). No son errores que impidan desplegar.
- No se modificaron modelos, migraciones ni reglas de negocio.

## Pasos posteriores, sin ejecutar todavía

1. Publicar los cambios revisados en GitHub únicamente tras autorización.
2. Crear o configurar un Web Service Python Free desde ese repositorio. La raíz
   del repositorio ya contiene manage.py: Root Directory vacío. Build: bash build.sh.
   Start: sh start.sh. Health check: /login/. Auto-deploy: desactivado.
3. Guardar DATABASE_URL de la instancia Neon existente y DJANGO_SECRET_KEY estable
   y fuerte en el panel privado de Render. Nunca en archivos del repositorio.
4. DJANGO_SETTINGS_MODULE=config.production y KAWA_PUBLIC_DEMO=false. Render
   proporciona RENDER_EXTERNAL_HOSTNAME; no copiar localhost como host público.
   Solo añadir DJANGO_ALLOWED_HOSTS y DJANGO_CSRF_ORIGINS para dominios propios.
5. No ejecutar migraciones, createsuperuser ni cargadores: el esquema y el
   superusuario ya están preparados según la información de esta instancia.
6. Tras autorización para desplegar, validar HTTPS, estáticos, login y CSRF en la
   URL real. No se certifica aquí un despliegue que aún no se realizó.

## Gratuidad y límites

Condiciones contrastadas con https://render.com/docs/free el 30/10/2026:
Free admite Python, HTTPS y datos externos como Neon. Se suspende tras 15 minutos
sin tráfico y despertar puede tardar alrededor de un minuto. Incluye 750 horas
por workspace y mes; no tiene shell, SSH, one-off jobs ni discos persistentes.
El almacenamiento local es efímero: PostgreSQL debe permanecer en Neon.

Las cuotas de transferencia y builds son compartidas por workspace. Con método
de pago pueden generarse cargos por excedentes; para conservar el criterio de
cero cargos, no agregar un método de pago ni aceptar upgrades. Sin método de
pago, Render documenta suspensión de servicios o builds al agotar esas cuotas.
También puede suspender servicios Free con tráfico saliente elevado, incluso
hacia una base externa. El servicio está configurado en Oregon y Neon en São
Paulo: habrá latencia entre regiones; no se crearon recursos para cambiarlo.

No se garantizan disponibilidad permanente ni rendimiento de producción.
Las pruebas de concurrencia PostgreSQL requieren un entorno aislado de CI;
no se ejecutan sobre la base Neon con datos del usuario.

## Resultado de validación local

- Suite completa: 146 pruebas, 145 aprobadas y una omitida (concurrencia con
  PostgreSQL real). Ejecución explícita con config.settings y variables de
  producción retiradas del subproceso. Base de pruebas temporal; sin acceso a Neon.
- Incluye check --deploy de producción y collectstatic en directorio temporal,
  entrega de estáticos con WhiteNoise y acceso HTTPS a login, sin conexión a DB.
- pip check: sin incompatibilidades. git diff --check: correcto.
- Exclusiones verificadas mediante git check-ignore, incluidos ambos informes
  de Neon, .env, .env.production, db.sqlite3 y .venv.
- Revisión final de patrones de tokens y claves privadas: sin hallazgos reales.
- Auditoría final de privacidad: se sustituyeron el hostname operativo y una
  ruta personal en docs/verificacion-neon.md por ejemplos. Los informes privados
  siguen exclusivamente en .local/, fuera de Git y del contexto Docker.
- Listo para publicar los cambios revisados y configurar el despliegue Free,
  sujeto a autorización de commit/push y posterior despliegue. La configuración
  privada de variables en Render y la comprobación de la URL pública quedan
  pendientes. No se crearon recursos ni se efectuaron esas acciones.
