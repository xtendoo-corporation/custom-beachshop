import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BeachshopFixCategoriesWizard(models.TransientModel):
    _name = 'beachshop.fix.categories.wizard'
    _description = 'Wizard para duplicar categorías y reasignar productos entre compañías'

    source_company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía Origen',
        required=True,
        default=lambda self: self.env['res.company'].search([], limit=1, order='id asc'),
        help='Compañía de la que se copiarán las categorías de producto.',
    )
    target_company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía Destino',
        required=True,
        default=lambda self: self.env['res.company'].search([], limit=2, order='id asc')[-1:],
        help='Compañía a la que se copiarán las categorías y se reasignarán los productos.',
    )

    @api.constrains('source_company_id', 'target_company_id')
    def _check_different_companies(self):
        for wizard in self:
            if wizard.source_company_id == wizard.target_company_id:
                raise UserError(_('La compañía origen y destino deben ser diferentes.'))

    def action_duplicate_categories(self):
        """Duplicar las categorías de producto de la compañía origen a la compañía destino,
        respetando la jerarquía padre/hijo."""
        self.ensure_one()

        source_company = self.source_company_id
        target_company = self.target_company_id

        ProductCategory = self.env['product.category'].sudo()

        # Obtener categorías de la compañía origen ordenadas por parent_path
        # para procesar padres antes que hijos
        source_categories = ProductCategory.search(
            [('company_id', '=', source_company.id)],
            order='parent_path asc',
        )

        if not source_categories:
            raise UserError(_(
                'No se encontraron categorías de producto en la compañía "%s".',
                source_company.name,
            ))

        # Mapping: id categoría origen -> id categoría destino
        categ_mapping = {}
        created_count = 0

        for source_categ in source_categories:
            # Determinar el parent_id en la compañía destino
            target_parent_id = False
            if source_categ.parent_id:
                target_parent_id = categ_mapping.get(source_categ.parent_id.id, False)

            # Buscar si ya existe una categoría con el mismo nombre y padre en la compañía destino
            domain = [
                ('name', '=', source_categ.name),
                ('company_id', '=', target_company.id),
                ('parent_id', '=', target_parent_id),
            ]
            existing_categ = ProductCategory.search(domain, limit=1)

            if existing_categ:
                categ_mapping[source_categ.id] = existing_categ.id
                _logger.info(
                    'Categoría "%s" ya existe en compañía "%s" (id=%s), se omite.',
                    source_categ.complete_name, target_company.name, existing_categ.id,
                )
            else:
                new_categ = ProductCategory.create({
                    'name': source_categ.name,
                    'company_id': target_company.id,
                    'parent_id': target_parent_id,
                })
                categ_mapping[source_categ.id] = new_categ.id
                created_count += 1
                _logger.info(
                    'Categoría "%s" creada en compañía "%s" (id=%s).',
                    source_categ.complete_name, target_company.name, new_categ.id,
                )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Duplicación completada'),
                'message': _(
                    'Se han creado %s categorías nuevas en la compañía "%s". '
                    '%s categorías ya existían y se omitieron.',
                    created_count,
                    target_company.name,
                    len(source_categories) - created_count,
                ),
                'type': 'success',
                'sticky': True,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def action_reassign_products(self):
        """Reasignar los productos de la compañía destino para que usen
        las categorías que pertenecen a su compañía (matching por complete_name)."""
        self.ensure_one()

        target_company = self.target_company_id

        ProductTemplate = self.env['product.template'].sudo()
        ProductCategory = self.env['product.category'].sudo()

        # Obtener todas las categorías de la compañía destino indexadas por complete_name
        target_categories = ProductCategory.search([
            ('company_id', '=', target_company.id),
        ])
        target_categ_by_name = {categ.complete_name: categ for categ in target_categories}

        # Obtener productos de la compañía destino
        products = ProductTemplate.search([
            ('company_id', '=', target_company.id),
        ])

        if not products:
            raise UserError(_(
                'No se encontraron productos en la compañía "%s".',
                target_company.name,
            ))

        reassigned_count = 0
        not_found = []

        for product in products:
            current_categ = product.categ_id
            if not current_categ:
                continue

            # Si la categoría ya pertenece a la compañía destino, no hacer nada
            if current_categ.company_id.id == target_company.id:
                continue

            # Buscar categoría equivalente en la compañía destino por complete_name
            target_categ = target_categ_by_name.get(current_categ.complete_name)

            if target_categ:
                product.categ_id = target_categ.id
                reassigned_count += 1
                _logger.info(
                    'Producto "%s" (id=%s): categoría cambiada de "%s" (comp. %s) a "%s" (comp. %s).',
                    product.name, product.id,
                    current_categ.complete_name, current_categ.company_id.name,
                    target_categ.complete_name, target_categ.company_id.name,
                )
            else:
                not_found.append(f'{product.name} -> {current_categ.complete_name}')
                _logger.warning(
                    'Producto "%s" (id=%s): no se encontró categoría "%s" en compañía "%s".',
                    product.name, product.id,
                    current_categ.complete_name, target_company.name,
                )

        message = _(
            'Se han reasignado %s productos a categorías de la compañía "%s".',
            reassigned_count,
            target_company.name,
        )
        if not_found:
            message += '\n\n' + _(
                'Los siguientes productos no pudieron ser reasignados '
                '(no se encontró categoría equivalente):\n%s',
                '\n'.join(not_found[:20]),
            )
            if len(not_found) > 20:
                message += _('\n... y %s más.', len(not_found) - 20)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reasignación completada'),
                'message': message,
                'type': 'success' if not not_found else 'warning',
                'sticky': True,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def action_execute_all(self):
        """Ejecutar duplicación de categorías y reasignación de productos en secuencia."""
        self.ensure_one()
        self.action_duplicate_categories()
        return self.action_reassign_products()
