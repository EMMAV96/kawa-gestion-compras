# Modernización frontend UX/UI de KAWA S.R.L.

## Alcance y auditoría inicial

Se revisaron base.html, app.css, las 34 plantillas operativas anteriores, sus
formularios, navegación por grupos y documentos imprimibles. Las vistas, rutas,
formularios Python, servicios, permisos, modelos y migraciones no se modificaron.
Se mantienen HTML, CSS, JavaScript nativo y Django Templates, sin dependencias
nuevas, compilación, fuentes remotas, CDN o frameworks frontend.

El adjunto recibido menciona cuatro capturas, pero solo contiene Pasted text.txt.
No se dispuso de esas imágenes para una comparación visual directa.

Problemas encontrados en el código:

- Menú plano con demasiados enlaces y sin señal de página activa.
- En móvil, navegación horizontal extensa en vez de un panel lateral.
- Espaciados distintos entre pantallas añadidas en sucesivas etapas.
- Formularios as_p y formularios manuales con presentaciones diferentes.
- Controles de fecha sin el mismo estilo que los demás inputs.
- Colores claros hardcodeados en tarjetas, tablas, login y documentos.
- Documentos con CSS propio duplicado e independiente del resto del sistema.
- Accesos del panel distribuidos de forma desigual entre roles.
- Iconos con abreviaturas distintas, sin un lenguaje gráfico compartido.

## Componentes reutilizables

En compras/templates/components:

| Parcial | Responsabilidad |
| --- | --- |
| sidebar.html | Secciones, permisos de visibilidad y grupo de la ruta actual |
| nav_link.html | Enlace reutilizable con aria-current y estado activo |
| navbar.html | Menú responsive, tema y perfil |
| theme_toggle.html | Botón de tema en aplicación, login y documentos |
| messages.html | Notificaciones, estados y roles accesibles |
| quick_card.html | Accesos rápidos por rol |
| form_fields.html | Etiquetas, ayudas, campos ocultos, obligatorios y errores |
| icons.html / icon.html | Símbolos SVG locales reutilizables, decorativos |

base.html compone la estructura. El panel se reorganiza sin indicadores nuevos
ni consultas estadísticas. Los formularios conservan nombres, métodos, CSRF,
valores, validaciones y acciones existentes. Las tablas mantienen sus columnas
y solo cambian su presentación; se agregan etiquetas ocultas para controles de
filas y regiones desplazables enfocables.

Se reutilizan las clases existentes (tarjeta, tabla, form-card, acciones, badge,
quick-card, stats-grid, etc.) para modernizar las pantallas sin reescribir su lógica.
Los indicadores administrativos existentes se conservan con su contexto original.

## Sidebar

| Sección | Opciones |
| --- | --- |
| Inicio | Panel principal |
| Ventas | Registrar venta, consultar ventas, resumen quincenal |
| Inventario | Consultar stock, cargar/ajustar |
| Pedidos | Registrar faltantes, consultar pedidos, consolidación |
| Proveedores y cotizaciones | Proveedores, solicitudes, recibidas y comparación |
| Compras | Nueva compra, operaciones |
| Finanzas | Pendientes, historial de decisiones |
| Administración | Dashboard, usuarios, catálogo, operaciones |

Cada grupo usa details/summary nativos: Enter/Espacio permiten expandir y contraer.
SVG discretos acompañan los títulos; una flecha indica la expansión. La ruta
actual determina en servidor el grupo abierto y el enlace resaltado con
aria-current. Los grupos pueden cerrarse manualmente; al entrar a otra página,
el correspondiente a ella vuelve a abrirse. Las demás preferencias se recuerdan
con kawa.nav.groups en localStorage, cuando esté disponible.

La visibilidad utiliza los mismos roles y finanzas_autorizado existentes. Ventas
no ve compras; Finanzas no ve preparación ni ajustes; Administrador no recibe
bandeja financiera por el rediseño. No se reemplazan las comprobaciones backend.

Cotizaciones recibidas apunta a /cotizaciones/#cotizaciones-recibidas, una sección
que utiliza las respuestas ya cargadas junto con las solicitudes. No se creó una
ruta ni una consulta de negocio. JavaScript ajusta el enlace activo al cambiar el
fragmento; el detalle de una oferta también activa ese acceso.

En escritorio, el botón superior alterna el sidebar completo y un riel compacto.
Al elegir un grupo en el riel se expande para mostrar sus enlaces. En ambos casos
hay desplazamiento interno y el contenido aprovecha el espacio restante. La
preferencia se guarda en kawa.sidebar.collapsed.

## Temas claro y oscuro

app.css define colores semánticos y variables de tipografía, espaciado, radios,
bordes y sombras. El oscuro usa una paleta propia de verdes y neutros, sin invertir
la pantalla. Incluye inputs, fechas, selects, formularios, tablas, mensajes, login,
sidebar, topbar, tarjetas y documentos.

- theme-init.js es síncrono y se carga antes de la hoja CSS. Lee kawa.theme y
  resuelve el tema antes de dibujar para evitar el destello de un tema incorrecto.
- Sin preferencia explícita usa prefers-color-scheme. Un cambio del sistema se
  refleja mientras no haya una elección explícita del usuario.
- El botón cambia el tema, su nombre accesible y aria-pressed, y guarda la elección.
- El evento storage sincroniza cambios entre pestañas del mismo origen.
- Si localStorage está bloqueado, la interfaz sigue funcionando; la elección
  puede mantenerse solo durante esa página. No se almacena nada en SQLite.

Login y documentos comparten los mismos recursos. En impresión se fuerzan fondo
blanco y texto oscuro, se ocultan controles y se mantienen encabezados de tablas.
No cambian número, fecha o contenido histórico del documento.

## Responsive y accesibilidad

Breakpoints principales:

- Desde 1024 px: sidebar lateral completo o compacto.
- Hasta 1023 px: panel lateral oculto inicialmente con JavaScript, backdrop y
  control superior. Aplica a tablet de 768 px y móviles.
- Hasta 600 px: tarjetas a una columna, controles y encabezados adaptados,
  login apilado y menores márgenes laterales.
- 1366, 1440 y 1920 px aprovechan un contenido flexible con máximo de 1456 px.
- 375 y 390 px mantienen formularios fluidos y tablas con scroll interno.

El panel móvil cierra con botón, fondo, enlace o Escape. Mientras está abierto,
la zona principal queda inert, Tab permanece en el panel y el cierre devuelve
el foco al botón. Un cambio a escritorio quita el modo modal. Sin JavaScript,
los grupos nativos y enlaces siguen disponibles; el sidebar móvil se presenta
estático y los controles dependientes de JS se ocultan.

Se incluyen enlace Saltar al contenido, foco visible, botones con nombres,
iconos decorativos ocultos a lectores, estados con texto y errores visibles.
Los controles táctiles principales tienen al menos 44 px en tablet/móvil.
Las tablas tienen desplazamiento horizontal controlado y reciben un nombre
accesible y foco mediante JS. No se ocultan columnas para adaptar el ancho.
Se respeta prefers-reduced-motion.

Se calcularon los contrastes de ocho pares de colores básicos: todos superan
4.5:1. Ejemplos: texto claro 14.36:1, secundario claro 5.46:1, botón claro 6.92:1,
texto oscuro 13.49:1 y botón oscuro 9.18:1. Esto no equivale a una auditoría global
WCAG ni sustituye una revisión visual con contenido real.

## Pruebas y conservación

- Suite previa: 117 pruebas aprobadas antes de intervenir.
- Suite con rediseño: 126 pruebas aprobadas (117 conservadas y 9 nuevas).
- Regresión adicional de frontend/integración: 21 pruebas aprobadas.
- Django check: sin problemas.
- makemigrations --check --dry-run: sin cambios pendientes.
- node --check para app.js y theme-init.js: sintaxis válida. Node se usó como
  herramienta ya instalada de verificación, no como dependencia o build del proyecto.

Las nueve pruebas nuevas en test_frontend.py verifican navegación por rol y sus
URLs, enlace actual único, grupo abierto, respuestas recibidas, recursos de tema,
CSRF, etiquetas/errores de formularios, pantallas operativas/administrativas,
login, documentos y ausencia de estadísticas nuevas. Las pruebas anteriores
siguen validando login/logout, operaciones, formularios, permisos y finanzas.

Se registraron hashes antes y después. Backend, formularios Python, permisos,
rutas, migraciones y db.sqlite3 permanecen idénticos. No se ejecutó ningún cargador
ni operación comercial sobre las bases reales o de demo.

El hash de demo.sqlite3 cambió durante la intervención; la base muestra un inicio
de sesión reciente y conserva sus conteos: 6 usuarios, 2 ventas, 8 compras y 3
decisiones. No se atribuye sin evidencia cada cambio de bytes ni se restauró una
versión anterior. Su integridad SQLite es correcta. Las pruebas de renderizado
utilizan sus propios datos ficticios en una base de test aislada.

## Comprobación manual en Chrome

No hay navegador automatizado conectado (inventario vacío). No se afirma haber
verificado visualmente tamaños, interacciones JS, colores renderizados o impresión.
Esta lista debe completarse en un navegador real.

1. Desde kawa-django iniciar la demo existente, sin volver a cargar ni reiniciar datos:

```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8001 --settings=config.demo_settings
```

2. Abrir http://127.0.0.1:8001/. Si los estilos están cacheados, recargar con
   Ctrl+Shift+R. Con estáticos recopilados, será necesario actualizar collectstatic
   en el entorno correspondiente; esta tarea no cambió configuración de producción.
3. En DevTools → Device Toolbar, probar 1920, 1440, 1366, 768, 390 y 375 px de ancho,
   con una altura normal de notebook/móvil. Repetir claro y oscuro.
4. Revisar en cada tamaño: login, panel, stock, ajuste, nueva venta/listado/detalle/
   resumen, pedidos nuevos/listado/detalle/consolidación, proveedores alta/edición,
   solicitudes nueva/listado/detalle, respuesta, oferta y comparación, compras
   nueva/listado/detalle, bandeja/historial y administración completa.
5. Confirmar que no haya scroll horizontal de toda la página, superposiciones o
   barra superior cortada. Las tablas deben poder desplazarse internamente sin
   perder columnas, controles ni acciones.
6. En escritorio, contraer y expandir el sidebar, seleccionar un grupo del riel,
   desplazarse por el menú y recargar. Debe mantenerse el modo elegido y abrirse
   el grupo de la página actual.
7. En móvil/tablet, abrir menú, navegar por Tab y Shift+Tab, cerrar con Escape,
   botón, fondo y enlace. Confirmar retorno de foco y bloqueo temporal del fondo.
8. Con distintas cuentas demo, revisar que aparezcan solo sus opciones. No enviar
   decisiones ni operaciones únicamente para probar un color; usar las pruebas
   automatizadas para comprobar negocio sin alterar la demo.
9. Cambiar tema desde login, aplicación y documento; recargar y abrir otra pestaña.
   Debe conservarse. Para comprobar preferencia del sistema, eliminar únicamente
   kawa.theme del almacenamiento local en DevTools y emular prefers-color-scheme.
10. Comprobar foco visible, nombres accesibles, etiquetas, ayudas, errores, controles
    de fecha, selects y checkboxes. En DevTools emular movimiento reducido.
11. En un documento ya existente abrir vista previa de impresión: fondo blanco,
    todos los renglones visibles, encabezados repetibles y controles ocultos.
12. Revisar consola por errores JS y red por archivos estáticos 404. Probar también
    con localStorage bloqueado y con JS desactivado para el modo degradado.

## Archivos intervenidos

Nuevos: components/sidebar.html, nav_link.html, navbar.html, theme_toggle.html,
messages.html, quick_card.html, form_fields.html, icons.html e icon.html dentro de
compras/templates; compras/static/compras/theme-init.js y app.js;
compras/test_frontend.py; docs/rediseño-frontend-ux-ui.md.

Actualizados: app.css, base.html, panel.html, registration/login.html,
compras/documento.html, cotizaciones/lista.html y las plantillas operativas que
consumen form.as_p o formularios manuales administrativos, controles de filas,
estados e iconos. Se mantiene el contenido y la funcionalidad de cada formulario.
README agrega únicamente el enlace a esta documentación.

No se realizaron commit ni push. Pendientes: capturas de referencia no recibidas,
revisión visual en Chrome y comprobación de interacciones/impresión en las seis
resoluciones indicadas. La intervención se detiene para revisión del usuario.
