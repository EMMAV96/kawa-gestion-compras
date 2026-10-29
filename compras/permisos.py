from django.core.exceptions import PermissionDenied


def exigir_rol(usuario, *roles):
    if not usuario.is_authenticated or not usuario.is_active:
        raise PermissionDenied
    if not (usuario.is_superuser or usuario.groups.filter(name__in=roles).exists()):
        raise PermissionDenied


def es_administrador(usuario):
    return usuario.is_superuser or usuario.groups.filter(name="Administrador").exists()


def sucursal_ventas(usuario):
    exigir_rol(usuario, "Ventas")
    from .models import UsuarioSucursal
    asignacion = UsuarioSucursal.objects.filter(usuario=usuario).select_related("sucursal").first()
    if asignacion is None:
        raise PermissionDenied("Debe solicitar al Administrador una sucursal antes de registrar ventas.")
    return asignacion.sucursal


def sucursales_visibles(usuario):
    exigir_rol(usuario, "Ventas", "Compras", "Finanzas", "Administrador")
    from .models import Sucursal, UsuarioSucursal
    if es_administrador(usuario) or usuario.groups.filter(name__in=["Compras", "Finanzas"]).exists():
        return Sucursal.objects.all()
    return Sucursal.objects.filter(pk__in=UsuarioSucursal.objects.filter(usuario=usuario).values("sucursal_id"))
