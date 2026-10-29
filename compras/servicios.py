from datetime import date
from calendar import monthrange
from collections import defaultdict
from uuid import UUID

from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models import F, Sum
from django.utils import timezone
from .models import Stock, Venta, DetalleVenta, AjusteStock, Modelo
from .permisos import exigir_rol, sucursal_ventas, sucursales_visibles


from .models import ItemFaltante, ListadoFaltantes, SolicitudCotizacion


def quincena(fecha: date) -> str:
    numero = "1.ª" if fecha.day <= 15 else "2.ª"
    return f"{numero} quincena {fecha:%m/%Y}"


@transaction.atomic
def crear_listado(sucursal, usuario, filas):
    """Persistencia interna para cargas existentes y fixtures, sin autorización.

    Las operaciones de usuarios deben pasar por registrar_pedido, que valida
    rol, sucursal y cantidades. Se conserva esta interfaz para compatibilidad.
    """
    hoy = timezone.localdate()
    listado = ListadoFaltantes.objects.create(
        sucursal=sucursal, usuario=usuario, fecha=hoy, quincena=quincena(hoy))
    ItemFaltante.objects.bulk_create([
        ItemFaltante(listado=listado, modelo=f["modelo"], cantidad=f["cantidad"],
                     motivo=f.get("motivo") or ItemFaltante.Motivo.VENTA)
        for f in filas
    ])
    return listado


def consolidar():
    """Faltantes pendientes de cotizar, sumados por modelo."""
    acumulado = {}
    pendientes = ItemFaltante.objects.filter(solicitado=False).select_related("modelo__marca")
    for item in pendientes:
        linea = acumulado.setdefault(item.modelo_id, {
            "modelo_id": item.modelo_id,
            "nombre": item.modelo.nombre,
            "marca": item.modelo.marca.nombre,
            "total": 0,
        })
        linea["total"] += item.cantidad
    return sorted(acumulado.values(), key=lambda l: l["nombre"])


def generar_solicitudes(modelos, proveedores, medio, *, usuario, clave_operacion, quincena=None):
    from .servicios_pedidos import emitir_solicitudes
    emision = emitir_solicitudes(usuario, modelos, proveedores, medio, clave_operacion, quincena)
    return emision.solicitudes.count()


# Stock y ventas: las escrituras condicionales funcionan también en SQLite,
# donde select_for_update no proporciona bloqueos de fila.


def _cantidad_entera(valor, positiva=True):
    if type(valor) is not int or (valor <= 0 if positiva else valor == 0):
        raise ValidationError("Ingrese una cantidad entera positiva." if positiva else "La variación debe ser un entero distinto de cero.")


@transaction.atomic
def ajustar_stock(usuario, sucursal, modelo, variacion, motivo):
    exigir_rol(usuario, "Administrador")
    _cantidad_entera(variacion, positiva=False)
    motivo = motivo.strip() if isinstance(motivo, str) else ""
    if not motivo or len(motivo) > 250:
        raise ValidationError("Indique un motivo de hasta 250 caracteres.")
    stock, _ = Stock.objects.get_or_create(sucursal=sucursal, modelo=modelo)
    actualizado = Stock.objects.filter(pk=stock.pk, cantidad__gte=max(0, -variacion)).update(
        cantidad=F("cantidad") + variacion)
    if not actualizado:
        raise ValidationError("El ajuste dejaría el stock negativo.")
    AjusteStock.objects.create(stock=stock, usuario=usuario, variacion=variacion, motivo=motivo)
    stock.refresh_from_db()
    return stock


@transaction.atomic
def registrar_venta(usuario, filas, clave_operacion):
    sucursal = sucursal_ventas(usuario)
    try:
        clave = UUID(str(clave_operacion))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError("Clave de operación inválida.")
    cantidades = defaultdict(int)
    for fila in filas:
        _cantidad_entera(fila.get("cantidad"))
        modelo = fila.get("modelo")
        if not isinstance(modelo, Modelo) or not modelo.pk:
            raise ValidationError("Seleccione un modelo válido.")
        cantidades[modelo.pk] += fila["cantidad"]
    if not cantidades:
        raise ValidationError("Debe cargar al menos un modelo.")
    # La inserción con clave única es la primera escritura. Serializa escritores
    # en SQLite antes de leer stock y permite recuperar reenvíos ya confirmados.
    venta, creada = Venta.objects.get_or_create(clave_operacion=clave,
        defaults={"usuario": usuario, "sucursal": sucursal, "fecha": timezone.localdate()})
    if not creada:
        existentes = dict(venta.detalles.values_list("modelo_id", "cantidad"))
        if venta.usuario_id != usuario.pk or venta.sucursal_id != sucursal.pk or existentes != dict(cantidades):
            raise ValidationError("La clave de operación ya se utilizó con otros datos.")
        return venta
    for modelo_id, cantidad in sorted(cantidades.items()):
        actualizado = Stock.objects.filter(sucursal=sucursal, modelo_id=modelo_id,
                                           cantidad__gte=cantidad).update(cantidad=F("cantidad") - cantidad)
        if not actualizado:
            raise ValidationError("Stock insuficiente para uno de los modelos seleccionados.")
        DetalleVenta.objects.create(venta=venta, modelo_id=modelo_id, cantidad=cantidad)
    return venta


def consultar_stock(usuario):
    return Stock.objects.filter(sucursal__in=sucursales_visibles(usuario)).select_related("sucursal", "modelo__marca")


def consultar_ventas(usuario):
    return Venta.objects.filter(sucursal__in=sucursales_visibles(usuario)).select_related("sucursal", "usuario")


def resumen_ventas(usuario, fecha, sucursal=None):
    inicio = fecha.replace(day=1 if fecha.day <= 15 else 16)
    fin = fecha.replace(day=15 if fecha.day <= 15 else monthrange(fecha.year, fecha.month)[1])
    ventas = consultar_ventas(usuario).filter(fecha__range=(inicio, fin))
    if sucursal:
        ventas = ventas.filter(sucursal=sucursal)
    return DetalleVenta.objects.filter(venta__in=ventas).values(
        "venta__sucursal_id", "modelo_id", "venta__sucursal__nombre", "modelo__nombre", "modelo__marca__nombre").annotate(total=Sum("cantidad")).order_by(
        "venta__sucursal__nombre", "modelo__nombre", "modelo__marca__nombre")
