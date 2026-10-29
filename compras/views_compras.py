from uuid import uuid4
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import OperationalError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from . import servicios_compras as negocio
from .forms_compras import (NuevaCompraForm, PreciosCompraFormSet, OfertaCompraForm, DecisionCompraForm, FiltroCompraForm)
from .models import Compra, DocumentoCompra, DecisionFinanciera
from .servicios_pedidos import exigir_compras


def _error(error):
    if isinstance(error, ValidationError):
        return " ".join(error.messages)
    if not any(palabra in str(error).lower() for palabra in ("locked", "busy")):
        raise error
    return "La base está ocupada. Reintente la misma operación; se conservará su integridad."


@login_required
def compra_lista(request):
    compras = negocio.consultar_compras(request.user)
    form = FiltroCompraForm(request.GET)
    if form.is_valid():
        if form.cleaned_data["estado"]:
            compras = compras.filter(estado=form.cleaned_data["estado"])
    else:
        compras = compras.none()
    return render(request, "compras/lista.html", {"compras": compras, "form": form})


@login_required
def compra_nueva(request):
    exigir_compras(request.user)
    form = NuevaCompraForm(request.POST if request.method == "POST" else None, initial={"clave_operacion": uuid4(),
        "solicitud": request.GET.get("solicitud"), "procedimiento": request.GET.get("procedimiento", "HABITUAL")})
    precios = PreciosCompraFormSet(request.POST if request.method == "POST" else None, prefix="precios")
    if request.method == "POST":
        form_ok, precios_ok = form.is_valid(), precios.is_valid()
        if form_ok and precios_ok:
            try:
                compra = negocio.preparar_compra(request.user, **form.cleaned_data, precios=precios.precios())
            except (ValidationError, OperationalError) as error:
                form.add_error(None, _error(error))
            else:
                messages.success(request, "Compra preparada. Los pedidos de origen quedaron reservados.")
                return redirect("compra_detalle", pk=compra.pk)
    # El campo valida también reenvíos de una operación ya confirmada, pero la
    # pantalla solo ofrece necesidades sin reserva vigente.
    disponibles = negocio.necesidades_disponibles(request.user)
    return render(request, "compras/nueva.html", {"form": form, "precios": precios,
        "disponibles": disponibles, "seleccionados": request.POST.getlist("items")})


def _contexto_detalle(usuario, compra, decision_form=None):
    puede_preparar = usuario.is_superuser or usuario.groups.filter(name__in=["Compras", "Administrador"]).exists()
    ofertas = negocio.ofertas_para_compra(usuario, compra) if puede_preparar and compra.procedimiento == "COTIZACION" and not compra.cerrada else []
    return {"compra": compra, "detalles": compra.detalles.all(),
        "origenes": compra.origenes.select_related("item"), "movimientos": compra.movimientos.select_related("usuario"),
        "puede_preparar": puede_preparar, "puede_decidir": negocio.puede_decidir(usuario),
        "oferta_form": OfertaCompraForm(ofertas=ofertas), "ofertas": ofertas,
        "decision_form": decision_form or DecisionCompraForm()}


@login_required
def compra_detalle(request, pk):
    compra = get_object_or_404(negocio.consultar_compras(request.user), pk=pk)
    return render(request, "compras/detalle.html", _contexto_detalle(request.user, compra))


@login_required
@require_POST
def compra_accion(request, pk, accion):
    exigir_compras(request.user)
    compra = get_object_or_404(negocio.consultar_compras(request.user), pk=pk)
    try:
        if accion == "evaluar":
            negocio.evaluar_solicitud(request.user, compra)
        elif accion == "seleccionar":
            form = OfertaCompraForm(request.POST, ofertas=negocio.ofertas_para_compra(request.user, compra))
            if not form.is_valid():
                raise ValidationError("Seleccione una oferta completa y compatible.")
            negocio.seleccionar_oferta(request.user, compra, form.cleaned_data["oferta"])
        elif accion == "documentar":
            negocio.generar_documento(request.user, compra)
        elif accion == "solicitar":
            negocio.solicitar_aprobacion(request.user, compra)
        else:
            raise ValidationError("Acción desconocida.")
    except (ValidationError, OperationalError) as error:
        messages.error(request, _error(error))
    else:
        messages.success(request, "Operación completada.")
    return redirect("compra_detalle", pk=pk)


@login_required
def documento_compra(request, pk):
    compra = get_object_or_404(negocio.consultar_compras(request.user), pk=pk)
    documento = get_object_or_404(DocumentoCompra, compra=compra)
    return render(request, "compras/documento.html", {"documento": documento})


@login_required
def finanzas_bandeja(request):
    negocio.exigir_finanzas(request.user)
    return render(request, "compras/bandeja.html", {"compras": negocio.consultar_compras(request.user).filter(estado=Compra.Estado.PENDIENTE_APROBACION)})


@login_required
def finanzas_historial(request):
    negocio.exigir_finanzas(request.user)
    return render(request, "compras/decisiones.html", {"decisiones": DecisionFinanciera.objects.select_related("compra", "usuario").order_by("-pk")})


@login_required
@require_POST
def compra_decidir(request, pk):
    negocio.exigir_finanzas(request.user)
    compra = get_object_or_404(negocio.consultar_compras(request.user), pk=pk)
    form = DecisionCompraForm(request.POST)
    if form.is_valid():
        try:
            negocio.decidir_compra(request.user, compra, **form.cleaned_data)
        except (ValidationError, OperationalError) as error:
            form.add_error(None, _error(error))
        else:
            messages.success(request, "Decisión financiera registrada.")
            return redirect("compra_detalle", pk=pk)
    compra.refresh_from_db()
    return render(request, "compras/detalle.html", _contexto_detalle(request.user, compra, form))
