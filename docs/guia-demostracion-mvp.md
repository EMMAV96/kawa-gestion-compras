# Guía de demostración del MVP KAWA S.R.L.

## Preparación

Para una base nueva, configurar primero `KAWA_LOCAL_DEMO_PASSWORD` con una clave
privada exclusiva de al menos 12 caracteres. Ver el procedimiento de entrada
segura en [despliegue-gratuito.md](despliegue-gratuito.md). Las cuentas existentes
conservan su contraseña.


Trabajar exclusivamente con una base ficticia. Desde `kawa-django`:

```powershell
.\.venv\Scripts\python.exe manage.py migrate --settings=config.demo_settings
.\.venv\Scripts\python.exe manage.py cargar_demo --settings=config.demo_settings
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8001 --settings=config.demo_settings
```

Abrir http://127.0.0.1:8001/. Todas las cuentas de esta guía son ficticias y usan
la clave privada configurada mediante `KAWA_LOCAL_DEMO_PASSWORD` al inicializarlas; no hay una clave predeterminada publicada:

| Cuenta | Uso |
| --- | --- |
| demo_admin | Usuarios, catálogos y ajustes de stock |
| demo_ventas_rosario | Operaciones de Ventas en Rosario |
| demo_ventas_mendoza | Operaciones de Ventas en Mendoza |
| demo_ventas_cordoba | Operaciones de Ventas en Córdoba |
| demo_compras | Proveedores, solicitudes, ofertas y compras |
| demo_finanzas | Bandeja, documentos y decisiones financieras |

Cerrar sesión antes de cambiar de cuenta. Para sesiones simultáneas usar perfiles
o navegadores separados; dos pestañas del mismo navegador comparten la sesión.
La demo usa nombres de cookies propios para no reutilizar la sesión de la base
habitual. No usar usuarios reales en esta demostración.

La carga inicial incluye tres sucursales, dos marcas ficticias, tres modelos,
nueve existencias iniciales, dos ventas, proveedores habituales y no habituales,
ofertas completas/parciales y ocho compras en todos los estados previstos.
Hay un pedido libre de Urbana 125 por dos unidades en Rosario y otro de Ruta 250
por cuatro en Mendoza. También hay una compra rechazada cuya reserva se liberó.

La demo ya contiene ejemplos históricos. Los recorridos siguientes generan nuevas
operaciones ficticias para mostrar cómo se trabaja, sin borrar esos ejemplos.
Anotar los números de pedido, compra y documento que muestre cada recorrido.

## Escenario A — Stock y Ventas

1. Ingresar como **demo_admin**. En Stock consultar Rosario y anotar la existencia
   de **Aurora Urbana 125**. Inicialmente es 10 por una venta precargada.
2. En Cargar o ajustar stock agregar **5** unidades a ese modelo en Rosario, con
   motivo «Ejemplo ficticio de demostración». Volver a Stock: debe aumentar en 5.
3. Cerrar sesión e ingresar como **demo_ventas_rosario**. Consultar Stock: solo
   aparecen registros de Rosario. No puede elegir Mendoza o Córdoba.
4. En Registrar venta elegir Aurora Urbana 125, cantidad **2**, y confirmar.
   La sucursal se asigna automáticamente. Anotar el número de venta y comprobar
   el detalle con dos unidades. Se descuentan exactamente dos existencias.
5. En Resumen quincenal elegir una fecha de la quincena actual. Se suman las dos
   unidades nuevas a las ventas precargadas; no se reemplaza el historial.
6. Para mostrar un reenvío, volver al formulario ya enviado con Atrás y reenviarlo
   con los mismos datos y la misma clave oculta. Debe volver a la misma venta y
   conservar el stock. Si el navegador impide reenviar formularios, esta garantía
   está comprobada por la prueba HTTP y concurrente; abrir un formulario nuevo
   crea intencionalmente otra operación y no sirve para demostrar duplicados.
7. Intentar una venta por **9999** unidades: aparece Stock insuficiente. No cambia
   la existencia ni se agrega otra venta.

## Escenario B — Compra a proveedor habitual

1. Como **demo_ventas_rosario**, registrar un pedido de Aurora Urbana 125 por
   **2** unidades. Anotar su número. La sucursal y el responsable quedan asignados.
2. Como **demo_compras**, abrir Pedidos de faltantes y consultar ese detalle.
   Aplicar filtros de sucursal y quincena para mostrar la consolidación.
3. En Proveedores verificar **Distribuidora Ejemplo Habitual**, activo, habitual
   y con las marcas que abastece.
4. En Operaciones de compra → Nueva compra elegir **Proveedor habitual**.
   Seleccionar ese proveedor y únicamente la necesidad del pedido recién creado.
   En precios, elegir Aurora Urbana 125 y precio **1500000.25**. Dejar vacía la
   solicitud del procedimiento B y las demás filas de precio.
5. Preparar la operación. Anotar su número. Revisar cantidad, total, sucursal y
   pedido de origen. Estado: En preparación. La necesidad queda reservada.
6. Generar documentación: se obtiene una **Nota de Pedido**, con número NP único.
   Abrir el documento e imprimirlo desde el navegador si se desea. Estado:
   Documentación preparada.
7. Solicitar aprobación financiera. Estado: Pendiente de aprobación.
8. Como **demo_finanzas**, abrir Aprobaciones pendientes. Elegir la compra recién
   creada, no otra precargada. Consultar su documento y anotar el stock actual.
9. Aprobar. Se registra usuario, fecha y resultado; desaparece de la bandeja y
   aparece en Decisiones financieras. El stock debe ser exactamente el mismo.
10. Como Compras, consultar la compra cerrada y su historial. Ya no hay acciones
    para cambiar precios, oferta, documento o resultado. Una segunda decisión se
    rechaza desde el backend.

Puede demostrarse el rechazo con otra compra o usar el ejemplo ya precargado:
su motivo queda visible y su necesidad vuelve a estar disponible, sin borrar
la operación rechazada. La Nota de Pedido no exige una cotización.

## Escenario C — Compra mediante cotizaciones

1. Como **demo_ventas_mendoza**, registrar un pedido de **Aurora Ruta 250**, dos
   unidades. Anotar su número.
2. Como **demo_compras**, abrir Solicitudes y cotizaciones → Nueva solicitud.
   Opcionalmente filtrar por una fecha de la quincena actual y actualizar pendientes.
3. Elegir Aurora Ruta 250 y los proveedores **Mayorista Ejemplo Norte** y
   **Mayorista Ejemplo Sur**, medio Mail. Generar solicitudes. Se registran en el
   sistema, sin enviar correos externos.
4. Abrir el detalle de ambas solicitudes y anotar la cantidad consolidada **Q**.
   En una demo recién cargada existe además un pedido libre por cuatro unidades:
   por eso Q puede ser **6**, no únicamente las dos recién registradas. Los pedidos
   ya solicitados se excluyen, aunque su compra esté esperando respuestas.
5. En la solicitud Norte, registrar una cotización con cantidad **Q**, precio
   **2100000.50** y fecha actual: es completa. En Sur usar cantidad **Q−1**, precio
   **1900000.00**: es incompleta. Para varios modelos se pueden omitir filas dejando
   cantidad y precio vacíos. No se admite superar la cantidad solicitada.
6. Abrir Comparar cotizaciones. Las dos ofertas aparecen en la misma cesta de
   modelos/cantidades. La parcial muestra un subtotal: su menor importe no se
   presenta como una oferta completa más económica.
7. Desde el detalle de la solicitud Norte elegir Preparar compra, o abrir Nueva
   compra → Mediante cotizaciones y seleccionar esa solicitud. Dejar vacíos el
   proveedor habitual, los pedidos manuales y los precios del procedimiento A.
8. En el detalle consultar respuestas e iniciar evaluación. Como ya existen
   ofertas, pasa a En evaluación sin simular una espera. Elegir la oferta Norte,
   que es completa y corresponde a los mismos pedidos de origen.
9. Generar la **Orden de Compra**, revisar su número OC, precios, total y pedidos.
   Solicitar aprobación financiera.
10. Como **demo_finanzas**, abrir esa compra y **rechazarla** con motivo «Ejemplo
    ficticio: presupuesto insuficiente». La decisión aparece en el historial; las
    reservas se liberan, pero el pedido, las solicitudes, ofertas y documento se
    conservan. El stock no cambia.

Para demostrar la espera real, abrir la compra precargada en Pendiente de
cotizaciones, registrar una respuesta a una de sus solicitudes y volver a
consultar respuestas en el detalle de la compra.

## Comprobaciones de permisos

- Ventas no puede abrir Operaciones de compra ni pedidos de otra sucursal aunque
  escriba sus URLs manualmente. Las consultas de detalle ajeno devuelven 404.
- Compras consulta pedidos de Rosario, Mendoza y Córdoba, pero no puede decidir.
- Administrador puede cargar existencias y administrar usuarios; sin Finanzas
  no puede abrir la bandeja financiera ni aprobar o rechazar.
- Solo demo_finanzas tiene el grupo Finanzas en la carga inicial. Un superusuario
  tampoco decide si no pertenece explícitamente a ese grupo.

## Repetición y recuperación de la demo

`cargar_demo` no es un botón de reinicio. Repetirlo conserva cambios, claves,
operaciones y usuarios posteriores. Si se necesita repetir desde cero, detener
el servidor y elegir **otro archivo que todavía no exista**, sin borrar bases:

```powershell
$env:KAWA_DEMO_DB_PATH = Join-Path $PWD "otra-demo.sqlite3"
.\.venv\Scripts\python.exe manage.py migrate --settings=config.demo_settings
.\.venv\Scripts\python.exe manage.py cargar_demo --settings=config.demo_settings
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8001 --settings=config.demo_settings
```

No elegir db.sqlite3 ni una base con información existente. Para volver al archivo
demo predeterminado, cerrar el servidor y quitar solo la variable del proceso:

```powershell
Remove-Item Env:KAWA_DEMO_DB_PATH -ErrorAction SilentlyContinue
```

Esto no elimina archivos ni datos. La trazabilidad académica completa requiere
los documentos RF y diagramas originales; esta guía demuestra los recorridos
implementados sin asignarles códigos inventados.
