"""ERPNext HR/Selling integration (user request 2026-08-10):

- Employee gets a "Documents" tab with a documents child table (name/file/expiry)
  that feeds the expiry alerts.
- Sales Person gets the flat per-delivery commission field (drivers are Sales
  Persons linked to their Employee).
- Seeds the five Designations and the two Container Sizes.

Idempotent — also re-syncs labels/descriptions of already-created fields."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CUSTOM_FIELDS = {
	"Employee": [
		{
			"fieldname": "cr_is_driver",
			"fieldtype": "Check",
			"label": "Works as a Driver Too",
			"insert_after": "designation",
			"module": "Container Rental",
			"description": "فعّله للمشرف الذي يقود أيضًا، ليظهر في قوائم إسناد السائقين ويستطيع إسناد الطلب لنفسه",
		},
		{
			"fieldname": "cr_documents_tab",
			"fieldtype": "Tab Break",
			"label": "Documents",
			"insert_after": "internal_work_history",
			"module": "Container Rental",
		},
		{
			"fieldname": "cr_documents",
			"fieldtype": "Table",
			"label": "Employee Documents",
			"options": "CR Document Item",
			"insert_after": "cr_documents_tab",
			"module": "Container Rental",
			"description": "Iqama, insurance, driver card... with automatic expiry alerts",
		},
	],
	"Sales Person": [
		{
			"fieldname": "cr_commission_per_delivery",
			"fieldtype": "Currency",
			"label": "Commission Per Delivery",
			"insert_after": "commission_rate",
			"module": "Container Rental",
			"description": "Credited to the driver on every successful container delivery",
		},
	],
}

DESIGNATIONS = ["سائق", "مشرف سواقين", "موظف خدمة عملاء", "موظف متابعة حوالات", "إداري"]
CONTAINER_SIZES = ["10 ياردة", "20 ياردة"]


SYNCED_PROPERTIES = ("label", "description", "options", "default", "fieldtype")


def sync_custom_field_labels(definitions):
	"""create_custom_fields skips fields that already exist — push the app's
	current label/description/options so redefinitions (e.g. Select values
	moved to English) reach sites where the field was created earlier."""
	for doctype, fields in definitions.items():
		for field in fields:
			name = f"{doctype}-{field['fieldname']}"
			if not frappe.db.exists("Custom Field", name):
				continue
			values = {key: field[key] for key in SYNCED_PROPERTIES if key in field}
			if values:
				frappe.db.set_value("Custom Field", name, values, update_modified=False)
	frappe.clear_cache()


def execute():
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
	sync_custom_field_labels(CUSTOM_FIELDS)

	for designation in DESIGNATIONS:
		if not frappe.db.exists("Designation", designation):
			frappe.get_doc({"doctype": "Designation", "designation_name": designation}).insert(
				ignore_permissions=True
			)

	for size in CONTAINER_SIZES:
		if not frappe.db.exists("Container Size", size):
			frappe.get_doc({"doctype": "Container Size", "size_name": size}).insert(
				ignore_permissions=True
			)

	frappe.db.commit()
