# Etapa 5: Integración, validación y demostración

## Resultado y alcance

El MVP conserva el monolito Python/Django, SQLite, ORM, Django Templates, HTML/CSS
y la aplicación compras. Esta etapa agrega datos aislados y pruebas integrales,
corrige preparación local y presentación de roles/menú, y documenta resultados.
No agrega módulos de negocio, no cambia sus reglas ni modifica configuraciones
de producción. No se realizaron commit, push o despliegues.

Entorno verificado: Python 3.11.9, Django 5.2.18 y SQLite 3.45.1 en Windows.

| Verificación | Resultado |
| --- | --- |
| Suite anterior | 105 pruebas aprobadas antes de los cambios |
| Suite final | 117 pruebas aprobadas; 12 nuevas en test_integracion.py |
| Django check, configuración habitual y demo | Sin problemas |
| makemigrations --check --dry-run | Sin cambios pendientes |
| migrate --check | Migraciones aplicadas |
| SQLite integrity_check / foreign_key_check | Correctos en base habitual y demo |
| Conservación de información | Todos los registros de db.sqlite3 iguales a la instantánea inicial |
| Migraciones 0001–0005 | Hashes intactos; no se creó ninguna migración |
| Carga de demo repetida | Segunda ejecución sin modificaciones |
| Revisión visual en navegador | No completada: no hay navegadores conectados |
| check --deploy | Seis advertencias esperadas del entorno local; no apto para publicación directa |

## Arquitectura y carpetas

```text
kawa-django/
  manage.py
  config/
    settings.py           # Configuración habitual y db.sqlite3
    demo_settings.py      # Extiende la anterior con SQLite separado y cookies propias
    urls.py, wsgi.py
  compras/
    models.py             # Dominio y restricciones de base
    permisos.py           # Grupos y acceso por sucursal
    servicios.py          # Stock, ventas y compatibilidad anterior
    servicios_pedidos.py  # Pedidos, proveedores, solicitudes y ofertas
    servicios_compras.py  # Compras, reservas, documentos y decisiones
    forms.py, forms_compras.py
    views.py, views_compras.py, urls.py
    context.py, admin.py
    management/commands/  # Cargadores manuales
    migrations/           # 0001 a 0005, sin cambios en esta etapa
    templates/, static/
    tests.py, test_*.py
  docs/
  db.sqlite3              # Información habitual, no se cargó demo aquí
  demo.sqlite3            # Datos ficticios aislados, ignorados por Git
```

Las vistas validan formularios y llaman servicios. Los servicios autorizan las
operaciones y ejecutan transacciones ORM. Restricciones de unicidad, cantidades y
estados refuerzan la integridad en SQLite. Los GET no ejecutan decisiones ni
transiciones. Los POST están protegidos por CSRF y autenticación.

## Modelos y módulos

| Módulo | Modelos principales | Integración verificada |
| --- | --- | --- |
| Catálogos y usuarios | Marca, Modelo, Sucursal, UsuarioSucursal, User/Group | Referencias protegidas y sucursal de usuarios de Ventas |
| Stock | Stock, AjusteStock | Unicidad sucursal/modelo, cantidades no negativas y carga de Administrador |
| Ventas | Venta, DetalleVenta | Descuento atómico, reenvío idempotente y resumen quincenal |
| Pedidos | ListadoFaltantes, ItemFaltante | Responsable, sucursal, detalle, filtros y consolidación |
| Proveedores y ofertas | Proveedor, EmisionSolicitud, SolicitudCotizacion, DetalleSolicitudCotizacion, Cotizacion, DetalleCotizacion | Marcas/activos, copias históricas, ofertas completas/parciales y comparación por cesta |
| Compras | Compra, DetalleCompra, OrigenCompra, DocumentoCompra, DecisionFinanciera, MovimientoCompra | Reservas exclusivas, precios históricos, documentos, transiciones y decisión única |

Los importes usan Decimal. Las compras no realizan recepción y aprobar nunca
incrementa existencias. Se conservan los significados de solicitado, las reservas
vigentes y los estados definidos en las etapas anteriores.

## Roles y permisos

- Ventas registra ventas/pedidos únicamente en su sucursal. Las consultas se
  limitan por sucursal en backend; un detalle ajeno devuelve 404.
- Compras consulta todas las sucursales, gestiona proveedores, solicitudes/ofertas
  y prepara/documenta/envía compras. No decide financieramente por ese rol.
- Finanzas consulta stock/ventas y compras según lo existente, usa su bandeja y
  registra decisiones. No recibe permiso para preparar o documentar compras.
- Administrador administra usuarios/catálogos, ajusta stock y conserva las
  facultades operativas de etapas anteriores; no adquiere permiso financiero.
- La pertenencia explícita a Finanzas se exige incluso a superusuarios. Si una
  persona tiene varios grupos, sus roles ahora se muestran de forma estable.

Se revisaron servicios, decoradores, rutas manuales, GET/POST, CSRF y los accesos
de navegación. Las pruebas previas mantienen su cobertura de concurrencia real,
rollback, documentos históricos y compras cerradas.

## Correcciones realizadas

1. Los scripts locales ejecutaban makemigrations y cargar_datos al iniciar.
   Ahora solo instalan dependencias, aplican migraciones ya incluidas e inician
   Django. Trabajan desde la carpeta del script, evitando la confusión del directorio
   superior. El .bat detiene el arranque si fallan instalación o migraciones.
2. cargar_datos reasignaba grupos de usuarios existentes; ahora solo asigna
   grupos/sucursal a usuarios que acaba de crear. No cambia sus contraseñas.
   Se conserva para compatibilidad con las 105 pruebas anteriores; el comando
   recomendado para demostrar es el nuevo cargar_demo en una base separada.
3. El menú lateral acumuló opciones sin permitir desplazamiento vertical.
   Se agregó overflow y espacio flexible dentro de la barra lateral.
4. El rótulo de rol elegía arbitrariamente un grupo de un set. Ahora muestra los
   grupos en orden estable; no se modifican autorizaciones.
5. El README daba por existentes usuarios y claves de la demo antigua. Se
   reemplazó esa indicación por cuentas ficticias separadas y comandos inequívocos.

No se editaron modelos, servicios comerciales o migraciones para cambiar reglas.

## Hallazgo funcional que requiere decisión posterior

Pendiente de solicitud no equivale a pendiente de compra. Una compra habitual no
cambia solicitado, de acuerdo con la compatibilidad aprobada anteriormente. Por
eso, emitir nuevas solicitudes por un modelo puede consolidar también faltantes
reservados o cubiertos por compras habituales. La restricción de reservas impide
crear otra compra sobre ellos, pero la solicitud consolidada puede no ser utilizable
para una nueva compra de los pedidos libres restantes.

Se conserva la integridad (no hay doble compra), pero existe una fricción de uso.
Excluir necesidades con compra vigente al emitir/consolidar solicitudes sería un
cambio en la regla de selección y requiere autorización; no se aplicó en esta
etapa. La demo separa los modelos de los recorridos habitual/cotizaciones y la guía
explica qué cantidades consolida. No se presenta este punto como resuelto.

## Datos ficticios aislados

`config.demo_settings` utiliza demo.sqlite3 por defecto, con otra cookie de sesión
y CSRF. KAWA_DEMO_DB_PATH permite elegir otro archivo. Apuntar a db.sqlite3 se
rechaza. El comando cargar_demo requiere KAWA_DEMO y verifica la ruta de conexión.
Si la base ya tiene usuarios o datos comerciales sin la marca de la demo, se niega
a escribir. No limpia tablas, no fusiona con datos reales y no sobrescribe cuentas.

La carga completa es una transacción. Un fallo revierte todos los datos nuevos.
Se crea un marcador de versión al completarla; posteriores ejecuciones se limitan
a informar que ya está cargada, conservando cambios del usuario. Una demo marcada
incompleta se rechaza en lugar de intentar reconstruirla. Las claves de operación
son UUID deterministas del conjunto ficticio.

Contenido de una base nueva:

- Rosario, Mendoza y Córdoba; seis usuarios ficticios para todos los roles.
- Dos marcas, tres modelos y tres proveedores ficticios con dominios .invalid.
- Nueve registros de stock inicial, nueve ajustes y dos ventas.
- Pedidos, ocho solicitudes, cuatro ofertas: tres completas y una parcial.
- Ocho compras que cubren los siete estados; cinco documentos.
- Dos aprobaciones y un rechazo con motivo, más pedidos libres para presentar.

No se ejecuta cargar_demo desde ningún arranque. Se ejecutó manualmente dos veces
sobre demo.sqlite3 durante la validación. No se ejecutó sobre db.sqlite3, y todas
sus cuentas, contraseñas y registros permanecieron iguales a la instantánea inicial.

## Instalación y ejecución

Desde la carpeta kawa-django, en un entorno con Python:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Para usar una instalación habitual existente:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

Para la presentación, usar exclusivamente la configuración separada:

```powershell
.\.venv\Scripts\python.exe manage.py migrate --settings=config.demo_settings
.\.venv\Scripts\python.exe manage.py cargar_demo --settings=config.demo_settings
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8001 --settings=config.demo_settings
```

Las cuentas/contraseña de demo y el recorrido están en
[guia-demostracion-mvp.md](guia-demostracion-mvp.md). No utilizar esas credenciales
en datos reales. Para repetir desde cero se elige otro archivo vacío; el comando
no funciona como reinicio y nunca borra información.

## Pruebas y verificaciones reproducibles

```powershell
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py migrate --check
.\.venv\Scripts\python.exe manage.py check --deploy
```

SQLite, sin modificar datos:

```powershell
.\.venv\Scripts\python.exe manage.py shell -c "from django.db import connection; c=connection.cursor(); print(c.execute('PRAGMA integrity_check').fetchall()); print(c.execute('PRAGMA foreign_key_check').fetchall())"
```

Repetir con --settings=config.demo_settings para la base ficticia. Los resultados
esperados son ok y una lista vacía de infracciones de claves foráneas.

Las 12 pruebas nuevas cubren:

- A: login real, carga de stock, consulta por sucursal, venta, reenvío, insuficiencia
  y resumen; todas las peticiones de escritura verifican CSRF.
- B: pedido → proveedor habitual → compra → Nota → bandeja → aprobación e historial.
- C: pedido → solicitudes → ofertas completa/parcial → comparación → selección →
  Orden → rechazo, liberación de reserva y conservación de relaciones.
- Acceso por URL ajena, Administración sin Finanzas y rechazo de POST sin CSRF.
- Presentación estable de roles múltiples.
- Carga demo completa, repetición sin cambios, rechazo de base habitual,
  usuario/catálogo preexistente y bandera demo apuntando al archivo habitual.
- Rollback total de una carga fallida y preservación de cuentas en cargar_datos.

Los archivos temporales de las pruebas concurrentes y de migración son aislados.
No se alteraron pruebas anteriores para conseguir resultados positivos.

## Revisión visual y límites de la evidencia

Se intentó abrir una sesión de navegador para inspección visual. El navegador
integrado no está disponible y el inventario de navegadores conectados fue vacío.
No se utilizó la cuenta real ni se alteró su sesión. El servidor temporal de demo
se cerró al finalizar el intento.

Las plantillas y formularios están validados mediante respuestas HTTP, contenido
renderizado y recorridos con CSRF. El cambio CSS fue revisado en código; quedan
pendientes inspección visual, tamaños móviles y vista previa de impresión en un
navegador real. No se afirma validación visual completa ni pruebas de carga.
Los scripts locales se revisaron en código; no se reinstalaron dependencias ni
se ejecutó el script Unix desde Windows durante esta etapa.

## Seguridad y despliegue futuro

check --deploy informó seis advertencias con la configuración local actual:

| Código de Django | Advertencia |
| --- | --- |
| security.W004 | HSTS sin configurar |
| security.W008 | Redirección HTTPS sin configurar |
| security.W009 | Clave de desarrollo inadecuada para producción |
| security.W012 | Cookie de sesión sin Secure |
| security.W016 | Cookie CSRF sin Secure |
| security.W018 | DEBUG activo |

Antes de publicar se requiere una revisión autorizada de clave por entorno,
DEBUG/hosts/orígenes, HTTPS y cookies seguras. HSTS solo debe habilitarse después
de validar correctamente HTTPS. AUTH_PASSWORD_VALIDATORS está vacío; también
se debe definir una política de contraseñas para un despliegue real.

El Dockerfile preexistente no se modificó, conforme a la restricción de no cambiar
configuración de producción. Sigue ejecutando makemigrations y cargar_datos al
arrancar. Aunque el cargador antiguo ahora respeta cuentas existentes, puede
crear cuentas de ejemplo faltantes: no usar ese arranque con datos reales hasta
corregirlo con autorización. Además utiliza COPY . . y no hay un .dockerignore:
antes de construir una imagen deben excluirse bases habituales/de demo, entornos
virtuales y otros archivos locales que no correspondan al despliegue. No se construyó/ejecutó el contenedor ni se desplegó.

Para un futuro despliegue también deben revisarse persistencia y permisos del
archivo SQLite, copias de respaldo y restauración, collectstatic y la instalación
exacta de dependencias. SQLite serializa escritores: los reintentos y la carga
esperada deben evaluarse antes de uso concurrente más intenso. Esta etapa no
cambia la base de datos, el servidor de producción ni incorpora tecnologías.

## Coherencia académica

El repositorio contiene documentación técnica de etapas y wireframes, pero no el
catálogo RF numerado, especificaciones de casos de uso, diagramas UML originales,
matriz de permisos académica ni diagrama de estados fuente. Los adjuntos de las
etapas orientaron el alcance; no reemplazan esos documentos para una trazabilidad
formal. Se necesitan sus versiones y numeración para construir la matriz completa.
No se inventaron códigos ni se modificaron documentos académicos.

## Archivos de esta etapa

Nuevos: config/demo_settings.py, compras/management/commands/cargar_demo.py,
compras/test_integracion.py, docs/etapa5-integracion-validacion.md y
docs/guia-demostracion-mvp.md. demo.sqlite3 es un artefacto ficticio local ignorado.

Modificados: README.md, iniciar.bat, iniciar.sh, .gitignore,
compras/management/commands/cargar_datos.py, compras/context.py y
compras/static/compras/app.css.

No se modificaron requirements, modelos, migraciones, reglas de compra/venta,
config/settings.py o Dockerfile. La base habitual conserva sus registros.

## Estado final

MVP funcional para demostración local con datos ficticios y recorridos integrales
probados. Suite final: 117 pruebas aprobadas. La preparación para producción,
la revisión visual y la regla de selección de necesidades descrita arriba quedan
pendientes de la evidencia/autorización correspondiente. Etapa 5 finalizada;
no se inicia trabajo posterior sin autorización.
