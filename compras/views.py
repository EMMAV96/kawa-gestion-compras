from functools import wraps
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import OperationalError, transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import servicios, servicios_pedidos
from .permisos import sucursal_ventas
from .forms import (
    AdminPasswordForm, AdminUserForm, ItemFormSet, ListadoForm, MarcaAdminForm,
    ModeloAdminForm, ProveedorForm, SolicitudForm, SucursalAdminForm,
    VentaForm, VentaFormSet, AjusteStockForm, ConsultaSucursalForm, ResumenVentasForm,
    FiltroPedidosForm, CotizacionRecibidaForm, CotizacionFormSet, ComparacionForm,
)
from .models import (
    ItemFaltante, ListadoFaltantes, Marca, Modelo, Proveedor, SolicitudCotizacion, Sucursal,
)


def rol_requerido(*roles):
    """Exige sesión iniciada y pertenecer a alguno de los grupos indicados."""
    def decorador(vista):
        @login_required
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            usuario = request.user
            if usuario.is_superuser or usuario.groups.filter(name__in=(*roles, "Administrador")).exists():
                return vista(request, *args, **kwargs)
            raise PermissionDenied
        return envoltura
    return decorador


@login_required
def panel(request):
    return render(request, "panel.html")


# ---------- Proveedores (rol Compras) ----------

@rol_requerido("Compras")
def proveedor_lista(request):
    proveedores = servicios_pedidos.consultar_proveedores(request.user)
    return render(request, "proveedores/lista.html", {"proveedores": proveedores})


def _formulario_proveedor(request, proveedor=None):
    form = ProveedorForm(request.POST or None, instance=proveedor)
    if request.method == "POST" and form.is_valid():
        servicios_pedidos.guardar_proveedor(request.user, form)
        messages.success(request, "Proveedor actualizado" if proveedor else "Proveedor guardado")
        return redirect("proveedor_lista")
    titulo = "Editar proveedor" if proveedor else "Nuevo proveedor"
    return render(request, "proveedores/form.html", {"form": form, "titulo": titulo})


@rol_requerido("Compras")
def proveedor_nuevo(request):
    return _formulario_proveedor(request)


@rol_requerido("Compras")
def proveedor_editar(request, pk):
    return _formulario_proveedor(request, get_object_or_404(Proveedor, pk=pk))


@rol_requerido("Compras")
@require_POST
def proveedor_baja(request, pk):
    proveedor = get_object_or_404(Proveedor, pk=pk)
    servicios_pedidos.baja_proveedor(request.user, proveedor)
    messages.success(request, "Proveedor dado de baja")
    return redirect("proveedor_lista")


# ---------- Modelos faltantes (rol Ventas) ----------

@rol_requerido("Ventas", "Compras")
def faltantes_lista(request):
    form = FiltroPedidosForm(request.GET, usuario=request.user)
    listados = servicios_pedidos.consultar_pedidos(request.user)
    if form.is_valid():
        listados = servicios_pedidos.filtrar_pedidos(listados, **form.cleaned_data)
    else:
        listados = listados.none()
    return render(request, "faltantes/lista.html", {"listados": listados.prefetch_related("items"), "form": form})


@rol_requerido("Ventas", "Compras")
def faltantes_detalle(request, pk):
    listado = get_object_or_404(servicios_pedidos.consultar_pedidos(request.user), pk=pk)
    return render(request, "faltantes/detalle.html", {"listado": listado, "items": listado.items.select_related("modelo__marca")})


@rol_requerido("Ventas", "Compras")
def faltantes_consolidado(request):
    form = FiltroPedidosForm(request.GET, usuario=request.user)
    lineas = servicios_pedidos.consolidar_pedidos(request.user, **form.cleaned_data) if form.is_valid() else []
    return render(request, "faltantes/consolidado.html", {"form": form, "lineas": lineas})


@rol_requerido("Ventas")
def faltantes_nuevo(request):
    from .permisos import es_administrador
    from .models import UsuarioSucursal
    if not es_administrador(request.user) and not UsuarioSucursal.objects.filter(usuario=request.user).exists():
        raise PermissionDenied("Debe tener una sucursal asignada para registrar pedidos.")
    form = ListadoForm(request.POST if request.method == "POST" else None, usuario=request.user)
    formset = ItemFormSet(request.POST if request.method == "POST" else None, prefix="filas")
    if request.method == "POST":
        form_ok, formset_ok = form.is_valid(), formset.is_valid()
        if form_ok and formset_ok:
            try:
                servicios_pedidos.registrar_pedido(request.user, formset.filas_cargadas(), form.cleaned_data["sucursal"])
            except (ValidationError, OperationalError) as error:
                _error_operacion(form, error)
            else:
                messages.success(request, "Listado enviado correctamente")
                return redirect("faltantes_lista")
    return render(request, "faltantes/nuevo.html", {"form": form, "formset": formset})


# ---------- Solicitudes y cotizaciones recibidas (rol Compras) ----------

@rol_requerido("Compras")
def cotizacion_lista(request):
    solicitudes = servicios_pedidos.consultar_solicitudes(request.user)
    return render(request, "cotizaciones/lista.html", {"solicitudes": solicitudes})


@rol_requerido("Compras")
def cotizacion_nueva(request):
    # La clave opcional conserva compatibilidad con formularios anteriores.
    # Los nuevos formularios siempre incluyen un UUID explícito.
    form = SolicitudForm(request.POST if request.method == "POST" else None,
                         initial={"clave_operacion": uuid4(), "quincena": request.GET.get("quincena", "")})
    if request.method == "POST" and form.is_valid():
        clave = form.cleaned_data["clave_operacion"]
        if clave is None:
            clave = request.session.get("clave_solicitud_legacy")
            if not clave:
                clave = str(uuid4())
                request.session["clave_solicitud_legacy"] = clave
        try:
            cantidad = servicios.generar_solicitudes(form.cleaned_data["modelos"],
                list(form.cleaned_data["proveedores"]), form.cleaned_data["medio"],
                usuario=request.user, clave_operacion=clave, quincena=form.cleaned_data["quincena"])
        except (ValidationError, OperationalError) as error:
            _error_operacion(form, error)
        else:
            messages.success(request, "Solicitud generada" if cantidad == 1 else f"{cantidad} solicitudes generadas")
            return redirect("cotizacion_lista")
    filtros = FiltroPedidosForm({"quincena": (request.POST if request.method == "POST" else request.GET).get("quincena", ""), "pendientes": True}, usuario=request.user)
    lineas = servicios_pedidos.consolidar_pedidos(request.user, **filtros.cleaned_data) if filtros.is_valid() else []
    return render(request, "cotizaciones/nueva.html", {"form": form, "lineas": lineas,
        "filtro": filtros, "seleccionados": request.POST.getlist("modelos")})


@rol_requerido("Compras")
def solicitud_detalle(request, pk):
    solicitud = get_object_or_404(servicios_pedidos.consultar_solicitudes(request.user), pk=pk)
    return render(request, "cotizaciones/solicitud_detalle.html", {"solicitud": solicitud})


@rol_requerido("Compras")
def cotizacion_recibida(request, pk):
    solicitud = get_object_or_404(servicios_pedidos.consultar_solicitudes(request.user), pk=pk)
    if request.method != "POST" and hasattr(solicitud, "cotizacion"):
        return redirect("cotizacion_detalle", pk=solicitud.cotizacion.pk)
    form = CotizacionRecibidaForm(request.POST if request.method == "POST" else None,
                                 initial={"fecha": timezone.localdate()})
    formset = CotizacionFormSet(request.POST if request.method == "POST" else None, prefix="filas",
        initial=[{"detalle_solicitud": d.pk} for d in solicitud.detalles.all()], form_kwargs={"solicitud": solicitud})
    if request.method == "POST":
        form_ok, filas_ok = form.is_valid(), formset.is_valid()
        if form_ok and filas_ok:
            try:
                oferta = servicios_pedidos.registrar_cotizacion(request.user, solicitud, form.cleaned_data["fecha"], formset.filas_cargadas())
            except (ValidationError, OperationalError) as error:
                _error_operacion(form, error)
            else:
                messages.success(request, "Cotización registrada.")
                return redirect("cotizacion_detalle", pk=oferta.pk)
    return render(request, "cotizaciones/recibida.html", {"solicitud": solicitud, "form": form, "formset": formset})


@rol_requerido("Compras")
def cotizacion_detalle(request, pk):
    from .models import Cotizacion
    servicios_pedidos.exigir_compras(request.user)
    oferta = get_object_or_404(Cotizacion.objects.select_related("solicitud__proveedor").prefetch_related("detalles__detalle_solicitud"), pk=pk)
    return render(request, "cotizaciones/oferta_detalle.html", {"oferta": oferta})


@rol_requerido("Compras")
def cotizacion_comparar(request):
    servicios_pedidos.exigir_compras(request.user)
    form = ComparacionForm(request.GET)
    grupos = servicios_pedidos.comparar_cotizaciones(request.user, **form.cleaned_data) if form.is_valid() else []
    return render(request, "cotizaciones/comparar.html", {"form": form, "grupos": grupos})


# ---------- Administración ----------

@rol_requerido("Administrador")
def admin_dashboard(request):
    return render(request, "administracion/dashboard.html", {
        "cantidad_listados": ListadoFaltantes.objects.count(),
        "faltantes_pendientes": ItemFaltante.objects.filter(solicitado=False).count(),
        "cantidad_solicitudes": SolicitudCotizacion.objects.count(),
        "proveedores_activos": Proveedor.objects.filter(activo=True).count(),
        "cantidad_usuarios": User.objects.count(),
    })


@rol_requerido("Administrador")
def admin_usuario_lista(request):
    usuarios = User.objects.prefetch_related("groups").order_by("username")
    return render(request, "administracion/usuarios_lista.html", {"usuarios": usuarios})


@rol_requerido("Administrador")
def admin_usuario_form(request, pk=None):
    usuario = get_object_or_404(User, pk=pk) if pk is not None else None
    form = AdminUserForm(request.POST or None, instance=usuario)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
        messages.success(request, "Usuario guardado correctamente.")
        return redirect("admin_usuario_lista")
    return render(request, "administracion/usuario_form.html", {
        "form": form,
        "titulo": "Editar usuario" if usuario else "Nuevo usuario",
    })


@rol_requerido("Administrador")
@require_POST
def admin_usuario_estado(request, pk):
    usuario = get_object_or_404(User, pk=pk)
    if usuario.pk == request.user.pk:
        messages.error(request, "No podés desactivar tu propio usuario.")
    else:
        usuario.is_active = not usuario.is_active
        usuario.save(update_fields=["is_active"])
        messages.success(request, "Estado del usuario actualizado.")
    return redirect("admin_usuario_lista")


@rol_requerido("Administrador")
def admin_usuario_password(request, pk):
    usuario = get_object_or_404(User, pk=pk)
    form = AdminPasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario.set_password(form.cleaned_data["password"])
        usuario.save(update_fields=["password"])
        messages.success(request, "La contraseña se restableció correctamente.")
        return redirect("admin_usuario_lista")
    return render(request, "administracion/usuario_password.html", {"form": form, "usuario": usuario})


def _catalogo_config(tipo):
    configuracion = {
        "marcas": (Marca, MarcaAdminForm, "Marcas"),
        "modelos": (Modelo, ModeloAdminForm, "Modelos"),
        "sucursales": (Sucursal, SucursalAdminForm, "Sucursales"),
    }
    if tipo not in configuracion:
        raise PermissionDenied
    return configuracion[tipo]


@rol_requerido("Administrador")
def admin_catalogo_lista(request, tipo):
    modelo, _, titulo = _catalogo_config(tipo)
    return render(request, "administracion/catalogo_lista.html", {
        "tipo": tipo,
        "titulo": titulo,
        "registros": modelo.objects.all(),
    })


@rol_requerido("Administrador")
def admin_catalogo_form(request, tipo, pk=None):
    modelo, formulario, titulo = _catalogo_config(tipo)
    registro = get_object_or_404(modelo, pk=pk) if pk is not None else None
    form = formulario(request.POST or None, instance=registro)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{titulo[:-1] if titulo.endswith('s') else titulo} guardado correctamente.")
        return redirect("admin_catalogo_lista", tipo=tipo)
    return render(request, "administracion/catalogo_form.html", {
        "form": form,
        "titulo": f"Editar {titulo[:-1].lower()}" if registro else f"Nueva entrada en {titulo.lower()}",
        "tipo": tipo,
    })


def _catalogo_en_uso(tipo, registro):
    if tipo == "marcas":
        return registro.modelos.exists() or registro.proveedores.exists()
    if tipo == "modelos":
        return (registro.items_faltantes.exists() or registro.stock_set.exists()
                or registro.detalleventa_set.exists() or registro.detallesolicitudcotizacion_set.exists())
    return (registro.listadofaltantes_set.exists() or registro.stock_set.exists()
            or registro.venta_set.exists() or registro.usuariosucursal_set.exists())


@rol_requerido("Administrador")
@require_POST
def admin_catalogo_eliminar(request, tipo, pk):
    modelo, _, titulo = _catalogo_config(tipo)
    registro = get_object_or_404(modelo, pk=pk)
    if _catalogo_en_uso(tipo, registro):
        messages.error(request, "No se puede borrar este registro porque está en uso.")
    else:
        registro.delete()
        messages.success(request, "Registro borrado correctamente.")
    return redirect("admin_catalogo_lista", tipo=tipo)


@rol_requerido("Administrador")
def admin_operaciones(request):
    listados = ListadoFaltantes.objects.select_related("sucursal", "usuario").prefetch_related("items__modelo")
    solicitudes = servicios_pedidos.consultar_solicitudes(request.user)
    return render(request, "administracion/operaciones.html", {
        "listados": listados,
        "solicitudes": solicitudes,
    })


# ---------- Stock y ventas ----------


def _error_operacion(form, error):
    if isinstance(error, ValidationError):
        form.add_error(None, error)
    else:
        if not any(texto in str(error).lower() for texto in ("locked", "busy")):
            raise error
        form.add_error(None, "La base est\u00e1 ocupada. Reintente el mismo formulario.")


@rol_requerido("Ventas", "Compras", "Finanzas")
def stock_lista(request):
    form = ConsultaSucursalForm(request.GET, usuario=request.user)
    stock = servicios.consultar_stock(request.user)
    if form.is_valid():
        if form.cleaned_data["sucursal"]:
            stock = stock.filter(sucursal=form.cleaned_data["sucursal"])
    else:
        stock = stock.none()
    return render(request, "stock/lista.html", {"form": form, "stock": stock})


@rol_requerido("Administrador")
def stock_ajuste(request):
    form = AjusteStockForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            servicios.ajustar_stock(request.user, **form.cleaned_data)
        except (ValidationError, OperationalError) as error:
            _error_operacion(form, error)
        else:
            messages.success(request, "Stock actualizado.")
            return redirect("stock_lista")
    return render(request, "stock/ajuste.html", {"form": form})


@rol_requerido("Ventas")
def venta_nueva(request):
    sucursal = sucursal_ventas(request.user)
    form = VentaForm(request.POST if request.method == "POST" else None,
                     initial={"clave_operacion": uuid4()})
    formset = VentaFormSet(request.POST if request.method == "POST" else None, prefix="filas")
    if request.method == "POST":
        valido = form.is_valid()
        filas_validas = formset.is_valid()
        if valido and filas_validas:
            # Nunca aceptar una sucursal enviada por el cliente.
            if request.POST.get("sucursal") and request.POST["sucursal"] != str(sucursal.pk):
                raise PermissionDenied
            try:
                venta = servicios.registrar_venta(request.user, formset.filas_cargadas(), form.cleaned_data["clave_operacion"])
            except (ValidationError, OperationalError) as error:
                _error_operacion(form, error)
            else:
                messages.success(request, "Venta registrada.")
                return redirect("venta_detalle", pk=venta.pk)
    return render(request, "ventas/nueva.html", {"form": form, "formset": formset, "sucursal": sucursal})


@rol_requerido("Ventas", "Compras", "Finanzas")
def venta_lista(request):
    form = ConsultaSucursalForm(request.GET, usuario=request.user)
    ventas = servicios.consultar_ventas(request.user)
    if form.is_valid():
        if form.cleaned_data["sucursal"]:
            ventas = ventas.filter(sucursal=form.cleaned_data["sucursal"])
    else:
        ventas = ventas.none()
    return render(request, "ventas/lista.html", {"form": form, "ventas": ventas})


@rol_requerido("Ventas", "Compras", "Finanzas")
def venta_detalle(request, pk):
    venta = get_object_or_404(servicios.consultar_ventas(request.user), pk=pk)
    return render(request, "ventas/detalle.html", {"venta": venta, "detalles": venta.detalles.select_related("modelo__marca")})


@rol_requerido("Ventas", "Compras", "Finanzas")
def venta_resumen(request):
    datos = request.GET if request.GET else {"fecha": timezone.localdate()}
    form = ResumenVentasForm(datos, usuario=request.user)
    lineas = []
    periodo = ""
    if form.is_valid():
        lineas = servicios.resumen_ventas(request.user, **form.cleaned_data)
        periodo = servicios.quincena(form.cleaned_data["fecha"])
    return render(request, "ventas/resumen.html", {"form": form, "lineas": lineas, "periodo": periodo})
