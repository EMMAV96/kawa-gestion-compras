from decimal import Decimal

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError

from .models import DetalleSolicitudCotizacion, UsuarioSucursal, ItemFaltante, Marca, Modelo, Proveedor, SolicitudCotizacion, Sucursal


class LoginForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Usuario o contraseña incorrectos",
    }


class ProveedorForm(forms.ModelForm):
    marcas = forms.ModelMultipleChoiceField(
        queryset=Marca.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label="Marcas que abastece",
        error_messages={"required": "Seleccione al menos una marca"},
    )

    class Meta:
        model = Proveedor
        fields = ["razon_social", "email", "es_fijo", "marcas"]
        error_messages = {
            "razon_social": {"required": "Ingrese la razón social"},
            "email": {"required": "Ingrese el email", "invalid": "Ingrese un email válido"},
        }


class ListadoForm(forms.Form):
    sucursal = forms.ModelChoiceField(
        queryset=Sucursal.objects.all(),
        empty_label="Elegir sucursal",
        error_messages={"required": "Seleccione la sucursal"},
    )

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        if usuario is not None:
            from .permisos import es_administrador
            from .models import UsuarioSucursal
            if not es_administrador(usuario):
                asignacion = UsuarioSucursal.objects.filter(usuario=usuario).first()
                self.fields["sucursal"].disabled = True
                self.fields["sucursal"].initial = asignacion.sucursal_id if asignacion else None
                self.fields["sucursal"].queryset = Sucursal.objects.filter(pk=asignacion.sucursal_id) if asignacion else Sucursal.objects.none()


class ModeloChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.nombre} · {obj.marca.nombre}"


class ItemForm(forms.Form):
    modelo = ModeloChoiceField(
        queryset=Modelo.objects.select_related("marca"), required=False,
        empty_label="Elegir modelo", widget=forms.Select(attrs={"aria-label": "Modelo"}))
    cantidad = forms.IntegerField(
        required=False, min_value=1,
        widget=forms.NumberInput(attrs={"aria-label": "Cantidad", "class": "cantidad", "min": 1}))
    motivo = forms.ChoiceField(
        required=False, choices=ItemFaltante.Motivo.choices, initial=ItemFaltante.Motivo.VENTA,
        widget=forms.Select(attrs={"aria-label": "Motivo"}))

    def clean(self):
        datos = super().clean()
        if datos.get("modelo") and not datos.get("cantidad") and "cantidad" not in self.errors:
            self.add_error("cantidad", "Ingrese la cantidad")
        if datos.get("cantidad") and not datos.get("modelo"):
            self.add_error("modelo", "Elija el modelo")
        if not datos.get("motivo"):
            datos["motivo"] = ItemFaltante.Motivo.VENTA
        return datos


class BaseItemFormSet(forms.BaseFormSet):
    def clean(self):
        if any(self.errors):
            return
        cargadas = [f for f in self.forms if f.cleaned_data.get("modelo") and f.cleaned_data.get("cantidad")]
        if not cargadas:
            raise ValidationError("Debe cargar al menos un modelo")

    def filas_cargadas(self):
        return [f.cleaned_data for f in self.forms
                if f.cleaned_data.get("modelo") and f.cleaned_data.get("cantidad")]


ItemFormSet = forms.formset_factory(ItemForm, formset=BaseItemFormSet, extra=8)


class ProveedorChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.razon_social} ({'fijo' if obj.es_fijo else 'no fijo'})"


class SolicitudForm(forms.Form):
    clave_operacion = forms.UUIDField(required=False, widget=forms.HiddenInput)
    quincena = forms.DateField(required=False, label="Fecha de la quincena (opcional)",
                              widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    modelos = forms.ModelMultipleChoiceField(
        queryset=Modelo.objects.all(),
        error_messages={"required": "Seleccione al menos un modelo"},
    )
    proveedores = ProveedorChoiceField(
        queryset=Proveedor.objects.filter(activo=True),
        widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "Seleccione al menos un proveedor"},
    )
    medio = forms.ChoiceField(choices=SolicitudCotizacion.Medio.choices, label="Medio de envío")


ROLES = ("Ventas", "Compras", "Finanzas", "Administrador")


class AdminUserForm(forms.ModelForm):
    sucursal = forms.ModelChoiceField(queryset=Sucursal.objects.all(), required=False,
                                     help_text="Obligatoria para el rol Ventas.")
    rol = forms.ChoiceField(choices=[(rol, rol) for rol in ROLES], label="Rol")
    password = forms.CharField(
        label="Contraseña inicial", required=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email", "is_active")
        labels = {
            "username": "Nombre de usuario",
            "first_name": "Nombre",
            "last_name": "Apellido",
            "email": "Email",
            "is_active": "Usuario activo",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            asignacion = UsuarioSucursal.objects.filter(usuario=self.instance).first()
            self.fields["sucursal"].initial = asignacion.sucursal_id if asignacion else None
            self.fields["rol"].initial = (
                "Administrador" if self.instance.is_superuser
                else self.instance.groups.first().name if self.instance.groups.exists()
                else ""
            )
        else:
            self.fields["password"].required = True
            self.fields["rol"].initial = "Ventas"

    def clean(self):
        datos = super().clean()
        if datos.get("rol") == "Ventas" and not datos.get("sucursal"):
            self.add_error("sucursal", "Seleccione la sucursal del usuario de Ventas.")
        return datos

    def save(self, commit=True):
        usuario = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            usuario.set_password(password)
        if commit:
            usuario.save()
            grupo, _ = Group.objects.get_or_create(name=self.cleaned_data["rol"])
            usuario.groups.set([grupo])
            sucursal = self.cleaned_data.get("sucursal")
            if sucursal:
                UsuarioSucursal.objects.update_or_create(usuario=usuario, defaults={"sucursal": sucursal})
            else:
                UsuarioSucursal.objects.filter(usuario=usuario).delete()
        return usuario


class AdminPasswordForm(forms.Form):
    password = forms.CharField(
        label="Nueva contraseña", min_length=8,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    confirmar = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean(self):
        datos = super().clean()
        if datos.get("password") != datos.get("confirmar"):
            self.add_error("confirmar", "Las contraseñas no coinciden.")
        return datos


class MarcaAdminForm(forms.ModelForm):
    class Meta:
        model = Marca
        fields = ("nombre",)
        labels = {"nombre": "Nombre"}


class ModeloAdminForm(forms.ModelForm):
    class Meta:
        model = Modelo
        fields = ("nombre", "marca")
        labels = {"nombre": "Nombre", "marca": "Marca"}


class SucursalAdminForm(forms.ModelForm):
    class Meta:
        model = Sucursal
        fields = ("nombre",)
        labels = {"nombre": "Nombre"}


class VentaForm(forms.Form):
    clave_operacion = forms.UUIDField(widget=forms.HiddenInput)


class LineaVentaForm(ItemForm):
    motivo = None


VentaFormSet = forms.formset_factory(LineaVentaForm, formset=BaseItemFormSet, extra=8)


class AjusteStockForm(forms.Form):
    sucursal = forms.ModelChoiceField(queryset=Sucursal.objects.all())
    modelo = ModeloChoiceField(queryset=Modelo.objects.select_related("marca"))
    variacion = forms.IntegerField(label="Unidades a agregar o quitar", min_value=-2147483647, max_value=2147483647,
                                  help_text="Positivo para carga inicial o aumento; negativo para disminución.")
    motivo = forms.CharField(max_length=250)

    def clean_variacion(self):
        valor = self.cleaned_data["variacion"]
        if valor == 0:
            raise ValidationError("La variación no puede ser cero.")
        return valor


class ConsultaSucursalForm(forms.Form):
    sucursal = forms.ModelChoiceField(queryset=Sucursal.objects.none(), required=False, empty_label="Todas las sucursales habilitadas")

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        from .permisos import sucursales_visibles
        self.fields["sucursal"].queryset = sucursales_visibles(usuario)


class ResumenVentasForm(ConsultaSucursalForm):
    fecha = forms.DateField(label="Fecha de la quincena", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))


class FiltroPedidosForm(forms.Form):
    sucursal = forms.ModelChoiceField(queryset=Sucursal.objects.none(), required=False, empty_label="Todas las sucursales habilitadas")
    fecha = forms.DateField(required=False, label="Fecha exacta", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    quincena = forms.DateField(required=False, label="Fecha de la quincena", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    pendientes = forms.BooleanField(required=False, label="Solo pendientes de solicitud")

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        from .servicios_pedidos import sucursales_pedidos
        self.fields["sucursal"].queryset = sucursales_pedidos(usuario)


class CotizacionRecibidaForm(forms.Form):
    fecha = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))


class LineaCotizacionForm(forms.Form):
    detalle_solicitud = forms.ModelChoiceField(queryset=DetalleSolicitudCotizacion.objects.none(), widget=forms.HiddenInput)
    cantidad = forms.IntegerField(required=False, min_value=1)
    precio_unitario = forms.DecimalField(required=False, min_value=Decimal("0.01"), max_digits=12, decimal_places=2)

    def __init__(self, *args, solicitud, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["detalle_solicitud"].queryset = solicitud.detalles.all()
        valor = self.data.get(self.add_prefix("detalle_solicitud")) if self.is_bound else self.initial.get("detalle_solicitud")
        self.linea = self.fields["detalle_solicitud"].queryset.filter(pk=valor).first() if str(valor).isdigit() else None

    def clean(self):
        datos = super().clean()
        cantidad, precio = datos.get("cantidad"), datos.get("precio_unitario")
        if (cantidad is not None or precio is not None) and (cantidad is None or precio is None):
            raise ValidationError("Complete cantidad y precio, o deje ambos vacíos para omitir el modelo.")
        if cantidad and datos.get("detalle_solicitud") and cantidad > datos["detalle_solicitud"].cantidad:
            self.add_error("cantidad", "La cantidad supera la solicitada.")
        return datos


class BaseCotizacionFormSet(forms.BaseFormSet):
    def clean(self):
        if any(self.errors):
            return
        filas = self.filas_cargadas()
        if not filas:
            raise ValidationError("Debe registrar al menos un modelo cotizado.")
        ids = [f["detalle_solicitud"].pk for f in filas]
        if len(ids) != len(set(ids)):
            raise ValidationError("No repita un modelo en la cotización.")

    def filas_cargadas(self):
        return [f.cleaned_data for f in self.forms if f.cleaned_data.get("cantidad") and f.cleaned_data.get("precio_unitario")]


CotizacionFormSet = forms.formset_factory(LineaCotizacionForm, formset=BaseCotizacionFormSet, extra=0)


class ComparacionForm(forms.Form):
    solicitud = forms.ModelChoiceField(queryset=SolicitudCotizacion.objects.all(), required=False,
                                     empty_label="Todas las cestas de modelos y cantidades")
