"""Servicios autorizados de pedidos y cotizaciones. No modifican existencias."""
from calendar import monthrange
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from uuid import UUID

from django.core.exceptions import ValidationError, PermissionDenied
from django.core.validators import DecimalValidator
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import (ListadoFaltantes, ItemFaltante, Modelo, Sucursal, UsuarioSucursal,
                     Proveedor, SolicitudCotizacion, EmisionSolicitud,
                     DetalleSolicitudCotizacion, Cotizacion, DetalleCotizacion)
from .permisos import exigir_rol, es_administrador


def exigir_compras(usuario):
    exigir_rol(usuario, "Compras", "Administrador")


def sucursales_pedidos(usuario):
    exigir_rol(usuario, "Ventas", "Compras", "Administrador")
    if es_administrador(usuario) or usuario.groups.filter(name="Compras").exists():
        return Sucursal.objects.all()
    return Sucursal.objects.filter(pk__in=UsuarioSucursal.objects.filter(usuario=usuario).values("sucursal_id"))


def consultar_pedidos(usuario):
    return ListadoFaltantes.objects.filter(sucursal__in=sucursales_pedidos(usuario)).select_related("sucursal", "usuario")


def filtrar_pedidos(pedidos, sucursal=None, fecha=None, quincena=None, pendientes=False):
    if sucursal:
        pedidos = pedidos.filter(sucursal=sucursal)
    if fecha:
        pedidos = pedidos.filter(fecha=fecha)
    if quincena:
        inicio, fin = limites_quincena(quincena)
        pedidos = pedidos.filter(fecha__range=(inicio, fin))
    if pendientes:
        pedidos = pedidos.filter(items__solicitado=False).distinct()
    return pedidos


def limites_quincena(fecha):
    return (fecha.replace(day=1 if fecha.day <= 15 else 16),
            fecha.replace(day=15 if fecha.day <= 15 else monthrange(fecha.year, fecha.month)[1]))


def consolidar_pedidos(usuario, **filtros):
    pedidos = filtrar_pedidos(consultar_pedidos(usuario), **filtros)
    items = ItemFaltante.objects.filter(listado__in=pedidos)
    if filtros.get("pendientes"):
        items = items.filter(solicitado=False)
    return items.values("modelo_id", "modelo__nombre", "modelo__marca__nombre").annotate(
        total=Sum("cantidad")).order_by("modelo__nombre", "modelo_id")


@transaction.atomic
def registrar_pedido(usuario, filas, sucursal=None):
    exigir_rol(usuario, "Ventas", "Administrador")
    if es_administrador(usuario):
        if sucursal is None:
            raise ValidationError("Seleccione una sucursal.")
    else:
        asignacion = UsuarioSucursal.objects.filter(usuario=usuario).first()
        if not asignacion:
            raise PermissionDenied("Debe tener una sucursal asignada para registrar pedidos.")
        if sucursal and sucursal.pk != asignacion.sucursal_id:
            raise PermissionDenied
        sucursal = asignacion.sucursal
    from . import servicios
    if not filas:
        raise ValidationError("Debe cargar al menos un modelo.")
    for fila in filas:
        servicios._cantidad_entera(fila.get("cantidad"))
        if not isinstance(fila.get("modelo"), Modelo) or not fila["modelo"].pk:
            raise ValidationError("Seleccione un modelo válido.")
        if fila.get("motivo", ItemFaltante.Motivo.VENTA) not in ItemFaltante.Motivo.values:
            raise ValidationError("Motivo inválido.")
    return servicios.crear_listado(sucursal, usuario, filas)


def consultar_proveedores(usuario):
    exigir_compras(usuario)
    return Proveedor.objects.prefetch_related("marcas")


def guardar_proveedor(usuario, form):
    exigir_compras(usuario)
    if not form.is_valid():
        raise ValidationError("Revise los datos del proveedor.")
    with transaction.atomic():
        return form.save()


def baja_proveedor(usuario, proveedor):
    exigir_compras(usuario)
    Proveedor.objects.filter(pk=proveedor.pk).update(activo=False)


def consultar_solicitudes(usuario):
    exigir_compras(usuario)
    return SolicitudCotizacion.objects.select_related("proveedor", "cotizacion").prefetch_related("detalles")


@transaction.atomic
def emitir_solicitudes(usuario, modelos, proveedores, medio, clave_operacion, quincena=None):
    exigir_compras(usuario)
    try:
        clave = UUID(str(clave_operacion))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError("Clave de operación inválida.")
    modelos_ids = sorted({m.pk for m in modelos})
    proveedores_ids = sorted({p.pk for p in proveedores})
    if not modelos_ids or not proveedores_ids:
        raise ValidationError("Seleccione al menos un modelo y un proveedor.")
    if medio not in SolicitudCotizacion.Medio.values:
        raise ValidationError("Medio inválido.")
    periodo = limites_quincena(quincena)[0] if quincena else None
    parametros = {"modelos": modelos_ids, "proveedores": proveedores_ids, "medio": medio,
                  "quincena": periodo.isoformat() if periodo else None}
    emision, creada = EmisionSolicitud.objects.get_or_create(clave_operacion=clave,
        defaults={"usuario": usuario, "parametros": parametros})
    if not creada:
        if emision.usuario_id != usuario.pk or emision.parametros != parametros:
            raise ValidationError("La clave de operación ya se utilizó con otros datos.")
        return emision
    proveedores = list(Proveedor.objects.filter(pk__in=proveedores_ids).prefetch_related("marcas"))
    if len(proveedores) != len(proveedores_ids) or any(not p.activo for p in proveedores):
        raise ValidationError("Seleccione proveedores activos.")
    items = ItemFaltante.objects.filter(solicitado=False, modelo_id__in=modelos_ids)
    if quincena:
        items = items.filter(listado__fecha__range=limites_quincena(quincena))
    items = list(items.select_related("modelo__marca"))
    if set(i.modelo_id for i in items) != set(modelos_ids):
        raise ValidationError("Algún modelo ya no tiene faltantes pendientes en el período elegido.")
    cantidades = defaultdict(int)
    modelos_por_id = {}
    for item in items:
        if item.cantidad <= 0:
            raise ValidationError("Hay faltantes históricos sin cantidad positiva; deben revisarse antes de emitir.")
        cantidades[item.modelo_id] += item.cantidad
        modelos_por_id[item.modelo_id] = item.modelo
    marcas = {m.marca_id for m in modelos_por_id.values()}
    for proveedor in proveedores:
        if not marcas <= {m.pk for m in proveedor.marcas.all()}:
            raise ValidationError(f"{proveedor.razon_social} no abastece todas las marcas seleccionadas.")
    # Reclamo condicional de todos los faltantes: otra clave no puede emitirlos otra vez.
    actualizados = ItemFaltante.objects.filter(pk__in=[i.pk for i in items], solicitado=False).update(solicitado=True)
    if actualizados != len(items):
        raise ValidationError("Los faltantes ya fueron incluidos en otra solicitud. Actualice la consulta.")
    for proveedor in proveedores:
        solicitud = SolicitudCotizacion.objects.create(emision=emision, proveedor=proveedor,
            proveedor_nombre=proveedor.razon_social, proveedor_email=proveedor.email, medio=medio, fecha=timezone.localdate())
        solicitud.items.set(items)
        DetalleSolicitudCotizacion.objects.bulk_create([
            DetalleSolicitudCotizacion(solicitud=solicitud, modelo=modelos_por_id[modelo_id],
                nombre_modelo=modelos_por_id[modelo_id].nombre,
                nombre_marca=modelos_por_id[modelo_id].marca.nombre, cantidad=cantidad)
            for modelo_id, cantidad in sorted(cantidades.items())])
    return emision


@transaction.atomic
def registrar_cotizacion(usuario, solicitud, fecha, filas):
    exigir_compras(usuario)
    from .servicios import _cantidad_entera
    solicitud = SolicitudCotizacion.objects.get(pk=solicitud.pk)
    if not fecha or fecha < solicitud.fecha or fecha > timezone.localdate():
        raise ValidationError("La fecha debe estar entre la solicitud y hoy.")
    pedidos = {d.pk: d for d in solicitud.detalles.all()}
    normalizadas = {}
    for fila in filas:
        detalle = fila.get("detalle_solicitud")
        if not isinstance(detalle, DetalleSolicitudCotizacion) or detalle.pk not in pedidos:
            raise ValidationError("El modelo no pertenece a la solicitud de origen.")
        if detalle.pk in normalizadas:
            raise ValidationError("No repita un modelo en la cotización.")
        cantidad = fila.get("cantidad")
        _cantidad_entera(cantidad)
        if cantidad > pedidos[detalle.pk].cantidad:
            raise ValidationError("La cantidad cotizada supera la solicitada.")
        try:
            precio = Decimal(str(fila.get("precio_unitario")))
            if not precio.is_finite() or precio <= 0:
                raise ValidationError("El precio debe ser positivo y finito.")
            DecimalValidator(max_digits=12, decimal_places=2)(precio)
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError("Ingrese un precio válido con hasta dos decimales.")
        importe = precio * cantidad
        # SQLite convierte NUMERIC con 15 dígitos significativos. Este límite
        # evita perder centavos en importes grandes al leer el DecimalField.
        DecimalValidator(max_digits=14, decimal_places=2)(importe)
        normalizadas[detalle.pk] = (cantidad, precio, importe)
    if not normalizadas:
        raise ValidationError("Debe registrar al menos un modelo cotizado.")
    cotizacion, creada = Cotizacion.objects.get_or_create(solicitud=solicitud,
        defaults={"usuario": usuario, "fecha": fecha})
    if not creada:
        anteriores = {d.detalle_solicitud_id: (d.cantidad, d.precio_unitario, d.importe) for d in cotizacion.detalles.all()}
        if anteriores != normalizadas or cotizacion.fecha != fecha:
            raise ValidationError("La solicitud ya tiene una cotización registrada. No se modifica su historia.")
        return cotizacion
    DetalleCotizacion.objects.bulk_create([DetalleCotizacion(cotizacion=cotizacion,
        detalle_solicitud_id=detalle_id, cantidad=valores[0], precio_unitario=valores[1], importe=valores[2])
        for detalle_id, valores in sorted(normalizadas.items())])
    return cotizacion


def comparar_cotizaciones(usuario, solicitud=None):
    exigir_compras(usuario)
    cotizaciones = Cotizacion.objects.select_related("solicitud__proveedor").prefetch_related(
        "solicitud__detalles", "detalles__detalle_solicitud")
    cesta_elegida = None
    if solicitud:
        cesta_elegida = tuple(sorted((d.modelo_id, d.cantidad) for d in solicitud.detalles.all()))
    grupos = {}
    for oferta in cotizaciones:
        cesta = tuple(sorted((d.modelo_id, d.cantidad) for d in oferta.solicitud.detalles.all()))
        if cesta_elegida is not None and cesta != cesta_elegida:
            continue
        grupo = grupos.setdefault(cesta, {"pedido": oferta.solicitud.detalles.all(), "ofertas": []})
        grupo["ofertas"].append({"cotizacion": oferta, "completa": oferta.completa,
                                  "total": oferta.total, "detalles": oferta.detalles.all()})
    return list(grupos.values())
