from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from .models import Compra, Proveedor, ItemFaltante, Modelo, SolicitudCotizacion, Cotizacion


class ItemOrigenField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return f"Pedido {obj.listado_id} · {obj.listado.sucursal} · {obj.modelo} · {obj.cantidad} unidades"


class NuevaCompraForm(forms.Form):
    clave_operacion = forms.UUIDField(widget=forms.HiddenInput)
    procedimiento = forms.ChoiceField(choices=Compra.Procedimiento.choices)
    proveedor = forms.ModelChoiceField(queryset=Proveedor.objects.filter(activo=True, es_fijo=True), required=False,
                                     label="Proveedor habitual (procedimiento A)")
    items = ItemOrigenField(queryset=ItemFaltante.objects.select_related("listado__sucursal", "modelo__marca"),
                           required=False, widget=forms.CheckboxSelectMultiple)
    solicitud = forms.ModelChoiceField(queryset=SolicitudCotizacion.objects.all(), required=False,
                                      label="Solicitud de origen (procedimiento B)")


class PrecioCompraForm(forms.Form):
    modelo = forms.ModelChoiceField(queryset=Modelo.objects.select_related("marca"), required=False)
    precio = forms.DecimalField(required=False, min_value=Decimal("0.01"), max_digits=12, decimal_places=2)

    def clean(self):
        datos = super().clean()
        if bool(datos.get("modelo")) != (datos.get("precio") is not None):
            raise ValidationError("Complete modelo y precio acordado, o deje ambos vacíos.")
        return datos


class BasePreciosFormSet(forms.BaseFormSet):
    def clean(self):
        if any(self.errors):
            return
        modelos = [f.cleaned_data["modelo"].pk for f in self.forms if f.cleaned_data.get("modelo")]
        if len(modelos) != len(set(modelos)):
            raise ValidationError("Ingrese un solo precio por modelo.")

    def precios(self):
        return {f.cleaned_data["modelo"].pk: f.cleaned_data["precio"] for f in self.forms if f.cleaned_data.get("modelo")}


PreciosCompraFormSet = forms.formset_factory(PrecioCompraForm, formset=BasePreciosFormSet, extra=8)


class OfertaCompraForm(forms.Form):
    oferta = forms.ModelChoiceField(queryset=Cotizacion.objects.none())

    def __init__(self, *args, ofertas, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["oferta"].queryset = Cotizacion.objects.filter(pk__in=[o.pk for o in ofertas]).select_related("solicitud")
        self.fields["oferta"].label_from_instance = lambda o: f"Cotización {o.pk} · {o.solicitud.proveedor_nombre} · ARS {o.total}"


class DecisionCompraForm(forms.Form):
    resultado = forms.ChoiceField(choices=[(Compra.Estado.APROBADA, "Aprobar"), (Compra.Estado.RECHAZADA, "Rechazar")])
    motivo = forms.CharField(required=False, max_length=2000, widget=forms.Textarea(attrs={"rows": 3}),
                             help_text="Obligatorio al rechazar.")

    def clean(self):
        datos = super().clean()
        if datos.get("resultado") == Compra.Estado.RECHAZADA and not datos.get("motivo", "").strip():
            self.add_error("motivo", "Ingrese el motivo del rechazo.")
        return datos


class FiltroCompraForm(forms.Form):
    estado = forms.ChoiceField(required=False, choices=[("", "Todos los estados"), *Compra.Estado.choices])
