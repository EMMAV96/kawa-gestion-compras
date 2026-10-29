from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch
from django.contrib.auth.models import User, Group, AnonymousUser
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import IntegrityError, transaction
from django.test import TestCase, SimpleTestCase
from django.urls import reverse
from django.utils import timezone
from . import servicios_compras as negocio, servicios_pedidos as pedidos
from .models import (Compra, DetalleCompra, OrigenCompra, DocumentoCompra, DecisionFinanciera,
                     MovimientoCompra, Marca, Modelo, Sucursal, UsuarioSucursal, Proveedor,
                     Stock, Venta, ItemFaltante, Cotizacion)


class ComprasTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sucursal = Sucursal.objects.create(nombre="Rosario")
        cls.marca = Marca.objects.create(nombre="Marca K")
        cls.modelo = Modelo.objects.create(nombre="Moto A", marca=cls.marca)
        cls.otro = Modelo.objects.create(nombre="Moto B", marca=cls.marca)
        cls.proveedor = Proveedor.objects.create(razon_social="Habitual", email="h@e.com", es_fijo=True)
        cls.alternativo = Proveedor.objects.create(razon_social="Alternativo", email="a@e.com")
        for proveedor in [cls.proveedor, cls.alternativo]:
            proveedor.marcas.add(cls.marca)
        for nombre, rol in [("compras", "Compras"), ("ventas", "Ventas"), ("finanzas", "Finanzas"), ("admin", "Administrador"), ("otro_finanzas", "Finanzas"), ("sin_rol", None)]:
            usuario = User.objects.create_user(nombre)
            if rol:
                usuario.groups.add(Group.objects.get_or_create(name=rol)[0])
            setattr(cls, nombre, usuario)
        cls.superusuario = User.objects.create_superuser("super")
        UsuarioSucursal.objects.create(usuario=cls.ventas, sucursal=cls.sucursal)
        Stock.objects.create(sucursal=cls.sucursal, modelo=cls.modelo, cantidad=10)

    def item(self, cantidad=3, modelo=None):
        return pedidos.registrar_pedido(self.ventas, [{"modelo": modelo or self.modelo, "cantidad": cantidad}]).items.get()

    def habitual(self, items=None, clave=None, proveedor=None, precios=None):
        items = items if items is not None else [self.item()]
        return negocio.preparar_compra(self.compras, "HABITUAL", clave or uuid4(),
            proveedor=proveedor or self.proveedor, items=items,
            precios=precios if precios is not None else {self.modelo.pk: "12.50"})

    def solicitud(self, items=None, proveedores=None):
        items = items or [self.item()]
        emision = pedidos.emitir_solicitudes(self.compras, list({i.modelo_id: i.modelo for i in items}.values()),
            proveedores or [self.alternativo], "MAIL", uuid4())
        return emision.solicitudes.order_by("pk").first()

    def cotizar(self, solicitud, parcial=False, precio="10.25"):
        filas = [{"detalle_solicitud": d, "cantidad": d.cantidad - 1 if parcial else d.cantidad,
                  "precio_unitario": precio} for d in solicitud.detalles.all()]
        return pedidos.registrar_cotizacion(self.compras, solicitud, timezone.localdate(), filas)

    def mediante_oferta(self):
        solicitud = self.solicitud()
        oferta = self.cotizar(solicitud)
        compra = negocio.preparar_compra(self.compras, "COTIZACION", uuid4(), solicitud=solicitud)
        compra = negocio.evaluar_solicitud(self.compras, compra)
        return negocio.seleccionar_oferta(self.compras, compra, oferta)

    def pendiente(self, compra=None):
        compra = compra or self.habitual()
        negocio.generar_documento(self.compras, compra)
        return negocio.solicitar_aprobacion(self.compras, compra)

    def test_habitual_reserva_y_copia_varios_modelos(self):
        a, b = self.item(2), self.item(4, self.otro)
        compra = self.habitual([a, b], precios={self.modelo.pk: "1.10", self.otro.pk: "2.20"})
        self.assertEqual(compra.estado, Compra.Estado.EN_PREPARACION)
        self.assertEqual(compra.total, Decimal("11.00"))
        self.assertEqual(compra.detalles.count(), 2)
        self.assertEqual(compra.origenes.count(), 2)
        self.assertFalse(negocio.necesidades_disponibles(self.compras).exists())
        self.assertFalse(ItemFaltante.objects.filter(solicitado=True).exists())

    def test_nota_numeracion_y_reenvio_documental(self):
        compra = self.habitual()
        documento = negocio.generar_documento(self.compras, compra)
        self.assertEqual(documento.tipo, "NOTA_PEDIDO")
        self.assertEqual(documento.contenido["total"], "37.50")
        self.assertEqual(negocio.generar_documento(self.compras, compra).pk, documento.pk)
        otra = negocio.generar_documento(self.compras, self.habitual())
        self.assertNotEqual(documento.numero, otra.numero)
        compra.refresh_from_db()
        self.assertEqual(compra.estado, "DOCUMENTACION_PREPARADA")
        self.assertEqual(DocumentoCompra.objects.count(), 2)

    def test_procedimiento_b_completo_y_orden(self):
        compra = self.mediante_oferta()
        self.assertEqual(compra.estado, "EN_EVALUACION")
        self.assertEqual(compra.total, Decimal("30.75"))
        self.assertEqual(compra.proveedor, self.alternativo)
        documento = negocio.generar_documento(self.compras, compra)
        self.assertEqual(documento.tipo, "ORDEN_COMPRA")
        self.assertEqual(documento.contenido["cotizacion"], compra.cotizacion_id)
        compra = negocio.solicitar_aprobacion(self.compras, compra)
        self.assertEqual(negocio.decidir_compra(self.finanzas, compra, "APROBADA").estado, "APROBADA")

    def test_espera_real_y_evaluacion_al_recibir(self):
        solicitud = self.solicitud()
        compra = negocio.preparar_compra(self.compras, "COTIZACION", uuid4(), solicitud=solicitud)
        self.assertIsNone(compra.total)
        compra = negocio.evaluar_solicitud(self.compras, compra)
        self.assertEqual(compra.estado, "PENDIENTE_COTIZACIONES")
        self.cotizar(solicitud)
        compra = negocio.evaluar_solicitud(self.compras, compra)
        self.assertEqual(compra.estado, "EN_EVALUACION")
        self.assertEqual(compra.movimientos.count(), 3)

    def test_proveedor_inactivo_no_habitual_o_marcas_incompatibles(self):
        item = self.item()
        for campo in ["activo", "es_fijo"]:
            Proveedor.objects.filter(pk=self.proveedor.pk).update(**{campo: False})
            with self.assertRaises(ValidationError):
                self.habitual([item])
            Proveedor.objects.filter(pk=self.proveedor.pk).update(**{campo: True})
        self.proveedor.marcas.clear()
        with self.assertRaises(ValidationError):
            self.habitual([item])
        self.assertFalse(Compra.objects.exists())
        self.assertFalse(OrigenCompra.objects.exists())

    def test_precios_cantidades_y_modelos_adicionales(self):
        item = self.item()
        for precio in ["0", "-2", "NaN", "Infinity", "1.001", "10000000000.00"]:
            with self.subTest(precio=precio), self.assertRaises(ValidationError):
                self.habitual([item], precios={self.modelo.pk: precio})
        for precios in [{}, {self.otro.pk: "2"}]:
            with self.assertRaises(ValidationError):
                self.habitual([item], precios=precios)
        ItemFaltante.objects.filter(pk=item.pk).update(cantidad=0)
        with self.assertRaises(ValidationError):
            self.habitual([item])
        self.assertFalse(Compra.objects.exists())

    def test_oferta_incompleta_no_se_puede_seleccionar(self):
        solicitud = self.solicitud()
        oferta = self.cotizar(solicitud, parcial=True)
        compra = negocio.preparar_compra(self.compras, "COTIZACION", uuid4(), solicitud=solicitud)
        compra = negocio.evaluar_solicitud(self.compras, compra)
        with self.assertRaises(ValidationError):
            negocio.seleccionar_oferta(self.compras, compra, oferta)
        with self.assertRaises(ValidationError):
            negocio.generar_documento(self.compras, compra)
        self.assertIsNone(compra.cotizacion_id)

    def test_oferta_de_otra_necesidad_aunque_cesta_igual_se_rechaza(self):
        solicitud = self.solicitud()
        compra = negocio.preparar_compra(self.compras, "COTIZACION", uuid4(), solicitud=solicitud)
        self.cotizar(solicitud)
        compra = negocio.evaluar_solicitud(self.compras, compra)
        otra = self.solicitud()
        oferta = self.cotizar(otra)
        with self.assertRaises(ValidationError):
            negocio.seleccionar_oferta(self.compras, compra, oferta)

    def test_puede_elegir_otro_proveedor_de_la_misma_emision(self):
        solicitud = self.solicitud(proveedores=[self.proveedor, self.alternativo])
        otra = solicitud.emision.solicitudes.exclude(pk=solicitud.pk).get()
        oferta = self.cotizar(otra)
        compra = negocio.preparar_compra(self.compras, "COTIZACION", uuid4(), solicitud=solicitud)
        compra = negocio.evaluar_solicitud(self.compras, compra)
        compra = negocio.seleccionar_oferta(self.compras, compra, oferta)
        self.assertEqual(compra.proveedor_id, otra.proveedor_id)

    def test_pedidos_modificados_no_se_presentan_como_cesta_original(self):
        solicitud = self.solicitud()
        ItemFaltante.objects.update(cantidad=9)
        with self.assertRaises(ValidationError):
            negocio.preparar_compra(self.compras, "COTIZACION", uuid4(), solicitud=solicitud)

    def test_reenvio_de_creacion_no_reserva_ni_duplica(self):
        item, clave = self.item(), uuid4()
        compra = self.habitual([item], clave)
        self.assertEqual(self.habitual([item], clave).pk, compra.pk)
        self.assertEqual(Compra.objects.count(), 1)
        with self.assertRaises(ValidationError):
            self.habitual([item], clave, precios={self.modelo.pk: "99"})
        with self.assertRaises(ValidationError):
            self.habitual([item])
        self.assertEqual(OrigenCompra.objects.count(), 1)

    def test_misma_necesidad_no_admite_procedimientos_simultaneos(self):
        solicitud = self.solicitud()
        self.habitual(list(solicitud.items.all()))
        with self.assertRaises(ValidationError):
            negocio.preparar_compra(self.compras, "COTIZACION", uuid4(), solicitud=solicitud)
        self.assertEqual(Compra.objects.count(), 1)

    def test_fallo_parcial_revierte_compra_reserva_y_detalles(self):
        item = self.item()
        with patch("compras.servicios_compras.DetalleCompra.objects.bulk_create", side_effect=RuntimeError("fallo")):
            with self.assertRaises(RuntimeError):
                self.habitual([item])
        self.assertFalse(Compra.objects.exists())
        self.assertFalse(OrigenCompra.objects.exists())
        self.assertEqual(negocio.necesidades_disponibles(self.compras).count(), 1)

    def test_solicitar_aprobacion_y_bandeja_sin_duplicados(self):
        compra = self.pendiente()
        self.assertEqual(negocio.solicitar_aprobacion(self.compras, compra).estado, "PENDIENTE_APROBACION")
        self.assertEqual(compra.movimientos.count(), 3)
        self.client.force_login(self.finanzas)
        self.assertContains(self.client.get(reverse("finanzas_bandeja")), "Habitual")

    def test_aprobar_no_modifica_stock_ni_ventas(self):
        antes = list(Stock.objects.values())
        compra = negocio.decidir_compra(self.finanzas, self.pendiente(), "APROBADA")
        self.assertTrue(compra.cerrada)
        self.assertEqual(compra.decision.usuario, self.finanzas)
        self.assertEqual(list(Stock.objects.values()), antes)
        self.assertFalse(Venta.objects.exists())
        self.assertTrue(compra.origenes.get().vigente)

    def test_rechazo_requiere_motivo_y_libera_con_historia(self):
        compra = self.pendiente()
        with self.assertRaises(ValidationError):
            negocio.decidir_compra(self.finanzas, compra, "RECHAZADA", " ")
        self.assertFalse(DecisionFinanciera.objects.exists())
        compra = negocio.decidir_compra(self.finanzas, compra, "RECHAZADA", "Fuera de presupuesto")
        self.assertEqual(compra.decision.motivo, "Fuera de presupuesto")
        self.assertFalse(compra.origenes.get().vigente)
        nueva = self.habitual([compra.origenes.get().item])
        self.assertNotEqual(nueva.pk, compra.pk)
        self.assertEqual(DocumentoCompra.objects.filter(compra=compra).count(), 1)
        self.assertEqual(compra.origenes.count(), 1)

    def test_admin_y_superusuario_sin_finanzas_no_deciden(self):
        compra = self.pendiente()
        for usuario in [self.admin, self.superusuario, self.compras, self.ventas, self.sin_rol, AnonymousUser()]:
            with self.assertRaises(PermissionDenied):
                negocio.decidir_compra(usuario, compra, "APROBADA")
        self.superusuario.groups.add(Group.objects.get(name="Finanzas"))
        self.assertEqual(negocio.decidir_compra(self.superusuario, compra, "APROBADA").estado, "APROBADA")

    def test_finanzas_inactivo_no_puede_decidir(self):
        compra = self.pendiente()
        self.finanzas.is_active = False
        with self.assertRaises(PermissionDenied):
            negocio.decidir_compra(self.finanzas, compra, "APROBADA")

    def test_decision_duplicada_y_compra_cerrada_inmutables(self):
        compra = negocio.decidir_compra(self.finanzas, self.pendiente(), "APROBADA")
        version = compra.version
        for operacion in [lambda: negocio.decidir_compra(self.otro_finanzas, compra, "RECHAZADA", "Otro"),
                          lambda: negocio.solicitar_aprobacion(self.compras, compra),
                          lambda: negocio.evaluar_solicitud(self.compras, compra)]:
            with self.assertRaises(ValidationError):
                operacion()
        compra.refresh_from_db()
        self.assertEqual(compra.version, version)
        self.assertEqual(compra.estado, "APROBADA")
        self.assertEqual(DecisionFinanciera.objects.count(), 1)

    def test_transiciones_invalidas(self):
        compra = self.habitual()
        for operacion in [lambda: negocio.solicitar_aprobacion(self.compras, compra),
                          lambda: negocio.decidir_compra(self.finanzas, compra, "APROBADA"),
                          lambda: negocio.evaluar_solicitud(self.compras, compra)]:
            with self.assertRaises(ValidationError):
                operacion()
        self.assertFalse(DecisionFinanciera.objects.exists())
        self.assertFalse(DocumentoCompra.objects.exists())

    def test_documento_incorrecto_impide_envio_y_decision(self):
        compra = self.habitual()
        documento = negocio.generar_documento(self.compras, compra)
        DocumentoCompra.objects.filter(pk=documento.pk).update(tipo="ORDEN_COMPRA")
        with self.assertRaises(ValidationError):
            negocio.solicitar_aprobacion(self.compras, compra)
        DocumentoCompra.objects.filter(pk=documento.pk).update(tipo="NOTA_PEDIDO")
        compra = negocio.solicitar_aprobacion(self.compras, compra)
        DocumentoCompra.objects.filter(pk=documento.pk).update(tipo="ORDEN_COMPRA")
        with self.assertRaises(ValidationError):
            negocio.decidir_compra(self.finanzas, compra, "APROBADA")
        self.assertFalse(DecisionFinanciera.objects.exists())

    def test_fallo_decision_revierte_estado_version_y_reserva(self):
        compra = self.pendiente()
        version = compra.version
        with patch("compras.servicios_compras.MovimientoCompra.objects.create", side_effect=RuntimeError("fallo")):
            with self.assertRaises(RuntimeError):
                negocio.decidir_compra(self.finanzas, compra, "RECHAZADA", "Motivo")
        compra.refresh_from_db()
        self.assertEqual(compra.estado, "PENDIENTE_APROBACION")
        self.assertEqual(compra.version, version)
        self.assertTrue(compra.origenes.get().vigente)
        self.assertFalse(DecisionFinanciera.objects.exists())

    def test_historia_y_documento_no_cambian_con_catalogos_o_pedidos(self):
        compra = self.habitual()
        documento = negocio.generar_documento(self.compras, compra)
        original = documento.contenido
        Modelo.objects.filter(pk=self.modelo.pk).update(nombre="Cambio")
        Proveedor.objects.filter(pk=self.proveedor.pk).update(razon_social="Otro nombre", email="otro@e.com")
        ItemFaltante.objects.update(cantidad=99)
        Sucursal.objects.update(nombre="Otra sucursal")
        documento.refresh_from_db()
        compra.refresh_from_db()
        self.assertEqual(documento.contenido, original)
        self.assertEqual(compra.detalles.get().nombre_modelo, "Moto A")
        self.assertEqual(compra.proveedor_nombre, "Habitual")
        self.client.force_login(self.finanzas)
        respuesta = self.client.get(reverse("documento_compra", args=[compra.pk]))
        self.assertContains(respuesta, "Moto A")
        self.assertNotContains(respuesta, "Otra sucursal")

    def test_permisos_preparacion_y_consulta(self):
        item = self.item()
        for usuario in [self.finanzas, self.ventas, self.sin_rol]:
            with self.assertRaises(PermissionDenied):
                negocio.preparar_compra(usuario, "HABITUAL", uuid4(), proveedor=self.proveedor,
                    items=[item], precios={self.modelo.pk: "1"})
        for usuario in [self.ventas, self.sin_rol]:
            with self.assertRaises(PermissionDenied):
                negocio.consultar_compras(usuario)

    def test_restricciones_sql_y_admin_solo_lectura(self):
        compra = self.pendiente()
        with self.assertRaises(IntegrityError), transaction.atomic():
            DocumentoCompra.objects.create(compra=self.habitual(), numero=compra.documento.numero,
                tipo="NOTA_PEDIDO", contenido={})
        with self.assertRaises(IntegrityError), transaction.atomic():
            DetalleCompra.objects.filter(compra=compra).update(cantidad=0)
        from django.contrib import admin
        from django.test import RequestFactory
        request = RequestFactory().get("/admin/")
        request.user = self.superusuario
        for modelo in [Compra, DetalleCompra, OrigenCompra, DocumentoCompra, DecisionFinanciera, MovimientoCompra]:
            configuracion = admin.site._registry[modelo]
            self.assertFalse(configuracion.has_add_permission(request))
            self.assertFalse(configuracion.has_change_permission(request))
            self.assertFalse(configuracion.has_delete_permission(request))

    def test_rutas_finanzas_no_conceden_bypass_a_admin_o_super(self):
        compra = self.pendiente()
        for usuario in [self.admin, self.superusuario, self.compras, self.ventas]:
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(reverse("finanzas_bandeja")).status_code, 403)
            self.assertEqual(self.client.get(reverse("finanzas_historial")).status_code, 403)
            self.assertEqual(self.client.post(reverse("compra_decidir", args=[compra.pk]), {"resultado": "APROBADA"}).status_code, 403)
            self.assertNotContains(self.client.get(reverse("panel")), "Aprobaciones pendientes")
        self.assertFalse(DecisionFinanciera.objects.exists())

    def test_recorrido_habitual_por_pantallas_y_solo_post(self):
        item = self.item()
        self.client.force_login(self.compras)
        ruta = reverse("compra_nueva")
        self.assertEqual(self.client.get(ruta).status_code, 200)
        datos = {"clave_operacion": uuid4(), "procedimiento": "HABITUAL", "proveedor": self.proveedor.pk,
            "items": [item.pk], "precios-TOTAL_FORMS": 1, "precios-INITIAL_FORMS": 0,
            "precios-0-modelo": self.modelo.pk, "precios-0-precio": "12.50"}
        self.assertEqual(self.client.post(ruta, datos).status_code, 302)
        self.assertEqual(self.client.post(ruta, datos).status_code, 302)
        compra = Compra.objects.get()
        for accion in ["documentar", "solicitar"]:
            url = reverse("compra_accion", args=[compra.pk, accion])
            self.assertEqual(self.client.get(url).status_code, 405)
            self.assertEqual(self.client.post(url).status_code, 302)
        self.client.force_login(self.finanzas)
        self.assertContains(self.client.get(reverse("compra_detalle", args=[compra.pk])), "Decisión financiera")
        self.assertEqual(self.client.post(reverse("compra_decidir", args=[compra.pk]), {"resultado": "APROBADA"}).status_code, 302)
        self.assertContains(self.client.get(reverse("finanzas_historial")), "Aprobada")

    def test_rechazo_en_pantalla_muestra_validacion(self):
        compra = self.pendiente()
        self.client.force_login(self.finanzas)
        respuesta = self.client.post(reverse("compra_decidir", args=[compra.pk]), {"resultado": "RECHAZADA"})
        self.assertContains(respuesta, "Ingrese el motivo del rechazo")
        self.assertFalse(DecisionFinanciera.objects.exists())

    def test_autenticacion_y_ventas_no_accede(self):
        compra = self.habitual()
        for ruta in [reverse("compra_lista"), reverse("compra_nueva"), reverse("compra_detalle", args=[compra.pk]), reverse("finanzas_bandeja")]:
            self.assertEqual(self.client.get(ruta).status_code, 302)
        self.client.force_login(self.ventas)
        self.assertEqual(self.client.get(reverse("compra_lista")).status_code, 403)
        self.assertEqual(self.client.get(reverse("compra_nueva")).status_code, 403)


    def test_recorrido_b_por_pantallas(self):
        solicitud = self.solicitud()
        oferta = self.cotizar(solicitud)
        self.client.force_login(self.compras)
        datos = {"clave_operacion": uuid4(), "procedimiento": "COTIZACION", "solicitud": solicitud.pk,
                 "precios-TOTAL_FORMS": 0, "precios-INITIAL_FORMS": 0}
        self.assertEqual(self.client.post(reverse("compra_nueva"), datos).status_code, 302)
        compra = Compra.objects.get()
        for accion, datos in [("evaluar", {}), ("seleccionar", {"oferta": oferta.pk}), ("documentar", {}), ("solicitar", {})]:
            self.assertEqual(self.client.post(reverse("compra_accion", args=[compra.pk, accion]), datos).status_code, 302)
        self.assertContains(self.client.get(reverse("documento_compra", args=[compra.pk])), "Orden de Compra")
        self.client.force_login(self.finanzas)
        self.assertEqual(self.client.post(reverse("compra_decidir", args=[compra.pk]), {"resultado": "RECHAZADA", "motivo": "Presupuesto"}).status_code, 302)
        compra.refresh_from_db()
        self.assertEqual(compra.estado, "RECHAZADA")

    def test_finanzas_no_puede_preparar_documentar_ni_seleccionar(self):
        compra = self.habitual()
        self.client.force_login(self.finanzas)
        self.assertEqual(self.client.get(reverse("compra_nueva")).status_code, 403)
        for accion in ["evaluar", "seleccionar", "documentar", "solicitar"]:
            self.assertEqual(self.client.post(reverse("compra_accion", args=[compra.pk, accion])).status_code, 403)
        with self.assertRaises(PermissionDenied):
            negocio.generar_documento(self.finanzas, compra)

    def test_inactivo_o_marcas_cambiadas_impiden_seleccion(self):
        solicitud = self.solicitud()
        oferta = self.cotizar(solicitud)
        compra = negocio.preparar_compra(self.compras, "COTIZACION", uuid4(), solicitud=solicitud)
        compra = negocio.evaluar_solicitud(self.compras, compra)
        Proveedor.objects.filter(pk=self.alternativo.pk).update(activo=False)
        with self.assertRaises(ValidationError):
            negocio.seleccionar_oferta(self.compras, compra, oferta)
        Proveedor.objects.filter(pk=self.alternativo.pk).update(activo=True)
        self.alternativo.marcas.clear()
        with self.assertRaises(ValidationError):
            negocio.seleccionar_oferta(self.compras, compra, oferta)
        self.assertIsNone(Compra.objects.get(pk=compra.pk).cotizacion_id)

    def test_fallo_documental_revierte_estado_y_documento(self):
        compra = self.habitual()
        with patch("compras.servicios_compras.MovimientoCompra.objects.create", side_effect=RuntimeError("fallo")):
            with self.assertRaises(RuntimeError):
                negocio.generar_documento(self.compras, compra)
        compra.refresh_from_db()
        self.assertEqual(compra.estado, "EN_PREPARACION")
        self.assertFalse(DocumentoCompra.objects.exists())

    def test_reasignacion_item_no_cambia_el_pedido_de_origen(self):
        compra = self.habitual()
        origen = compra.origenes.get()
        otro_pedido = self.item().listado
        ItemFaltante.objects.filter(pk=origen.item_id).update(listado=otro_pedido)
        documento = negocio.generar_documento(self.compras, compra)
        self.assertEqual(documento.contenido["origenes"][0]["pedido"], origen.pedido_id)

    def test_compra_rechazada_no_vuelve_a_modificarse(self):
        compra = negocio.decidir_compra(self.finanzas, self.pendiente(), "RECHAZADA", "No autorizada")
        datos = (compra.estado, compra.version, list(compra.detalles.values()), list(compra.origenes.values()))
        with self.assertRaises(ValidationError):
            negocio.solicitar_aprobacion(self.compras, compra)
        with self.assertRaises(ValidationError):
            negocio.decidir_compra(self.finanzas, compra, "APROBADA")
        compra.refresh_from_db()
        self.assertEqual(datos, (compra.estado, compra.version, list(compra.detalles.values()), list(compra.origenes.values())))


    def test_oferta_con_detalle_ajeno_no_es_valida_aunque_cantidad_coincida(self):
        from .models import DetalleCotizacion
        solicitud = self.solicitud(proveedores=[self.proveedor, self.alternativo])
        otra = solicitud.emision.solicitudes.exclude(pk=solicitud.pk).get()
        oferta = self.cotizar(solicitud)
        # Simula un documento legado inconsistente fuera del servicio autorizado.
        DetalleCotizacion.objects.filter(cotizacion=oferta).update(detalle_solicitud=otra.detalles.get())
        compra = negocio.preparar_compra(self.compras, "COTIZACION", uuid4(), solicitud=solicitud)
        compra = negocio.evaluar_solicitud(self.compras, compra)
        with self.assertRaises(ValidationError):
            negocio.seleccionar_oferta(self.compras, compra, oferta)
        self.assertEqual(negocio.ofertas_para_compra(self.compras, compra), [])


class SQLiteComprasTest(SimpleTestCase):
    def ejecutar_aislado(self, codigo):
        import subprocess
        import sys
        import tempfile
        from pathlib import Path
        inicio = r"""
import os, sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
from django.conf import settings
settings.DATABASES['default']['NAME'] = sys.argv[1]
import django
django.setup()
"""
        with tempfile.TemporaryDirectory() as carpeta:
            resultado = subprocess.run([sys.executable, '-c', inicio + codigo,
                str(Path(carpeta) / 'compras.sqlite3')], capture_output=True, text=True, timeout=60)
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)

    def test_reservas_documentos_y_decisiones_concurrentes_en_archivo_sqlite(self):
        self.ejecutar_aislado(r"""
import time
from uuid import uuid4
from threading import Barrier
from concurrent.futures import ThreadPoolExecutor
from django.core.management import call_command
from django.contrib.auth.models import User, Group
from django.db import connections, OperationalError
from django.core.exceptions import ValidationError
from compras.models import *
from compras import servicios_compras as negocio, servicios_pedidos as pedidos
call_command('migrate', verbosity=0)
c = User.objects.create_user('compras')
c.groups.add(Group.objects.create(name='Compras'))
v = User.objects.create_user('ventas')
v.groups.add(Group.objects.create(name='Ventas'))
f = User.objects.create_user('finanzas')
f.groups.add(Group.objects.create(name='Finanzas'))
s = Sucursal.objects.create(nombre='Rosario')
UsuarioSucursal.objects.create(usuario=v, sucursal=s)
m = Modelo.objects.create(nombre='Moto', marca=Marca.objects.create(nombre='K'))
p = Proveedor.objects.create(razon_social='P', email='p@e.com', es_fijo=True)
p.marcas.add(m.marca)
stock = Stock.objects.create(sucursal=s, modelo=m, cantidad=10)
def nuevo_item():
    return pedidos.registrar_pedido(v, [{'modelo': m, 'cantidad': 3}]).items.get()
item = nuevo_item()
def competir(operacion, valores):
    barrera = Barrier(2)
    def ejecutar(valor):
        usuario = User.objects.get(pk=f.pk if operacion == 'decidir' else c.pk)
        barrera.wait(timeout=10)
        try:
            for intento in range(100):
                try:
                    if operacion == 'crear':
                        salida = negocio.preparar_compra(usuario, 'HABITUAL', valor, proveedor=p, items=[item], precios={m.pk: '10.10'})
                    elif operacion == 'documentar':
                        salida = negocio.generar_documento(usuario, compra)
                    else:
                        salida = negocio.decidir_compra(usuario, compra, valor, 'Presupuesto' if valor == 'RECHAZADA' else '')
                    return ('ok', salida.pk)
                except OperationalError as error:
                    if 'locked' not in str(error).lower():
                        raise
                    time.sleep(0.02)
                except ValidationError:
                    return ('invalida', None)
            raise AssertionError('SQLite permanecio bloqueado')
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        return list(pool.map(ejecutar, valores))
clave = uuid4()
resultados = competir('crear', [clave, clave])
assert resultados[0] == resultados[1] and resultados[0][0] == 'ok', resultados
assert Compra.objects.count() == 1 and OrigenCompra.objects.count() == 1
compra = Compra.objects.get()
resultados = competir('documentar', [None, None])
assert all(r[0] == 'ok' for r in resultados), resultados
assert DocumentoCompra.objects.count() == 1
compra = negocio.solicitar_aprobacion(c, compra)
resultados = competir('decidir', ['APROBADA', 'RECHAZADA'])
assert sorted(r[0] for r in resultados) == ['invalida', 'ok'], resultados
assert DecisionFinanciera.objects.count() == 1
compra.refresh_from_db()
assert compra.estado == compra.decision.resultado
stock.refresh_from_db()
assert stock.cantidad == 10 and not Venta.objects.exists()
item = nuevo_item()
resultados = competir('crear', [uuid4(), uuid4()])
assert sorted(r[0] for r in resultados) == ['invalida', 'ok'], resultados
assert Compra.objects.count() == 2
assert OrigenCompra.objects.filter(item=item, vigente=True).count() == 1
otra = Compra.objects.order_by('pk').last()
negocio.generar_documento(c, otra)
assert len(set(DocumentoCompra.objects.values_list('numero', flat=True))) == 2
print('SQLite: reenvios, reserva exclusiva, numeracion y decision concurrente correctos')
""")

    def test_migracion_0005_preserva_datos_de_etapa_3(self):
        self.ejecutar_aislado(r"""
from uuid import uuid4
from datetime import date
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
anterior = [('compras', '0004_preservar_solicitudes_existentes')]
executor = MigrationExecutor(connection)
executor.migrate(anterior)
apps = executor.loader.project_state(anterior).apps
User = apps.get_model('auth', 'User')
usuario = User.objects.create(username='original')
sucursal = apps.get_model('compras', 'Sucursal').objects.create(nombre='Rosario')
marca = apps.get_model('compras', 'Marca').objects.create(nombre='K')
modelo = apps.get_model('compras', 'Modelo').objects.create(nombre='Moto', marca=marca)
stock = apps.get_model('compras', 'Stock').objects.create(sucursal=sucursal, modelo=modelo, cantidad=7)
venta = apps.get_model('compras', 'Venta').objects.create(usuario=usuario, sucursal=sucursal, fecha=date(2024, 2, 15), clave_operacion=uuid4())
apps.get_model('compras', 'DetalleVenta').objects.create(venta=venta, modelo=modelo, cantidad=2)
proveedor = apps.get_model('compras', 'Proveedor').objects.create(razon_social='P', email='p@e.com')
solicitud = apps.get_model('compras', 'SolicitudCotizacion').objects.create(proveedor=proveedor, proveedor_nombre='P', proveedor_email='p@e.com')
executor = MigrationExecutor(connection)
executor.migrate(executor.loader.graph.leaf_nodes())
from compras.models import Stock, Venta, SolicitudCotizacion, Compra
assert Stock.objects.get(pk=stock.pk).cantidad == 7
assert Venta.objects.get(pk=venta.pk).detalles.get().cantidad == 2
assert SolicitudCotizacion.objects.get(pk=solicitud.pk).proveedor_nombre == 'P'
assert not Compra.objects.exists()
assert connection.cursor().execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
print('Datos anteriores preservados al migrar 0005')
""")
