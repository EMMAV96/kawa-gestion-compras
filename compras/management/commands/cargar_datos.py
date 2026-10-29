import os
from django.conf import settings
from django.core.management.base import CommandError
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand

from compras.models import Marca, Modelo, Sucursal, UsuarioSucursal

USUARIOS = [
    ("ventas01", "Ventas"),
    ("compras01", "Compras"),
    ("finanzas01", "Finanzas"),
    ("admin01", "Administrador"),
]


class Command(BaseCommand):
    help = "Crea datos locales con KAWA_LOCAL_DEMO_PASSWORD, sin clave predeterminada."

    def handle(self, *args, **opciones):
        if settings.SETTINGS_MODULE == "config.production" or getattr(settings, "KAWA_PUBLIC_DEMO", False):
            raise CommandError("El cargador local no está habilitado en producción.")
        password = getattr(settings, "KAWA_LOCAL_DEMO_PASSWORD", "") or os.environ.get("KAWA_LOCAL_DEMO_PASSWORD", "")
        if len(password) < 12:
            raise CommandError("Configure una clave local exclusiva de al menos 12 caracteres en KAWA_LOCAL_DEMO_PASSWORD.")
        usuarios_creados = set()
        for nombre_usuario, rol in USUARIOS:
            grupo, _ = Group.objects.get_or_create(name=rol)
            usuario, creado = User.objects.get_or_create(username=nombre_usuario)
            if creado:
                usuario.set_password(password)
                usuario.save()
                usuario.groups.set([grupo])
                usuarios_creados.add(nombre_usuario)

        if not Sucursal.objects.exists():
            for nombre in ("Rosario", "Córdoba", "Mendoza"):
                Sucursal.objects.create(nombre=nombre)
        if not Marca.objects.exists():
            x = Marca.objects.create(nombre="Marca X")
            y = Marca.objects.create(nombre="Marca Y")
            Modelo.objects.create(nombre="Modelo A", marca=x)
            Modelo.objects.create(nombre="Modelo B", marca=y)
            Modelo.objects.create(nombre="Modelo C", marca=x)
        # Solo el usuario de demostracion recibe una asignacion predeterminada;
        # nunca inferir la sucursal de usuarios reales ni reemplazar una existente.
        ventas = User.objects.get(username="ventas01")
        sucursal = Sucursal.objects.filter(nombre="Rosario").first()
        if sucursal and "ventas01" in usuarios_creados:
            UsuarioSucursal.objects.get_or_create(usuario=ventas, defaults={"sucursal": sucursal})
        self.stdout.write(self.style.SUCCESS("Datos de demostración listos."))
