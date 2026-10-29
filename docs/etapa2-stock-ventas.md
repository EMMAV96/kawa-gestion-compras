# Etapa 2: Stock y Ventas

## Alcance

Se conserva el monolito Django y la aplicacion `compras`, SQLite, ORM,
Templates y CSS existentes. No se modifican cotizaciones, compras ni
aprobaciones financieras. La migracion inicial permanece intacta.

## Modelos y relaciones

- UsuarioSucursal: un usuario tiene como maximo una sucursal asignada.
  Sucursal usa PROTECT; la asignacion se administra en Usuarios.
- Stock: sucursal y modelo protegidos, combinacion unica, cantidad >= 0.
- Venta: usuario, sucursal, fecha local y clave UUID unica de operacion.
- DetalleVenta: venta y modelo protegidos, cantidad > 0; un modelo por venta.
  Las filas repetidas se consolidan antes de guardar.
- AjusteStock: registra stock, responsable, fecha, variacion y motivo.
  Una variacion distinta de cero representa la carga inicial o un ajuste.

Migracion nueva: `0002_stock_ajustestock_usuariosucursal_venta_detalleventa_and_more`.
Solo agrega tablas y restricciones; no asigna sucursales arbitrarias a usuarios
existentes ni altera sus registros. No requiere reescribir `0001_initial`.

## Usuarios y permisos

El Administrador asigna sucursal desde Administracion > Usuarios > Editar.
La sucursal es obligatoria al guardar un usuario con rol Ventas. Usuarios
existentes sin asignacion no pueden registrar ventas hasta completarla.
No se cambia el modelo User ni los grupos actuales.

- Ventas: registra ventas para su sucursal automaticamente; consulta stock,
  ventas y resumen de esa sucursal, incluyendo operaciones de otros vendedores
  de la misma sucursal. No puede consultar detalles de otra sucursal.
- Compras y Finanzas: consultan todas las sucursales y filtran por sucursal.
  No registran ventas ni ajustan stock.
- Administrador: asigna usuarios, consulta todas las sucursales y carga/ajusta
  stock. El grupo Administrador no habilita registrar ventas.
- Un superusuario conserva su acceso privilegiado; para vender debe tener
  sucursal asignada. Usuarios sin rol no acceden a las consultas.

Se validan permisos en vistas y servicios. Los filtros de consulta tambien se
limitan en backend. Una sucursal ajena inyectada en un POST de venta se rechaza.
Los modelos operativos nuevos son de solo lectura en el admin nativo, para
impedir cambios de stock o ventas que omitan los servicios.

Los pedidos/faltantes conservan su comportamiento previo; su adecuacion de
permisos y sucursales corresponde a la Etapa 3.

## Pantallas

- `/stock/`: existencias y filtro por sucursal habilitada. Una combinacion no
  registrada representa disponibilidad cero.
- `/stock/ajuste/`: carga inicial y ajustes mediante variaciones con motivo.
- `/ventas/nueva/`: venta con una o varias filas, sin selector de sucursal.
- `/ventas/`: consulta por sucursal.
- `/ventas/<id>/`: responsable, fecha, sucursal y unidades por modelo.
- `/ventas/resumen/`: fecha de referencia y sucursal; unidades por modelo
  y sucursal. Primera quincena: 1-15; segunda: 16-fin de mes.

La fecha de venta se toma del servidor en America/Argentina/Buenos_Aires.
No hay ventas retroactivas, importes de venta, anulaciones ni edicion de ventas
confirmadas en esta etapa. El formulario conserva el esquema existente de ocho
filas; las filas vacias se ignoran.

## Atomicidad y SQLite

`registrar_venta` crea cabecera, descuenta existencias y crea detalles dentro
de una unica transaccion. Cada descuento usa UPDATE con condicion
`cantidad >= unidades` y expresiones F, sin depender de select_for_update.
Un error de cualquier linea revierte tambien las anteriores y la cabecera.

La clave UUID es unica en base. Reenviar el mismo formulario con el mismo
usuario, sucursal y cantidades devuelve la venta existente sin descontar otra
vez. Reutilizar una clave con datos diferentes se rechaza. Un formulario nuevo
tiene otra clave y representa una operacion nueva.

SQLite serializa escritores y puede devolver database is locked. La pantalla
informa que se reintente y conserva la clave y las filas. No hay reintentos
automaticos indefinidos ni descuentos parciales. La prueba de concurrencia usa
un archivo SQLite temporal, dos conexiones en hilos y reintentos acotados con
el mismo token: valida reenvios concurrentes y competencia por stock escaso.

Los ajustes usan variaciones atomicas, nunca reemplazan una cantidad leida
antes de una venta. Si el resultado fuera negativo, tampoco se guarda el ajuste.
Las compras no participan en este modulo ni aumentan el stock.

## Ejecucion en Windows

Desde `kawa-django`, con las dependencias instaladas:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

Si no existe el entorno:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
```

Para una base nueva de demostracion, ejecutar `manage.py cargar_datos` con el
mismo interprete. El comando conserva las cuentas de demo existentes y agrega
una asignacion Rosario para ventas01 solo si no tiene ninguna. Como antes,
reasigna sus grupos de demostracion: no usarlo para administrar usuarios reales.
En una base existente, asignar manualmente las sucursales desde Usuarios.

1. Ingresar como Administrador y asignar Rosario, Mendoza o Cordoba a Ventas.
2. Cargar unidades desde Cargar o ajustar stock, seleccionando sucursal/modelo.
3. Ingresar como Ventas, registrar una venta y comprobar el descuento.
4. Consultar detalle y resumen quincenal.

No ejecutar makemigrations al iniciar para esta etapa: aplicar la migracion
incluida. Los scripts de inicio y Docker preexistentes no se modifican aqui.

## Validacion

```powershell
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py showmigrations compras
```

Se conservan las 16 pruebas originales. `compras/test_stock_ventas.py` agrega
restricciones de base, servicios, formularios, vistas, permisos, aislamiento de
sucursales, reversion, idempotencia, limites quincenales y concurrencia SQLite.
La prueba concurrente migra una base temporal aislada y no escribe db.sqlite3.

La documentacion academica RF/UML original sigue pendiente; no se asignan
codigos de requisitos ni se afirma una trazabilidad aun no contrastada.


## Resultado de la entrega

- 40 pruebas aprobadas: las 16 existentes y 24 nuevas.
- Verificacion concurrente sobre archivo SQLite aprobada.
- `manage.py check`: sin problemas.
- `makemigrations --check --dry-run`: sin cambios pendientes.
- Migracion 0002 aplicada sobre la base local, con respaldo previo en temporal.
- Comparacion con el respaldo: todos los registros anteriores preservados;
  solo se agregaron metadatos Django y tablas nuevas.
- `PRAGMA integrity_check` y `foreign_key_check`: correctos.
- `0001_initial.py` permanece sin modificaciones.
