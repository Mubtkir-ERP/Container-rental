"""ERPNext HR/Selling integration (user request 2026-08-10):

- Employee gets a "المستندات" tab with a documents child table (name/file/expiry)
  that feeds the expiry alerts.
- Sales Person gets the flat per-delivery commission field (drivers are Sales
  Persons linked to their Employee).
- Seeds the five Designations and the two Container Sizes.

Idempotent."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CUSTOM_FIELDS = {
	"Employee": [
		{
			"fieldname": "cr_documents_tab",
			"fieldtype": "Tab Break",
			"label": "المستندات",
			"insert_after": "internal_work_history",
			"module": "Container Rental",
		},
		{
			"fieldname": "cr_documents",
			"fieldtype": "Table",
			"label": "مستندات الموظف",
			"options": "CR Document Item",
			"insert_after": "cr_documents_tab",
			"module": "Container Rental",
			"description": "الإقامة، التأمين، كارت السائق... مع تنبيه تلقائي قبل الانتهاء",
		},
	],
	"Sales Person": [
		{
			"fieldname": "cr_commission_per_delivery",
			"fieldtype": "Currency",
			"label": "قيمة العمولة لكل توصيلة",
			"insert_after": "commission_rate",
			"module": "Container Rental",
			"description": "تُحتسب للسائق عند كل عملية توصيل حاوية ناجحة",
		},
	],
}

DESIGNATIONS = ["سائق", "مشرف سواقين", "موظف خدمة عملاء", "موظف متابعة حوالات", "إداري"]
CONTAINER_SIZES = ["10 ياردة", "20 ياردة"]


def execute():
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)

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
