"""Container-rental fields on ERPNext Sales Invoice: the source order and the
payment method the driver actually collected with. Tagged with module
"Container Rental" so the fixture filter in hooks.py exports them."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CUSTOM_FIELDS = {
	"Sales Invoice": [
		{
			"fieldname": "cr_container_order",
			"fieldtype": "Link",
			"label": "Container Order",
			"options": "Container Order",
			"insert_after": "customer_name",
			"read_only": 1,
			"module": "Container Rental",
		},
		{
			"fieldname": "cr_payment_method",
			"fieldtype": "Link",
			"label": "Collected Payment Method",
			"options": "Mode of Payment",
			"insert_after": "cr_container_order",
			"module": "Container Rental",
			"description": "طريقة الدفع التي اعتمدها السائق عند التسليم — تُستخدم عند تسجيل سند القبض",
		},
	]
}


def execute():
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
	from container_rental.patches.add_hr_customizations import sync_custom_field_labels

	sync_custom_field_labels(CUSTOM_FIELDS)
