# Section 7 — general expenses: municipality/unload fees + truck maintenance costs.
import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "expense_date", "label": _("التاريخ"), "fieldtype": "Date", "width": 110},
		{"fieldname": "expense_type", "label": _("نوع المصروف"), "fieldtype": "Data", "width": 140},
		{"fieldname": "reference", "label": _("المرجع"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 150},
		{"fieldname": "reference_doctype", "label": _("نوع المرجع"), "fieldtype": "Data", "width": 130, "hidden": 1},
		{"fieldname": "branch", "label": _("الفرع"), "fieldtype": "Data", "width": 110},
		{"fieldname": "description", "label": _("البيان"), "fieldtype": "Data", "width": 240},
		{"fieldname": "amount", "label": _("المبلغ"), "fieldtype": "Currency", "width": 120},
	]


def get_data(filters):
	values = {}
	date_cond_unload = ""
	date_cond_maint = ""
	if filters.get("from_date"):
		date_cond_unload += " AND u.unload_date >= %(from_date)s"
		date_cond_maint += " AND m.maintenance_date >= %(from_date)s"
		values["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		date_cond_unload += " AND u.unload_date <= %(to_date)s"
		date_cond_maint += " AND m.maintenance_date <= %(to_date)s"
		values["to_date"] = filters["to_date"]

	branch_cond_unload = ""
	if filters.get("branch"):
		branch_cond_unload = " AND u.branch = %(branch)s"
		values["branch"] = filters["branch"]

	rows = []
	expense_type = filters.get("expense_type")

	if expense_type in (None, "", "رسوم بلدية"):
		rows += frappe.db.sql(
			f"""
			SELECT
				u.unload_date AS expense_date,
				'رسوم بلدية' AS expense_type,
				u.name AS reference,
				'Container Unload' AS reference_doctype,
				u.branch,
				CONCAT('تفريغ الحاوية ', u.container) AS description,
				u.municipality_fee AS amount
			FROM `tabContainer Unload` u
			WHERE u.docstatus = 1 AND COALESCE(u.municipality_fee, 0) > 0
			{date_cond_unload}{branch_cond_unload}
			""",
			values,
			as_dict=True,
		)

	if expense_type in (None, "", "صيانة"):
		branch_cond_maint = " AND t.branch = %(branch)s" if filters.get("branch") else ""
		rows += frappe.db.sql(
			f"""
			SELECT
				m.maintenance_date AS expense_date,
				'صيانة' AS expense_type,
				m.parent AS reference,
				'Truck' AS reference_doctype,
				t.branch,
				CONCAT(m.maintenance_type, ' — الشاحنة ', m.parent) AS description,
				m.cost AS amount
			FROM `tabTruck Maintenance Log` m
			JOIN `tabTruck` t ON t.name = m.parent
			WHERE COALESCE(m.cost, 0) > 0
			{date_cond_maint}{branch_cond_maint}
			""",
			values,
			as_dict=True,
		)

	rows.sort(key=lambda r: str(r.expense_date or ""), reverse=True)
	return rows
