from __future__ import unicode_literals
from frappe import _


def get_data():
	return {
		'fieldname': 'item_group',
		'transactions': [
			{
				'label': _('Configuration'),
				'items': ['Item Default Rule']
			}
		]
	}
