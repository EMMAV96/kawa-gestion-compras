# Etapa 3: Pedidos, proveedores y cotizaciones

## Alcance y decisiones funcionales

Se conservan Python, Django, SQLite, Templates, HTML/CSS y la aplicación compras.
No se modifican Stock/Ventas, sus pruebas o sus migraciones. No se implementan
adjudicaciones, compras, documentos de compra ni aprobaciones financieras.

- ListadoFaltantes e ItemFaltante continúan representando los pedidos.
  `solicitado` sigue significando incluido en una solicitud; no significa comprado.
- Ventas registra automáticamente en su sucursal asignada. El selector está
  deshabilitado; los valores enviados por el navegador no alteran la sucursal.
  Consulta todos los pedidos de su sucursal. Sin asignación no puede registrar.
- Compras y Administrador consultan todas las sucursales. Finanzas conserva
  sus permisos anteriores y no accede a estos módulos.
- Los filtros por fecha exacta y quincena se combinan por intersección. La fecha
  de quincena representa los días 1–15 o 16–fin de mes, incluidos ambos límites.
  Sin fecha se consultan todos los períodos. Pendiente significa pendiente de
  solicitud; un pedido puede tener algunas líneas solicitadas y otras pendientes.
- Cada proveedor elegido debe estar activo y abastecer todas las marcas de la
  solicitud. Se conserva `es_fijo` como identificación de proveedor habitual.
  La baja posterior no borra documentos ni impide registrar una respuesta a una
  solicitud ya emitida.
- Una solicitud admite una cotización recibida inmutable, completa o parcial.
  Cada línea debe pertenecer a esa solicitud, con cantidad positiva no superior
  a la solicitada y precio positivo. Omitir un modelo o cotizar menos unidades
  produce una oferta incompleta. No hay revisiones de ofertas en esta etapa.
- Los precios se expresan en pesos argentinos (ARS), sin conversión de moneda,
  impuestos, descuentos ni vencimientos. La fecha de respuesta debe estar entre
  la emisión y el día actual. Las solicitudes nuevas usan el calendario local
  configurado en Django, también cuando el servidor utiliza UTC.
- No se ordenan ofertas incompletas por total junto con las completas. Cada grupo
  de comparación tiene exactamente los mismos identificadores de modelo y
  cantidades solicitadas. Puede filtrarse por la cesta de una solicitud.
  Diferencias de fechas, condiciones comerciales o proveedores siguen requiriendo
  evaluación humana; el sistema no elige un ganador.

## Modelos y relaciones

- EmisionSolicitud: usuario, fecha, clave UUID única y parámetros normalizados.
  Agrupa las solicitudes de una emisión y permite reconocer reenvíos.
- SolicitudCotizacion: mantiene proveedor e items originales. Agrega emisión
  opcional y copia del nombre/email del proveedor. Una emisión tiene como máximo
  una solicitud por proveedor. El seguimiento se deriva de la existencia de una
  cotización recibida, sin redefinir el estado histórico ENVIADA.
- DetalleSolicitudCotizacion: solicitud, modelo protegido, cantidad y copias de
  nombre de modelo/marca; un modelo por solicitud. Es la fuente histórica para
  consultar cantidades, registrar ofertas y comparar.
- Cotizacion: una por solicitud, usuario responsable, fecha y fecha de registro.
  El proveedor se obtiene de la solicitud; no se duplica una relación que pudiera
  contradecirla. Total y condición completa se calculan a partir de los detalles.
- DetalleCotizacion: cotización, detalle de solicitud, cantidad, precio unitario
  DecimalField(12,2) e importe DecimalField(14,2). Un detalle por cotización.

El servicio calcula los importes con Decimal y suma los totales en Python.
El límite de importe por línea es ARS 999.999.999.999,99: evita pérdida de
centavos con la conversión NUMERIC de SQLite. No se redondean silenciosamente
precios con más de dos decimales ni se aceptan NaN o infinitos.

## Compatibilidad e historial

La migración 0003 agrega estructuras, restricciones y los campos históricos.
La migración 0004 copia los datos disponibles de las solicitudes anteriores,
consolidando las cantidades de los items por modelo. No cambia `solicitado`,
los vínculos originales, fechas, usuarios, stock o ventas. Emisiones antiguas
quedan sin EmisionSolicitud porque no puede reconstruirse su agrupación real.

No puede recuperarse información anterior a modificaciones ya ocurridas antes
 de esta migración. Se preservan cantidades históricas cero, permitidas por el
modelo original; las emisiones nuevas exigen cantidades positivas. Una solicitud
antigua sin detalle o con cantidades cero puede no admitir una oferta completa y
requiere revisión de origen, sin inventar datos ni borrar registros.

Nombres y cantidades mostrados en solicitudes y ofertas provienen de las copias,
no de los faltantes o catálogos que puedan modificarse después. Las solicitudes,
emisiones y cotizaciones son de solo lectura en el admin nativo.

`crear_listado` se conserva como función interna de persistencia compatible con
fixtures/cargas existentes. No autoriza operaciones de usuario: todas las rutas
usan `registrar_pedido`, que valida permisos, sucursal y cantidades. El helper
antiguo `consolidar` sigue disponible para compatibilidad; las consultas de usuarios
usan el nuevo servicio con autorización y filtros.

## Atomicidad y reenvíos

La emisión guarda su clave única, reclama condicionalmente todos los faltantes,
crea las solicitudes y sus detalles dentro de una transacción. Si falla un paso,
se revierten el marcado y todos los documentos. Otra clave no puede reclamar
faltantes ya solicitados. Un reenvío con la misma clave/usuario/parámetros devuelve
la emisión confirmada, aunque hayan aparecido nuevos pedidos después.

Los formularios nuevos incluyen UUID. Para compatibilidad con formularios antiguos
sin clave se utiliza una clave de sesión; para iniciar otra operación se abre un
formulario nuevo. La cotización es única por solicitud: reenviar exactamente la
misma respuesta devuelve la existente, y cambiar sus datos se rechaza.

SQLite puede devolver database is locked ante escritores concurrentes. La pantalla
conserva el formulario e informa que se reintente. Las pruebas utilizan conexiones
y archivos temporales reales, con reintentos acotados y transacciones nuevas.

## Pantallas y rutas

| Ruta | Función |
| --- | --- |
| /faltantes/ | Pedidos con filtros de sucursal, fecha, quincena y pendientes |
| /faltantes/nuevo/ | Registro por Ventas o Administrador |
| /faltantes/<id>/ | Detalle y seguimiento de líneas |
| /faltantes/consolidado/ | Cantidades por modelo con los mismos filtros |
| /proveedores/ | ABM y consulta existentes; habitual, marcas y estado |
| /cotizaciones/ | Solicitudes y seguimiento de respuestas |
| /cotizaciones/nueva/ | Pendientes, filtro quincenal y emisión por proveedor |
| /cotizaciones/solicitudes/<id>/ | Copia histórica de la solicitud |
| /cotizaciones/solicitudes/<id>/respuesta/ | Registro de cotización completa/parcial |
| /cotizaciones/recibidas/<id>/ | Detalle, importes y condición de oferta |
| /cotizaciones/comparar/ | Comparación por cesta de modelos/cantidades |

## Ejecución y recorrido de verificación

Desde kawa-django:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

1. Administrador asigna sucursal a los usuarios de Ventas desde Usuarios.
2. Ventas registra pedidos y verifica que solo consulta su sucursal.
3. Compras consulta pendientes y su consolidación quincenal.
4. Compras registra proveedores activos con las marcas correspondientes.
5. Desde Nueva solicitud filtra la quincena, actualiza pendientes y selecciona
   modelos/proveedores. Verifica los detalles históricos de cada solicitud.
6. Registra una cotización por solicitud; deja ambos campos vacíos para omitir
   un modelo. Consulta detalle y comparación de ofertas completas/parciales.

No se cargaron pedidos, ofertas ni usuarios ficticios en la base local durante
esta entrega. Las pruebas generan datos aislados. El comando de demo existente
puede usarse en una base de demostración, considerando las advertencias de Etapa 2.

## Pruebas y validación

```powershell
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py showmigrations compras
```

La suite tiene 67 pruebas: las 40 previas intactas y 27 nuevas. Cubren permisos,
sucursales, quincenas, proveedores activos y marcas, transacciones, duplicados,
historial, importes, validaciones, ofertas parciales, formularios y comparación.
Incluyen migración desde 0002 con solicitudes anteriores y concurrencia real
SQLite para emisiones con la misma/diferente clave y respuestas simultáneas.

Las migraciones 0003 y 0004 se aplicaron a la base local con respaldo previo.
Se verificó que todos los valores y registros anteriores se conservaran, que
0001/0002 mantuvieran sus hashes y que PRAGMA integrity_check y foreign_key_check
no indicaran problemas. Solo se agregaron tablas, campos y metadatos Django.

## Archivos de esta etapa

Nuevos:

- compras/servicios_pedidos.py
- compras/test_pedidos_cotizaciones.py
- compras/migrations/0003_solicitudcotizacion_proveedor_email_and_more.py
- compras/migrations/0004_preservar_solicitudes_existentes.py
- compras/templates/faltantes/detalle.html y consolidado.html
- compras/templates/cotizaciones/solicitud_detalle.html, recibida.html,
  oferta_detalle.html y comparar.html
- docs/etapa3-pedidos-proveedores.md

Modificados:

- compras/models.py, servicios.py, forms.py, views.py, urls.py y admin.py
- compras/templates/base.html
- compras/templates/faltantes/lista.html y nuevo.html
- compras/templates/cotizaciones/lista.html y nueva.html
- compras/templates/administracion/operaciones.html
- README.md
- db.sqlite3: aplicación de migraciones, sin pérdida de datos anteriores

No se realizaron commit ni push. La documentación académica RF/UML original
sigue pendiente; no se afirma correspondencia con códigos de requisitos.
La selección definitiva y la Gestión de Compras quedan para una Etapa 4 autorizada.
