"""Custom fields on ERPNext Customer for the container-rental domain
(document section 2.4). The WhatsApp number is the standard Customer
`mobile_no` (primary Contact) — the same field frappe_whatsapp resolves. Tagged with module "Container Rental" so the fixture
filter in hooks.py exports them. Idempotent — also re-syncs labels."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CUSTOM_FIELDS = {
	"Customer": [
		{
			"fieldname": "cr_rental_section",
			"fieldtype": "Section Break",
			"label": "Container Rental Details",
			"insert_after": "customer_type",
			"module": "Container Rental",
		},
		{
			"fieldname": "cr_account_type",
			"fieldtype": "Select",
			"label": "Account Type",
			"options": "نقدي\nآجل",
			"default": "نقدي",
			"insert_after": "cr_rental_section",
			"allow_in_quick_entry": 1,
			"in_standard_filter": 1,
			"module": "Container Rental",
		},
		{
			"fieldname": "cr_rental_balance",
			"fieldtype": "Currency",
			"label": "Rental Balance",
			"read_only": 1,
			"insert_after": "cr_account_type",
			"module": "Container Rental",
			"description": "Total outstanding from container rentals",
		},
		{
			"fieldname": "cr_locations_section",
			"fieldtype": "Section Break",
			"label": "Delivery Locations",
			"insert_after": "cr_rental_balance",
			"collapsible": 1,
			"module": "Container Rental",
		},
		{
			"fieldname": "cr_delivery_locations",
			"fieldtype": "Table",
			"label": "Locations",
			"options": "Client Address",
			"insert_after": "cr_locations_section",
			"module": "Container Rental",
		},
	]
}


def execute():
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
	from container_rental.patches.add_hr_customizations import sync_custom_field_labels

	sync_custom_field_labels(CUSTOM_FIELDS)
