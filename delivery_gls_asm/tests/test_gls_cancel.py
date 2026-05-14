# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
# Mocked unit tests: no real GLS calls, safe to enable.
from unittest.mock import patch

from odoo.addons.base.tests.common import BaseCommon


class TestGlsAsmCancel(BaseCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.shipping_product = cls.env["product.product"].create(
            {"type": "service", "name": "Test Shipping costs", "list_price": 10.0}
        )
        cls.carrier_gls_asm = cls.env["delivery.carrier"].create(
            {
                "name": "GLS ASM Cancel Test",
                "delivery_type": "gls_asm",
                "product_id": cls.shipping_product.id,
                "prod_environment": False,
                "gls_asm_service": "37",
            }
        )
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Cancel Test Partner",
                "city": "Test City",
                "zip": "08001",
                "street": "Test Street, 1",
            }
        )
        cls.product = cls.env["product.product"].create(
            {"is_storable": True, "name": "Cancel Test product"}
        )
        # Minimal picking — we only need it to carry GLS refs.
        picking_type = cls.env.ref("stock.picking_type_out")
        cls.picking = cls.env["stock.picking"].create(
            {
                "partner_id": cls.partner.id,
                "picking_type_id": picking_type.id,
                "location_id": picking_type.default_location_src_id.id,
                "location_dest_id": cls.partner.property_stock_customer.id,
                "carrier_id": cls.carrier_gls_asm.id,
            }
        )

    def test_cancel_clears_refs_when_gls_rejects(self):
        """When GLS rejects the cancel (e.g. _return < 0 / "No existe envio"),
        local GLS refs must still be cleared so the picking can be re-shipped
        without leaving a stale gls_asm_public_tracking_ref that would make
        gls_asm_get_label return the cached label from GLS instead of
        triggering a fresh shipment."""
        self.picking.write(
            {
                "carrier_tracking_ref": "FAKE_TRACK",
                "gls_asm_public_tracking_ref": "FAKE_BAR",
                "gls_asm_picking_ref": "FAKE_INTL",
            }
        )
        carrier_cls = type(self.carrier_gls_asm)

        def fake_state_update(carrier, picking=None):
            if picking is not None:
                picking.delivery_state = "shipping_recorded_in_carrier"

        with patch.object(
            carrier_cls,
            "gls_asm_tracking_state_update",
            autospec=True,
            side_effect=fake_state_update,
        ), patch(
            "odoo.addons.delivery_gls_asm.models.delivery_carrier.GlsAsmRequest"
        ) as MockReq:
            MockReq.return_value._cancel_shipment.return_value = {
                "_return": -1,
                "gls_sent_xml": "<x/>",
                "value": "No existe envio",
            }
            self.carrier_gls_asm.gls_asm_cancel_shipment(self.picking)

        self.assertFalse(self.picking.gls_asm_public_tracking_ref)
        self.assertFalse(self.picking.gls_asm_picking_ref)

    def test_cancel_clears_refs_when_gls_accepts(self):
        """Successful cancel must also clear local GLS refs (regression test
        to ensure the new code path keeps the previous happy-path behavior)."""
        self.picking.write(
            {
                "carrier_tracking_ref": "OK_TRACK",
                "gls_asm_public_tracking_ref": "OK_BAR",
                "gls_asm_picking_ref": "OK_INTL",
            }
        )
        carrier_cls = type(self.carrier_gls_asm)

        def fake_state_update(carrier, picking=None):
            if picking is not None:
                picking.delivery_state = "shipping_recorded_in_carrier"

        with patch.object(
            carrier_cls,
            "gls_asm_tracking_state_update",
            autospec=True,
            side_effect=fake_state_update,
        ), patch(
            "odoo.addons.delivery_gls_asm.models.delivery_carrier.GlsAsmRequest"
        ) as MockReq:
            MockReq.return_value._cancel_shipment.return_value = {
                "_return": 0,
                "gls_sent_xml": "<x/>",
                "value": "Cancelled",
            }
            self.carrier_gls_asm.gls_asm_cancel_shipment(self.picking)

        self.assertFalse(self.picking.gls_asm_public_tracking_ref)
        self.assertFalse(self.picking.gls_asm_picking_ref)
