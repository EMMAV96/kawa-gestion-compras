from django.conf import settings
from django.db import models
from django.utils import timezone


class Marca(models.Model):
    nombre = models.CharField(max_length=80, unique=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Modelo(models.Model):
    nombre = models.CharField(max_length=80)
    marca = models.ForeignKey(Marca, on_delete=models.PROTECT, related_name="modelos")

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} · {self.marca.nombre}"


class Sucursal(models.Model):
    nombre = models.CharField(max_length=80)

    class Meta:
        ordering = ["nombre"]
        verbose_name_plural = "sucursales"

    def __str__(self):
        return self.nombre


class Proveedor(models.Model):
    razon_social = models.CharField("razón social", max_length=120)
    email = models.EmailField()
    es_fijo = models.BooleanField("proveedor fijo", default=False)
    activo = models.BooleanField(default=True)
    marcas = models.ManyToManyField(Marca, related_name="proveedores")

    class Meta:
        ordering = ["razon_social"]
        verbose_name_plural = "proveedores"

    def __str__(self):
        return self.razon_social


class ListadoFaltantes(models.Model):
    class Estado(models.TextChoices):
        CARGADO = "CARGADO", "Faltante cargado"

    sucursal = models.ForeignKey(Sucursal, on_delete=models.PROTECT)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha = models.DateField()
    quincena = models.CharField(max_length=40)
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.CARGADO)

    class Meta:
        ordering = ["-id"]
        verbose_name_plural = "listados de faltantes"

    def __str__(self):
        return f"Listado {self.pk} - {self.sucursal}"


class ItemFaltante(models.Model):
    class Motivo(models.TextChoices):
        VENTA = "VENTA", "Venta"
        PEDIDO_CLIENTE = "PEDIDO_CLIENTE", "Pedido de cliente"

    listado = models.ForeignKey(ListadoFaltantes, on_delete=models.CASCADE, related_name="items")
    modelo = models.ForeignKey(Modelo, on_delete=models.PROTECT, related_name="items_faltantes")
    cantidad = models.PositiveIntegerField()
    motivo = models.CharField(max_length=20, choices=Motivo.choices, default=Motivo.VENTA)
    solicitado = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.cantidad} x {self.modelo}"


class SolicitudCotizacion(models.Model):
    class Medio(models.TextChoices):
        MAIL = "MAIL", "Mail"
        FAX = "FAX", "Fax"

    class Estado(models.TextChoices):
        ENVIADA = "ENVIADA", "Enviada"

    emision = models.ForeignKey("EmisionSolicitud", on_delete=models.PROTECT, null=True, blank=True, related_name="solicitudes")
    proveedor_nombre = models.CharField(max_length=120, blank=True)
    proveedor_email = models.EmailField(blank=True)
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT)
    fecha = models.DateField(default=timezone.localdate, editable=False)
    medio = models.CharField(max_length=10, choices=Medio.choices, default=Medio.MAIL)
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.ENVIADA)
    items = models.ManyToManyField(ItemFaltante, related_name="solicitudes")

    class Meta:
        ordering = ["-id"]
        constraints = [models.UniqueConstraint(fields=["emision", "proveedor"], name="solicitud_emision_proveedor_unico")]
        verbose_name = "solicitud de cotización"
        verbose_name_plural = "solicitudes de cotización"

    def __str__(self):
        return f"Solicitud {self.pk} - {self.proveedor_nombre or self.proveedor}"


class UsuarioSucursal(models.Model):
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name="asignacion_sucursal")
    sucursal = models.ForeignKey(Sucursal, on_delete=models.PROTECT)

    def __str__(self):
        return f"{self.usuario} \u00b7 {self.sucursal}"


class Stock(models.Model):
    sucursal = models.ForeignKey(Sucursal, on_delete=models.PROTECT)
    modelo = models.ForeignKey(Modelo, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sucursal__nombre", "modelo__nombre"]
        constraints = [
            models.UniqueConstraint(fields=["sucursal", "modelo"], name="stock_sucursal_modelo_unico"),
            models.CheckConstraint(condition=models.Q(cantidad__gte=0), name="stock_no_negativo"),
        ]


class Venta(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    sucursal = models.ForeignKey(Sucursal, on_delete=models.PROTECT)
    fecha = models.DateField(default=timezone.localdate)
    creada = models.DateTimeField(auto_now_add=True)
    clave_operacion = models.UUIDField(unique=True, editable=False)

    class Meta:
        ordering = ["-creada", "-pk"]


class DetalleVenta(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.PROTECT, related_name="detalles")
    modelo = models.ForeignKey(Modelo, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["venta", "modelo"], name="venta_modelo_unico"),
            models.CheckConstraint(condition=models.Q(cantidad__gt=0), name="detalle_venta_positivo"),
        ]


class AjusteStock(models.Model):
    stock = models.ForeignKey(Stock, on_delete=models.PROTECT, related_name="ajustes")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    variacion = models.IntegerField()
    motivo = models.CharField(max_length=250)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=~models.Q(variacion=0), name="ajuste_no_cero")]


class EmisionSolicitud(models.Model):
    clave_operacion = models.UUIDField(unique=True, editable=False)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    parametros = models.JSONField()
    fecha = models.DateTimeField(auto_now_add=True)


class DetalleSolicitudCotizacion(models.Model):
    solicitud = models.ForeignKey(SolicitudCotizacion, on_delete=models.PROTECT, related_name="detalles")
    modelo = models.ForeignKey(Modelo, on_delete=models.PROTECT)
    nombre_modelo = models.CharField(max_length=80)
    nombre_marca = models.CharField(max_length=80)
    cantidad = models.PositiveIntegerField()

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(fields=["solicitud", "modelo"], name="solicitud_modelo_unico"),
            models.CheckConstraint(condition=models.Q(cantidad__gte=0), name="detalle_solicitud_no_negativo"),
        ]


class Cotizacion(models.Model):
    solicitud = models.OneToOneField(SolicitudCotizacion, on_delete=models.PROTECT, related_name="cotizacion")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha = models.DateField()
    registrada = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-pk"]

    @property
    def proveedor(self):
        return self.solicitud.proveedor

    @property
    def total(self):
        from decimal import Decimal
        return sum((linea.importe for linea in self.detalles.all()), Decimal("0.00"))

    @property
    def completa(self):
        pedido = dict(self.solicitud.detalles.values_list("modelo_id", "cantidad"))
        oferta = {linea.detalle_solicitud.modelo_id: linea.cantidad for linea in self.detalles.all()}
        return bool(pedido) and pedido == oferta


class DetalleCotizacion(models.Model):
    cotizacion = models.ForeignKey(Cotizacion, on_delete=models.PROTECT, related_name="detalles")
    detalle_solicitud = models.ForeignKey(DetalleSolicitudCotizacion, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField()
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    importe = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(fields=["cotizacion", "detalle_solicitud"], name="cotizacion_detalle_unico"),
            models.CheckConstraint(condition=models.Q(cantidad__gt=0), name="detalle_cotizacion_positivo"),
            models.CheckConstraint(condition=models.Q(precio_unitario__gt=0), name="precio_cotizacion_positivo"),
            models.CheckConstraint(condition=models.Q(importe__gt=0), name="importe_cotizacion_positivo"),
        ]


class Compra(models.Model):
    class Procedimiento(models.TextChoices):
        HABITUAL = "HABITUAL", "Proveedor habitual"
        COTIZACION = "COTIZACION", "Mediante cotizaciones"

    class Estado(models.TextChoices):
        EN_PREPARACION = "EN_PREPARACION", "En preparación"
        PENDIENTE_COTIZACIONES = "PENDIENTE_COTIZACIONES", "Pendiente de cotizaciones"
        EN_EVALUACION = "EN_EVALUACION", "En evaluación"
        DOCUMENTACION_PREPARADA = "DOCUMENTACION_PREPARADA", "Documentación preparada"
        PENDIENTE_APROBACION = "PENDIENTE_APROBACION", "Pendiente de aprobación"
        APROBADA = "APROBADA", "Aprobada"
        RECHAZADA = "RECHAZADA", "Rechazada"

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    creada = models.DateTimeField(auto_now_add=True)
    procedimiento = models.CharField(max_length=15, choices=Procedimiento.choices)
    estado = models.CharField(max_length=30, choices=Estado.choices, default=Estado.EN_PREPARACION)
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT)
    proveedor_nombre = models.CharField(max_length=120)
    proveedor_email = models.EmailField()
    solicitud = models.ForeignKey(SolicitudCotizacion, on_delete=models.PROTECT, null=True, blank=True)
    cotizacion = models.ForeignKey(Cotizacion, on_delete=models.PROTECT, null=True, blank=True)
    clave_operacion = models.UUIDField(unique=True, editable=False)
    parametros = models.JSONField()
    version = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        ordering = ["-pk"]
        constraints = [
            models.CheckConstraint(condition=models.Q(procedimiento__in=["HABITUAL", "COTIZACION"]), name="compra_procedimiento_valido"),
            models.CheckConstraint(condition=models.Q(estado__in=["EN_PREPARACION", "PENDIENTE_COTIZACIONES", "EN_EVALUACION", "DOCUMENTACION_PREPARADA", "PENDIENTE_APROBACION", "APROBADA", "RECHAZADA"]), name="compra_estado_valido"),
        ]

    @property
    def total(self):
        from decimal import Decimal
        lineas = list(self.detalles.all())
        if not lineas or any(d.importe is None for d in lineas):
            return None
        return sum((d.importe for d in lineas), Decimal("0.00"))

    @property
    def cerrada(self):
        return self.estado in (self.Estado.APROBADA, self.Estado.RECHAZADA)

    def __str__(self):
        return f"Compra {self.pk} - {self.proveedor_nombre}"


class OrigenCompra(models.Model):
    compra = models.ForeignKey(Compra, on_delete=models.PROTECT, related_name="origenes")
    item = models.ForeignKey(ItemFaltante, on_delete=models.PROTECT, related_name="origenes_compra")
    pedido = models.ForeignKey(ListadoFaltantes, on_delete=models.PROTECT, related_name="origenes_compra")
    cantidad = models.PositiveIntegerField()
    sucursal_nombre = models.CharField(max_length=80)
    fecha_pedido = models.DateField()
    vigente = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["compra", "item"], name="compra_item_unico"),
            models.UniqueConstraint(fields=["item"], condition=models.Q(vigente=True), name="necesidad_compra_vigente_unica"),
            models.CheckConstraint(condition=models.Q(cantidad__gt=0), name="origen_compra_positivo"),
        ]


class DetalleCompra(models.Model):
    compra = models.ForeignKey(Compra, on_delete=models.PROTECT, related_name="detalles")
    modelo = models.ForeignKey(Modelo, on_delete=models.PROTECT)
    nombre_modelo = models.CharField(max_length=80)
    nombre_marca = models.CharField(max_length=80)
    cantidad = models.PositiveIntegerField()
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    importe = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(fields=["compra", "modelo"], name="compra_modelo_unico"),
            models.CheckConstraint(condition=models.Q(cantidad__gt=0), name="detalle_compra_positivo"),
            models.CheckConstraint(condition=models.Q(precio_unitario__isnull=True, importe__isnull=True) | models.Q(precio_unitario__gt=0, importe__gt=0, precio_unitario__isnull=False, importe__isnull=False), name="compra_precio_importe_validos"),
        ]


class DocumentoCompra(models.Model):
    class Tipo(models.TextChoices):
        NOTA_PEDIDO = "NOTA_PEDIDO", "Nota de Pedido"
        ORDEN_COMPRA = "ORDEN_COMPRA", "Orden de Compra"

    compra = models.OneToOneField(Compra, on_delete=models.PROTECT, related_name="documento")
    numero = models.CharField(max_length=40, unique=True, editable=False)
    fecha = models.DateField(default=timezone.localdate, editable=False)
    tipo = models.CharField(max_length=15, choices=Tipo.choices)
    contenido = models.JSONField()

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(tipo__in=["NOTA_PEDIDO", "ORDEN_COMPRA"]), name="documento_compra_tipo_valido")]


class DecisionFinanciera(models.Model):
    compra = models.OneToOneField(Compra, on_delete=models.PROTECT, related_name="decision")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True)
    resultado = models.CharField(max_length=15, choices=[("APROBADA", "Aprobada"), ("RECHAZADA", "Rechazada")])
    motivo = models.TextField(blank=True, max_length=2000)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(resultado__in=["APROBADA", "RECHAZADA"]), name="decision_compra_valida")]


class MovimientoCompra(models.Model):
    compra = models.ForeignKey(Compra, on_delete=models.PROTECT, related_name="movimientos")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True)
    estado_anterior = models.CharField(max_length=30, blank=True)
    estado_nuevo = models.CharField(max_length=30)
    actividad = models.CharField(max_length=120)

    class Meta:
        ordering = ["pk"]
