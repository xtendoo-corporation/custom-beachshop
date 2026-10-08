from odoo import api, models


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    @api.onchange("product_id")
    def _onchange_product_id(self):
        """Al elegir producto a mano, deja el precio de lista en price_unit y
        el % de la tarifa en discount (como ya hace el escaneo por código de
        barras en pos_conventional_core)."""
        super()._onchange_product_id()
        for line in self:
            line._apply_pricelist_discount()

    def _apply_pricelist_discount(self):
        self.ensure_one()
        order = self.order_id
        product = self.product_id
        if not product or not order.pricelist_id:
            return
        qty = self.qty or 1.0
        public_price = product.lst_price
        pricelist_price = order.pricelist_id._get_product_price(
            product, qty, partner=order.partner_id, uom=product.uom_id
        )
        if public_price <= 0 or public_price <= pricelist_price:
            return
        taxes_after_fp = order.fiscal_position_id.map_tax(self.tax_ids)
        self.price_unit = self.env["account.tax"]._fix_tax_included_price_company(
            public_price, self.tax_ids, taxes_after_fp, self.company_id
        )
        self.discount = (public_price - pricelist_price) / public_price * 100
        self._onchange_qty()
