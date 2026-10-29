from django.contrib import admin

from . import models

for modelo in (models.Marca, models.Modelo, models.Sucursal, models.Proveedor,
               models.ListadoFaltantes, models.ItemFaltante):
    admin.site.register(modelo)


@admin.register(models.UsuarioSucursal)
class UsuarioSucursalAdmin(admin.ModelAdmin):
    list_display = ("usuario", "sucursal")

    def has_module_permission(self, request):
        from .permisos import es_administrador
        return es_administrador(request.user)

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    has_add_permission = has_module_permission
    has_change_permission = has_view_permission
    has_delete_permission = has_view_permission


class SoloLecturaAdmin(admin.ModelAdmin):
    def has_view_permission(self, request, obj=None):
        from .permisos import es_administrador
        return es_administrador(request.user)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


for modelo in (models.Stock, models.Venta, models.DetalleVenta, models.AjusteStock):
    admin.site.register(modelo, SoloLecturaAdmin)


# Solicitudes y respuestas emitidas se preservan; no se editan fuera del servicio.
for modelo in (models.SolicitudCotizacion, models.EmisionSolicitud,
               models.DetalleSolicitudCotizacion, models.Cotizacion, models.DetalleCotizacion):
    admin.site.register(modelo, SoloLecturaAdmin)


for modelo in (models.Compra, models.DetalleCompra, models.OrigenCompra,
               models.DocumentoCompra, models.DecisionFinanciera, models.MovimientoCompra):
    admin.site.register(modelo, SoloLecturaAdmin)
