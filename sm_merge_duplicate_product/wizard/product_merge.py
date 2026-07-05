# -*- coding: utf-8 -*-
import logging

import psycopg2

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import mute_logger

_logger = logging.getLogger(__name__)

# Junction table of this wizard's own product_ids field - never rewrite it,
# it holds the wizard's own selection while the merge is running.
_OWN_RELATION_TABLE = 'sm_product_merge_wizard_product_rel'


class ProductMergeWizard(models.TransientModel):
    _name = 'sm.product.merge.wizard'
    _description = 'Merge Duplicate Products'

    product_ids = fields.Many2many(
        'product.product', relation='sm_product_merge_wizard_product_rel',
        string='From Products', required=True,
        help="All the duplicate products to merge, including the one you want to keep.",
    )
    dst_product_id = fields.Many2one(
        'product.product', string='To Product', required=True,
        domain="[('id', 'in', product_ids)]",
        help="The product to keep. The others are merged into this one and removed.",
    )

    @api.model
    def default_get(self, field_names):
        res = super().default_get(field_names)
        if 'product_ids' in field_names and not res.get('product_ids'):
            products = self._selected_products()
            if products:
                res['product_ids'] = [(6, 0, products.ids)]
        product_ids = res.get('product_ids')
        if product_ids and 'dst_product_id' in field_names and not res.get('dst_product_id'):
            # Default to the oldest record: that is almost always the original
            # product, the newer ones being the accidental duplicates.
            res['dst_product_id'] = min(product_ids[0][2])
        return res

    def _selected_products(self):
        """ Resolve the records the action was triggered on into product.product,
        whether launched from the Products (product.template) list or the
        Product Variants (product.product) list.
        """
        active_model = self.env.context.get('active_model')
        active_ids = self.env.context.get('active_ids') or []
        if active_model == 'product.product':
            return self.env['product.product'].browse(active_ids)
        if active_model == 'product.template':
            templates = self.env['product.template'].browse(active_ids)
            if any(len(t.product_variant_ids) > 1 for t in templates):
                raise UserError(_(
                    "One of the selected products has multiple variants. "
                    "Merge from the Product Variants list instead, so you can "
                    "pick the exact variants to combine."
                ))
            return templates.product_variant_ids
        return self.env['product.product']

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------
    def action_merge(self):
        self.ensure_one()
        if not self.env.user.has_group('stock.group_stock_manager'):
            raise AccessError(_("Only a stock manager can merge products."))

        products = self.product_ids
        dst = self.dst_product_id
        if len(products) < 2:
            raise UserError(_("Select at least 2 products to merge."))
        if dst not in products:
            raise UserError(_("The product to keep must be one of the selected products."))
        if len(set(products.mapped('type'))) > 1:
            raise UserError(_("All selected products must have the same Product Type."))
        if len(set(products.mapped('tracking'))) > 1:
            raise UserError(_(
                "All selected products must use the same Tracking "
                "(No Tracking / By Lot / By Serial Number)."
            ))

        src = products - dst
        src_templates = src.product_tmpl_id - dst.product_tmpl_id
        names = ', '.join(src.mapped('display_name'))

        self._merge_quants(src, dst)
        self._update_foreign_keys(src, dst)

        # Post on the template too: the Products form shows the template
        # chatter, so a variant-only message would be invisible there.
        dst.message_post(body=_("Merged with: %s") % names)
        dst.product_tmpl_id.message_post(body=_("Merged with: %s") % names)
        src.with_context(active_test=False)._unlink_or_archive()

        # unlink() already deletes an orphaned template once its last variant
        # is gone; when a variant could only be archived (e.g. an open POS
        # session blocks deletion), its template is left behind active with
        # zero variants - archive it too so it disappears from product lists.
        orphaned = src_templates.exists().filtered(lambda t: not t.product_variant_ids)
        if orphaned:
            orphaned.write({'active': False})

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'product.product',
            'view_mode': 'form',
            'res_id': dst.id,
            'target': 'current',
        }

    # ------------------------------------------------------------------
    # Stock: add each source quant's quantity onto the matching destination
    # quant (same location/lot/package/owner) instead of blindly repointing
    # the foreign key, which would just relocate the row and could collide
    # with the unique (product, location, lot, package, owner) index.
    # ------------------------------------------------------------------
    def _merge_quants(self, src, dst):
        Quant = self.env['stock.quant'].sudo()
        quants = Quant.search([('product_id', 'in', src.ids)])
        for quant in quants:
            if quant.quantity or quant.reserved_quantity:
                Quant._update_available_quantity(
                    dst, quant.location_id,
                    quantity=quant.quantity,
                    reserved_quantity=quant.reserved_quantity,
                    lot_id=quant.lot_id, package_id=quant.package_id,
                    owner_id=quant.owner_id, in_date=quant.in_date,
                )
        quants.unlink()

    # ------------------------------------------------------------------
    # Everything else: generic foreign-key reassignment. Odoo core uses the
    # exact same pg_constraint introspection to merge res.partner records
    # (see base/wizard/base_partner_merge.py) - this applies the same,
    # well-known technique to product.product.
    # ------------------------------------------------------------------
    def _get_fk_on(self, table):
        query = """
            SELECT cl1.relname as table, att1.attname as column
            FROM pg_constraint as con, pg_class as cl1, pg_class as cl2, pg_attribute as att1, pg_attribute as att2
            WHERE con.conrelid = cl1.oid
                AND con.confrelid = cl2.oid
                AND array_lower(con.conkey, 1) = 1
                AND con.conkey[1] = att1.attnum
                AND att1.attrelid = cl1.oid
                AND cl2.relname = %s
                AND att2.attname = 'id'
                AND array_lower(con.confkey, 1) = 1
                AND con.confkey[1] = att2.attnum
                AND att2.attrelid = cl2.oid
                AND con.contype = 'f'
        """
        self.env.cr.execute(query, (table,))
        return self.env.cr.fetchall()

    def _update_foreign_keys(self, src, dst):
        cr = self.env.cr
        relations = self._get_fk_on('product_product')
        self.env.invalidate_all()

        for table, column in relations:
            if table in (_OWN_RELATION_TABLE, 'stock_quant'):
                continue
            try:
                with mute_logger('odoo.sql_db'), cr.savepoint():
                    cr.execute(
                        'UPDATE "%s" SET "%s" = %%s WHERE "%s" IN %%s' % (table, column, column),
                        (dst.id, tuple(src.ids)),
                    )
            except psycopg2.Error:
                _logger.warning(
                    "Merge products: could not repoint %s.%s from %s to %s, "
                    "leaving those rows untouched.", table, column, src.ids, dst.id,
                )
        self.env.invalidate_all()
