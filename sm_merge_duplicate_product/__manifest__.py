# -*- coding: utf-8 -*-
{
    'name': 'Merge Duplicate Products',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Merge duplicate products into one, keeping stock, orders, and history intact',
    'description': """
Merge Duplicate Products
==========================

Select the duplicate products cluttering your catalog, pick which one to
keep, and merge. Every purchase line, sale line, invoice line, bill of
material, and stock move that pointed at a duplicate now points at the
product you kept - and its on-hand quantity is added to the kept product's
stock, at the same locations, lots, and packages.

Main Features
-------------
* Select 2 or more products anywhere a product list is shown, then Actions > Merge Products.
* Choose which product to keep; the others are merged into it.
* Stock quantities are combined per location/lot/package, not just reassigned - nothing is lost.
* Every document referencing a merged product (sales, purchases, invoices, BOMs, stock moves) is updated automatically.
* Merged products are deleted when possible, archived when history prevents deletion.
* Blocks merges across incompatible product types or tracking modes to protect data integrity.
    """,
    'author': 'Steven Marp',
    'website': 'https://apps.odoo.com/apps/modules/browse?author=Steven Marp',
    'license': 'OPL-1',
    'depends': ['stock'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/product_merge_views.xml',
    ],
    'images': [
        'static/description/banner.gif',
        'static/description/icon.png',
        'static/description/ss-01-select-and-merge-action.png',
        'static/description/ss-02-merge-wizard.png',
        'static/description/ss-04-after-merge.png',
        'static/description/ss-05-chatter-log.png',
        'static/description/ss-06-guard-tracking.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'price': 8.51,
    'currency': 'USD',
}
