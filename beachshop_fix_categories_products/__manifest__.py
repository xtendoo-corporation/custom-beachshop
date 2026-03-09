{
    'name': 'Beachshop Fix Categories Products',
    'version': '19.0.1.0.0',
    'category': 'Inventory',
    'author': 'Xtendoo',
    'website': '',
    'license': 'AGPL-3',
    'summary': 'Duplicar categorías de producto entre compañías y reasignar productos',
    'depends': [
        'stock',
        'product',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/fix_categories_wizard_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
