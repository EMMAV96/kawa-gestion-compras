def roles(request):
    """Expone los roles (grupos) del usuario a las plantillas."""
    usuario = request.user
    if not usuario.is_authenticated:
        return {}
    nombres = set(usuario.groups.values_list("name", flat=True))
    if usuario.is_superuser:
        nombres |= {"Ventas", "Compras", "Finanzas", "Administrador"}
    return {"finanzas_autorizado": usuario.is_active and usuario.groups.filter(name="Finanzas").exists(), "roles": nombres, "rol_usuario": "Administrador" if usuario.is_superuser else ", ".join(sorted(nombres)) or "Sin rol"}
