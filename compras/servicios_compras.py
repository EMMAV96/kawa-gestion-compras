"""Transacción de compras. Nunca modifica Stock ni genera recepciones."""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import DecimalValidator
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .models import (Compra, DetalleCompra, OrigenCompra, DocumentoCompra,
                     DecisionFinanciera, MovimientoCompra, Proveedor,
                     ItemFaltante, SolicitudCotizacion, Cotizacion)
from .permisos import exigir_rol
from .servicios_pedidos import exigir_compras

E = Compra.Estado
P = Compra.Procedimiento


def exigir_finanzas(usuario):
    # Deliberadamente no utiliza el bypass de superusuario/Administrador.
    if not usuario.is_authenticated or not usuario.is_active or not usuario.groups.filter(name="Finanzas").exists():
        raise PermissionDenied("La decisión requiere pertenecer explícitamente al grupo Finanzas.")


def puede_decidir(usuario):
    return usuario.is_authenticated and usuario.is_active and usuario.groups.filter(name="Finanzas").exists()


def consultar_compras(usuario):
    exigir_rol(usuario, "Compras", "Finanzas", "Administrador")
    return Compra.objects.select_related("usuario", "proveedor", "solicitud", "cotizacion", "documento", "decision__usuario")


def necesidades_disponibles(usuario):
    exigir_compras(usuario)
    return ItemFaltante.objects.exclude(origenes_compra__vigente=True).select_related("modelo__marca", "listado__sucursal")


def _precio(valor):
    try:
        precio = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError("Ingrese precios válidos.")
    if not precio.is_finite() or precio <= 0:
        raise ValidationError("Los precios deben ser positivos y finitos.")
    DecimalValidator(max_digits=12, decimal_places=2)(precio)
    return precio.quantize(Decimal("0.01"))


def _importe(precio, cantidad):
    importe = precio * cantidad
    DecimalValidator(max_digits=14, decimal_places=2)(importe)
    return importe


def _validar_proveedor(proveedor, modelos, habitual=False):
    proveedor = Proveedor.objects.get(pk=proveedor.pk)
    if not proveedor.activo or (habitual and not proveedor.es_fijo):
        raise ValidationError("Se requiere un proveedor activo" + (" y habitual." if habitual else "."))
    if not {m.marca_id for m in modelos} <= set(proveedor.marcas.values_list("pk", flat=True)):
        raise ValidationError("El proveedor no abastece todas las marcas solicitadas.")
    return proveedor


def _registrar_movimiento(compra, usuario, anterior, actividad):
    MovimientoCompra.objects.create(compra=compra, usuario=usuario, estado_anterior=anterior,
                                    estado_nuevo=compra.estado, actividad=actividad)


def _tomar(compra, estados):
    # Escritura condicional antes de consultar detalles. Funciona en SQLite,
    # sin depender de select_for_update. Un error posterior revierte la versión.
    if not Compra.objects.filter(pk=compra.pk, estado__in=estados).update(version=F("version") + 1):
        raise ValidationError("La transición no está permitida en el estado actual de la compra.")
    return Compra.objects.get(pk=compra.pk)


def _cesta_origen(items):
    cantidades = defaultdict(int)
    modelos = {}
    for item in items:
        if item.cantidad <= 0:
            raise ValidationError("Las cantidades deben ser positivas.")
        cantidades[item.modelo_id] += item.cantidad
        modelos[item.modelo_id] = item.modelo
    return dict(cantidades), modelos


def _validar_solicitud(solicitud, items):
    cesta, _ = _cesta_origen(items)
    esperada = dict(solicitud.detalles.values_list("modelo_id", "cantidad"))
    if not cesta or cesta != esperada:
        raise ValidationError("Los pedidos de origen no coinciden con la copia histórica de la solicitud.")


@transaction.atomic
def preparar_compra(usuario, procedimiento, clave_operacion, proveedor=None, items=(), precios=None, solicitud=None):
    exigir_compras(usuario)
    try:
        clave = UUID(str(clave_operacion))
    except (ValueError, AttributeError, TypeError):
        raise ValidationError("Clave de operación inválida.")
    precios = {int(k): _precio(v) for k, v in (precios or {}).items()}
    ids = sorted({i.pk for i in items})
    parametros = {"procedimiento": procedimiento, "proveedor": proveedor.pk if proveedor else None,
        "items": ids, "precios": {str(k): str(v) for k, v in sorted(precios.items())},
        "solicitud": solicitud.pk if solicitud else None}
    existente = Compra.objects.filter(clave_operacion=clave).first()
    if existente:
        if existente.usuario_id != usuario.pk or existente.parametros != parametros:
            raise ValidationError("La clave ya se utilizó con otros datos.")
        return existente
    if procedimiento == P.HABITUAL:
        if not proveedor or not ids or solicitud:
            raise ValidationError("Seleccione proveedor habitual y pedidos de origen, sin solicitud.")
        items = list(ItemFaltante.objects.filter(pk__in=ids).select_related("modelo__marca", "listado__sucursal"))
        if len(items) != len(ids):
            raise ValidationError("Hay pedidos de origen inexistentes.")
    elif procedimiento == P.COTIZACION:
        if not solicitud or proveedor or ids or precios:
            raise ValidationError("Para cotizaciones seleccione únicamente la solicitud de origen.")
        solicitud = SolicitudCotizacion.objects.select_related("proveedor").get(pk=solicitud.pk)
        proveedor = solicitud.proveedor
        items = list(solicitud.items.select_related("modelo__marca", "listado__sucursal"))
        _validar_solicitud(solicitud, items)
    else:
        raise ValidationError("Procedimiento inválido.")
    cesta, modelos = _cesta_origen(items)
    proveedor = _validar_proveedor(proveedor, modelos.values(), habitual=procedimiento == P.HABITUAL)
    if procedimiento == P.HABITUAL and set(precios) != set(cesta):
        raise ValidationError("Ingrese un precio acordado por cada modelo de los pedidos elegidos, sin modelos adicionales.")
    # PostgreSQL permits two readers to reach this insert concurrently.
    # get_or_create preserves the existing UUID idempotency contract on both DBs.
    compra, creada = Compra.objects.get_or_create(clave_operacion=clave, defaults={
        "usuario": usuario, "procedimiento": procedimiento, "parametros": parametros,
        "proveedor": proveedor, "proveedor_nombre": proveedor.razon_social,
        "proveedor_email": proveedor.email, "solicitud": solicitud})
    if not creada:
        if compra.usuario_id != usuario.pk or compra.parametros != parametros:
            raise ValidationError("La clave ya se utilizó con otros datos.")
        return compra
    try:
        with transaction.atomic():
            OrigenCompra.objects.bulk_create([OrigenCompra(compra=compra, item=item, pedido=item.listado, cantidad=item.cantidad,
                sucursal_nombre=item.listado.sucursal.nombre, fecha_pedido=item.listado.fecha) for item in items])
    except IntegrityError:
        raise ValidationError("Alguna necesidad ya está reservada por otra compra. Actualice los pendientes.")
    historicos = {d.modelo_id: d for d in solicitud.detalles.all()} if solicitud else {}
    DetalleCompra.objects.bulk_create([DetalleCompra(compra=compra, modelo=modelos[modelo_id],
        nombre_modelo=historicos[modelo_id].nombre_modelo if solicitud else modelos[modelo_id].nombre,
        nombre_marca=historicos[modelo_id].nombre_marca if solicitud else modelos[modelo_id].marca.nombre,
        cantidad=cantidad, precio_unitario=precios.get(modelo_id),
        importe=_importe(precios[modelo_id], cantidad) if modelo_id in precios else None)
        for modelo_id, cantidad in sorted(cesta.items())])
    _registrar_movimiento(compra, usuario, "", "Operación preparada y necesidades reservadas")
    return compra


@transaction.atomic
def evaluar_solicitud(usuario, compra):
    exigir_compras(usuario)
    compra = _tomar(compra, [E.EN_PREPARACION, E.PENDIENTE_COTIZACIONES, E.EN_EVALUACION])
    if compra.procedimiento != P.COTIZACION:
        raise ValidationError("El proveedor habitual no requiere evaluación de cotizaciones.")
    anterior = compra.estado
    # Varias solicitudes pueden representar la misma necesidad; basta una
    # respuesta para comenzar a evaluar, pero la selección exige oferta completa.
    ofertas = ofertas_para_compra(usuario, compra, solo_completas=False)
    compra.estado = E.EN_EVALUACION if ofertas else E.PENDIENTE_COTIZACIONES
    if anterior == E.EN_EVALUACION and not ofertas:
        raise ValidationError("No hay ofertas para evaluar.")
    compra.save(update_fields=["estado"])
    if compra.estado != anterior:
        _registrar_movimiento(compra, usuario, anterior, "Consulta de respuestas recibidas")
    return compra


def _oferta_compatible(compra, oferta):
    origen = set(compra.origenes.values_list("item_id", flat=True))
    if origen != set(oferta.solicitud.items.values_list("pk", flat=True)):
        return False
    cesta = dict(compra.detalles.values_list("modelo_id", "cantidad"))
    pedido = dict(oferta.solicitud.detalles.values_list("modelo_id", "cantidad"))
    return bool(cesta) and cesta == pedido


def _oferta_valida(compra, oferta):
    if not _oferta_compatible(compra, oferta) or not oferta.completa:
        return False
    esperados = set(oferta.solicitud.detalles.values_list("pk", flat=True))
    recibidos = list(oferta.detalles.values_list("detalle_solicitud_id", flat=True))
    return len(recibidos) == len(esperados) and set(recibidos) == esperados


def ofertas_para_compra(usuario, compra, solo_completas=True):
    exigir_compras(usuario)
    return [o for o in Cotizacion.objects.select_related("solicitud__proveedor").prefetch_related(
        "solicitud__items", "solicitud__detalles", "detalles__detalle_solicitud")
        if _oferta_compatible(compra, o) and (not solo_completas or _oferta_valida(compra, o))]


@transaction.atomic
def seleccionar_oferta(usuario, compra, oferta):
    exigir_compras(usuario)
    compra = _tomar(compra, [E.EN_EVALUACION])
    oferta = Cotizacion.objects.select_related("solicitud__proveedor").get(pk=oferta.pk)
    if compra.procedimiento != P.COTIZACION or not _oferta_valida(compra, oferta):
        raise ValidationError("La oferta debe ser completa y corresponder exactamente a los pedidos, modelos y cantidades de la compra.")
    proveedor = _validar_proveedor(oferta.proveedor, [d.modelo for d in compra.detalles.select_related("modelo")])
    if compra.cotizacion_id:
        if compra.cotizacion_id == oferta.pk:
            return compra
        raise ValidationError("La operación ya tiene una oferta seleccionada; no se reemplaza su historia.")
    lineas = {d.detalle_solicitud.modelo_id: d for d in oferta.detalles.select_related("detalle_solicitud")}
    for detalle in compra.detalles.all():
        linea = lineas[detalle.modelo_id]
        precio = _precio(linea.precio_unitario)
        importe = _importe(precio, detalle.cantidad)
        if linea.cantidad != detalle.cantidad or linea.importe != importe:
            raise ValidationError("La oferta tiene importes o cantidades inconsistentes.")
        detalle.precio_unitario, detalle.importe = precio, importe
        detalle.save(update_fields=["precio_unitario", "importe"])
    compra.cotizacion = oferta
    compra.proveedor = proveedor
    compra.proveedor_nombre = oferta.solicitud.proveedor_nombre
    compra.proveedor_email = oferta.solicitud.proveedor_email
    compra.save(update_fields=["cotizacion", "proveedor", "proveedor_nombre", "proveedor_email"])
    _registrar_movimiento(compra, usuario, compra.estado, "Oferta completa seleccionada")
    return compra


def _validar_comercial(compra):
    detalles = list(compra.detalles.select_related("modelo"))
    _validar_proveedor(compra.proveedor, [d.modelo for d in detalles], compra.procedimiento == P.HABITUAL)
    if not detalles or any(d.precio_unitario is None for d in detalles):
        raise ValidationError("Debe completar los precios antes de documentar.")
    for d in detalles:
        if d.cantidad <= 0 or _importe(_precio(d.precio_unitario), d.cantidad) != d.importe:
            raise ValidationError("Detalle comercial inválido.")
    if compra.procedimiento == P.COTIZACION and (not compra.cotizacion_id or not _oferta_valida(compra, compra.cotizacion) or compra.proveedor_id != compra.cotizacion.solicitud.proveedor_id):
        raise ValidationError("Falta una oferta completa y compatible.")


@transaction.atomic
def generar_documento(usuario, compra):
    exigir_compras(usuario)
    existente = DocumentoCompra.objects.filter(compra_id=compra.pk).first()
    if existente:
        return existente
    compra = _tomar(compra, [E.EN_PREPARACION, E.EN_EVALUACION])
    if compra.procedimiento == P.COTIZACION and compra.estado != E.EN_EVALUACION:
        raise ValidationError("Primero evalúe y seleccione una oferta.")
    _validar_comercial(compra)
    tipo = DocumentoCompra.Tipo.NOTA_PEDIDO if compra.procedimiento == P.HABITUAL else DocumentoCompra.Tipo.ORDEN_COMPRA
    prefijo = "NP" if tipo == DocumentoCompra.Tipo.NOTA_PEDIDO else "OC"
    contenido = {"compra": compra.pk, "procedimiento": compra.get_procedimiento_display(),
        "responsable": compra.usuario.get_full_name() or compra.usuario.username,
        "proveedor_id": compra.proveedor_id, "proveedor": compra.proveedor_nombre, "email": compra.proveedor_email,
        "cotizacion": compra.cotizacion_id, "moneda": "ARS", "total": str(compra.total),
        "detalles": [{"modelo_id": d.modelo_id, "modelo": d.nombre_modelo, "marca": d.nombre_marca,
            "cantidad": d.cantidad, "precio": str(d.precio_unitario), "importe": str(d.importe)} for d in compra.detalles.all()],
        "origenes": [{"item": o.item_id, "pedido": o.pedido_id, "sucursal": o.sucursal_nombre,
            "fecha": o.fecha_pedido.isoformat(), "cantidad": o.cantidad} for o in compra.origenes.select_related("item")]}
    documento = DocumentoCompra.objects.create(compra=compra, numero=f"{prefijo}-{compra.pk:08d}", tipo=tipo, contenido=contenido)
    anterior, compra.estado = compra.estado, E.DOCUMENTACION_PREPARADA
    compra.save(update_fields=["estado"])
    _registrar_movimiento(compra, usuario, anterior, f"Documento {documento.numero} generado")
    return documento


@transaction.atomic
def solicitar_aprobacion(usuario, compra):
    exigir_compras(usuario)
    # Reenvío ya realizado: no agrega otra solicitud ni modifica el historial.
    actual = Compra.objects.get(pk=compra.pk)
    if actual.estado == E.PENDIENTE_APROBACION:
        return actual
    compra = _tomar(compra, [E.DOCUMENTACION_PREPARADA])
    _validar_comercial(compra)
    documento = DocumentoCompra.objects.filter(compra=compra).first()
    esperado = DocumentoCompra.Tipo.NOTA_PEDIDO if compra.procedimiento == P.HABITUAL else DocumentoCompra.Tipo.ORDEN_COMPRA
    if not documento or documento.tipo != esperado:
        raise ValidationError("El documento no corresponde al procedimiento.")
    compra.estado = E.PENDIENTE_APROBACION
    compra.save(update_fields=["estado"])
    _registrar_movimiento(compra, usuario, E.DOCUMENTACION_PREPARADA, "Aprobación financiera solicitada")
    return compra


@transaction.atomic
def decidir_compra(usuario, compra, resultado, motivo=""):
    exigir_finanzas(usuario)
    if resultado not in (E.APROBADA, E.RECHAZADA):
        raise ValidationError("Resultado financiero inválido.")
    motivo = motivo.strip() if isinstance(motivo, str) else ""
    if len(motivo) > 2000 or (resultado == E.RECHAZADA and not motivo):
        raise ValidationError("El rechazo requiere un motivo; máximo 2000 caracteres.")
    compra = _tomar(compra, [E.PENDIENTE_APROBACION])
    documento = DocumentoCompra.objects.filter(compra=compra).first()
    esperado = DocumentoCompra.Tipo.NOTA_PEDIDO if compra.procedimiento == P.HABITUAL else DocumentoCompra.Tipo.ORDEN_COMPRA
    if not documento or documento.tipo != esperado:
        raise ValidationError("Falta la documentación correspondiente.")
    DecisionFinanciera.objects.create(compra=compra, usuario=usuario, resultado=resultado, motivo=motivo)
    compra.estado = resultado
    compra.save(update_fields=["estado"])
    if resultado == E.RECHAZADA:
        compra.origenes.update(vigente=False)
    _registrar_movimiento(compra, usuario, E.PENDIENTE_APROBACION, "Decisión financiera registrada")
    return compra
