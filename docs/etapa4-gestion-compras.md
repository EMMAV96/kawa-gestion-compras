# Etapa 4: Gestión de Compras y Aprobaciones

## Decisiones antes de implementar

- Se reserva cada ItemFaltante completo para una sola compra vigente, sin dividir
  cantidades entre compras. `solicitado` conserva su significado de la Etapa 3.
  Un rechazo libera la reserva pero conserva el origen y la compra histórica.
  Una aprobación mantiene la necesidad cubierta, sin aumentar existencias.
- El procedimiento habitual admite necesidades no reservadas aunque ya se hayan
  cotizado; no exige ofertas. Requiere proveedor habitual activo y precios acordados.
- El procedimiento B parte de una solicitud existente y sus pedidos originales.
  Si no hay respuesta se espera; si la respuesta existe se pasa a evaluación sin
  simular una espera. Se elige una única oferta completa para exactamente los
  mismos items de origen, modelos y cantidades. Una cesta igual para otros pedidos
  no constituye la misma necesidad.
- Se conservan los siete estados previstos. La selección registra la oferta y
  sus precios dentro de EN_EVALUACION; generar el documento avanza a
  DOCUMENTACION_PREPARADA. Se registra cada actividad y transición.
- Solo un usuario activo que pertenezca explícitamente al grupo Finanzas decide.
  Administrador y superusuario sin ese grupo no obtienen permiso implícito.
- Los documentos son HTML imprimibles, con numeración estable y copia comercial
  inmutable. No hay recepción, PDF, correos, compras parciales, cancelación de
  borradores o revisión de documentos en este alcance.
- No se encontró el diagrama académico original en el repositorio. Se utilizan
  los estados y recorridos del pedido adjunto, sin inventar códigos RF.


## Modelos y relaciones

- Compra: responsable, fecha, procedimiento, estado, proveedor y copia de su
  nombre/email. Se vincula opcionalmente con la solicitud y oferta seleccionada.
  Clave UUID única y parámetros normalizados reconocen reenvíos de creación.
  Una versión interna permite serializar las escrituras del servicio.
- OrigenCompra: compra, ItemFaltante y ListadoFaltantes originales protegidos,
  cantidad, sucursal y fecha de pedido históricas. Conserva la reserva vigente
  mediante un índice único parcial sobre el item; solo una compra puede cubrirlo.
- DetalleCompra: un registro por modelo, con nombre/marca históricos, cantidad y
  precios/importes DecimalField. En B los importes quedan pendientes hasta elegir
  una oferta. El total se calcula con Decimal, sin duplicar un saldo persistido.
- DocumentoCompra: relación uno a uno con Compra, tipo NOTA_PEDIDO u ORDEN_COMPRA,
  fecha local, número único y contenido JSON con valores comerciales copiados.
  Los importes se guardan como cadenas decimales dentro del documento histórico.
- DecisionFinanciera: una por compra, usuario, fecha, resultado y motivo. El rechazo
  exige motivo; aprobar permite agregar uno opcionalmente.
- MovimientoCompra: responsable, fecha, actividad y estados anterior/nuevo para
  seguir la preparación, evaluación, selección, documentación, envío y decisión.

Todas las relaciones documentales usan PROTECT. Los modelos de esta etapa son
solo lectura en el admin nativo: las operaciones se realizan mediante servicios.

## Procedimientos y estados

| Procedimiento | Estado de origen | Actividad | Estado de destino |
| --- | --- | --- | --- |
| A | Sin compra | Preparar proveedor habitual, pedidos y precios | EN_PREPARACION |
| A | EN_PREPARACION | Generar Nota de Pedido | DOCUMENTACION_PREPARADA |
| B | Sin compra | Preparar desde solicitud existente | EN_PREPARACION |
| B | EN_PREPARACION | Consultar respuestas, todavía no hay ofertas | PENDIENTE_COTIZACIONES |
| B | EN_PREPARACION o PENDIENTE_COTIZACIONES | Consultar respuestas ya recibidas | EN_EVALUACION |
| B | EN_EVALUACION | Seleccionar una oferta completa y compatible | EN_EVALUACION |
| B | EN_EVALUACION con oferta elegida | Generar Orden de Compra | DOCUMENTACION_PREPARADA |
| Ambos | DOCUMENTACION_PREPARADA | Solicitar aprobación | PENDIENTE_APROBACION |
| Ambos | PENDIENTE_APROBACION | Finanzas aprueba | APROBADA |
| Ambos | PENDIENTE_APROBACION | Finanzas rechaza con motivo | RECHAZADA |

Las respuestas se registran con las pantallas existentes de la Etapa 3. Desde el
detalle de compra se consulta su disponibilidad para actualizar la evaluación;
no se emiten solicitudes artificiales ni se cambia el estado al abrir un GET.
Una respuesta parcial permite evaluar, pero no seleccionarla para documentar.

Las ofertas de otros proveedores pueden elegirse cuando corresponden exactamente
a los mismos items de origen y a la misma cesta. Igualar solo modelos y cantidades
de pedidos diferentes no alcanza. La selección comprueba también que todos los
 detalles cotizados pertenecen a la solicitud declarada y sus importes coinciden.
Una vez elegida, no se reemplaza la oferta dentro de la misma compra.

## Permisos y garantías

Compras y Administrador conservan las facultades de preparación/consulta del
módulo operativo. Finanzas consulta compras y documentos, tiene bandeja e historial
y decide. Ventas no accede a compras. Usuarios sin rol tampoco acceden.

La pertenencia explícita a Finanzas se exige en cada POST de decisión y en el
servicio. Un superusuario sin ese grupo tampoco puede decidir. Si un usuario tiene
Administrador y además Finanzas, puede decidir por esa pertenencia explícita.
No se implementa una regla adicional de separación de responsables que no fue
solicitada. Todas las decisiones quedan identificadas por usuario y fecha.

Las compras cerradas no tienen acciones de edición/transición. Reenviar la misma
creación o consultar nuevamente el documento existente devuelve la información
confirmada sin modificar la compra cerrada. Una segunda decisión se rechaza,
aunque repita el resultado anterior. La restricción uno a uno lo refuerza en base.

Cada operación que escribe es atómica. Las transiciones utilizan escrituras
condicionales sobre los estados válidos, sin depender de bloqueos de fila que
SQLite no implementa. La reserva está protegida adicionalmente por su índice
único parcial. Un error revierte compra, detalles, reservas y movimientos, o
la decisión completa según corresponda.

SQLite puede informar que la base está ocupada. El formulario de creación conserva
la clave y los datos para reintentar. Las acciones documentales/envío son repetibles
sin crear registros duplicados; una decisión ya registrada se informa como una
transición no permitida. No hay reintentos automáticos indefinidos.

Las compras rechazadas conservan documento, precios, decisión y orígenes. Sus
reservas se liberan y puede iniciarse otra operación con una nueva clave. Las
aprobadas mantienen la necesidad cubierta. No se altera el campo `solicitado`:
las consultas de pendientes de cotización y de pendientes de compra tienen
significados distintos y sus pantallas los separan.

## Documentos

Los números son NP-<id de compra de ocho dígitos> y OC-<id de compra de ocho dígitos>.
La numeración es única y estable, sin cálculo MAX+1. Puede tener saltos dentro de
cada tipo; no es un comprobante fiscal ni una numeración legal de facturación.

El documento copia proveedor, contacto, responsable, procedimiento, oferta,
modelos, cantidades, precios, total y pedidos de origen. No consulta nombres
actuales del catálogo para reconstruir su contenido. Puede imprimirse desde el
navegador. El documento emitido refleja su preparación; el estado financiero
actual se consulta por separado en la compra.

Todos los precios se expresan en ARS. Se mantienen los límites de la Etapa 3:
precio DecimalField(12,2) e importe por línea DecimalField(14,2), para conservar
centavos al leer valores grandes desde SQLite. No se aceptan valores negativos,
cero, NaN, infinitos ni precios con más de dos decimales.

## Pantallas y rutas

| Ruta | Función |
| --- | --- |
| /compras/ | Listado con filtro por estado |
| /compras/nueva/ | Elegir procedimiento, proveedor/pedidos o solicitud |
| /compras/<id>/ | Detalles, orígenes, oferta, estado e historial |
| /compras/<id>/accion/evaluar/ | POST: actualizar evaluación de respuestas |
| /compras/<id>/accion/seleccionar/ | POST: elegir oferta completa |
| /compras/<id>/accion/documentar/ | POST: emitir Nota u Orden |
| /compras/<id>/accion/solicitar/ | POST: enviar a Finanzas |
| /compras/<id>/documento/ | HTML imprimible del documento |
| /compras/<id>/decision/ | POST: aprobación o rechazo por Finanzas |
| /finanzas/pendientes/ | Bandeja de compras por decidir |
| /finanzas/decisiones/ | Historial de decisiones realizadas |

Los menús y accesos del panel respetan roles. La solicitud de cotización tiene un
acceso para preparar una compra desde ella. Ninguna restricción depende solamente
de ocultar un botón; los servicios vuelven a validar permisos y reglas.

## Recorrido de demostración

Antes de iniciar, usar los usuarios existentes de la base y asignar sus grupos
correctos. No se restablecen claves, no se crea admin01 ni se ejecuta cargar_datos
sobre los usuarios reales. Ventas debe tener una sucursal asignada.

### A: habitual

1. Ventas registra un pedido de faltantes en su sucursal.
2. Compras verifica un proveedor activo, habitual y con la marca correspondiente.
3. En Nueva compra elige HABITUAL, proveedor y necesidades sin reserva vigente.
   Completa un precio acordado por cada modelo; las cantidades se suman de los
   pedidos elegidos. Deja vacía la solicitud del procedimiento B.
4. Prepara, revisa los orígenes y genera la Nota de Pedido.
5. Consulta/imprime el documento y solicita aprobación financiera.
6. Finanzas abre su bandeja, revisa compra/documento y aprueba o rechaza con motivo.
7. Compras consulta el resultado y los movimientos. Stock conserva sus unidades.

### B: cotizaciones

1. Ventas registra otra necesidad sin reserva de compra.
2. Compras emite solicitudes y registra respuestas desde las pantallas de Etapa 3.
   Puede preparar la compra antes de recibirlas para demostrar la espera real.
3. En Nueva compra elige COTIZACION y la solicitud de origen; deja vacíos proveedor
   habitual, items manuales y precios. El sistema toma los pedidos de la solicitud.
4. En detalle pulsa Consultar respuestas e iniciar evaluación. Si faltan respuestas
   queda pendiente; luego de registrarlas, repite esa consulta para evaluar.
5. Elige una única oferta completa compatible. Genera la Orden de Compra y solicita
   aprobación. Si ya había ofertas, no se fuerza un estado de espera artificial.
6. Finanzas revisa el documento y registra la decisión. Una oferta parcial nunca
   habilita la Orden. Una segunda compra no puede reservar los mismos pedidos.

## Migración, ejecución y pruebas

Nueva migración: `0005_compra_decisionfinanciera_detallecompra_and_more`.
Solo agrega tablas, índices y restricciones; no cambia las migraciones 0001–0004.
Se aplicó a la base local con respaldo previo en el directorio temporal del sistema.
Se compararon todos los registros anteriores: ninguno se eliminó ni modificó.
También se verificaron hashes de migraciones anteriores, claves foráneas e integridad
SQLite. No se cargaron operaciones comerciales ficticias en la base real.

Desde kawa-django:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

Verificación:

```powershell
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py showmigrations compras
```

Se mantienen las 67 pruebas existentes. Se agregan 38 pruebas de compras: recorridos
A/B, permisos, proveedores, precios, ofertas incompletas o incompatibles, transiciones,
documentos, numeración, historial, rechazos, inmutabilidad, rollback y stock intacto.
Dos verificaciones usan procesos y archivos SQLite temporales: migración desde 0004,
y competencia real por reservas, claves de creación, documentos y decisiones.

## Archivos de la etapa

Nuevos:

- compras/servicios_compras.py
- compras/forms_compras.py
- compras/views_compras.py
- compras/test_compras.py
- compras/migrations/0005_compra_decisionfinanciera_detallecompra_and_more.py
- compras/templates/compras/lista.html, nueva.html, detalle.html, documento.html,
  bandeja.html y decisiones.html
- docs/etapa4-gestion-compras.md

Modificados:

- compras/models.py, urls.py, admin.py y context.py
- compras/templates/base.html y panel.html
- compras/templates/cotizaciones/solicitud_detalle.html
- README.md
- db.sqlite3: aplicación de 0005, sin alterar datos comerciales anteriores

## Limitaciones

No hay recepción, incremento de stock por aprobación, logística, PDF, correo,
facturación, compras parciales, cancelación de borradores, edición posterior de
precios/documentos ni sustitución de ofertas seleccionadas. Un rechazo permite
preparar una nueva operación conservando la anterior. Un borrador mantiene sus
reservas; esta versión no añade una cancelación con estados fuera del alcance.
El formulario habitual presenta ocho filas de precios, como los formularios
existentes. La documentación académica original y el diagrama de estados siguen
pendientes: no se afirma correspondencia con códigos RF.

La Etapa 5 no se inicia y no se realizaron commit ni push.


## Resultado final

- Suite completa: 105 pruebas aprobadas (67 anteriores y 38 nuevas).
- Django check: sin problemas.
- Makemigrations --check --dry-run: sin cambios pendientes.
- Migración 0005 aplicada; migraciones anteriores intactas.
- Comparación del respaldo: datos anteriores preservados.
- SQLite integrity_check y foreign_key_check: correctos.
