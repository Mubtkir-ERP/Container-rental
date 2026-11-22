# Section 7 — general expenses: municipality/unload fees + truck maintenance costs.
import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "expense_date", "label": _("Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "expense_type", "label": _("Expense Type"), "fieldtype": "Data", "width": 140},
		{"fieldname": "reference", "label": _("Reference"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 150},
		{"fieldname": "reference_doctype", "label": _("Reference Type"), "fieldtype": "Data", "width": 130, "hidden": 1},
		{"fieldname": "branch", "label": _("Branch"), "fieldtype": "Data", "width": 110},
		{"fieldname": "description", "label": _("Description"), "fieldtype": "Data", "width": 240},
		{"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "width": 120},
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

	if expense_type in (None, "", "Municipality Fees", "رسوم بلدية"):
		rows += frappe.db.sql(
			f"""
			SELECT
				u.unload_date AS expense_date,
				'Municipality Fees' AS expense_type,
				u.name AS reference,
				'Container Unload' AS reference_doctype,
				u.branch,
				u.container AS _container,
				u.municipality_fee AS amount
			FROM `tabContainer Unload` u
			WHERE u.docstatus = 1 AND COALESCE(u.municipality_fee, 0) > 0
			{date_cond_unload}{branch_cond_unload}
			""",
			values,
			as_dict=True,
		)

	if expense_type in (None, "", "Maintenance"):
		branch_cond_maint = " AND t.branch = %(branch)s" if filters.get("branch") else ""
		rows += frappe.db.sql(
			f"""
			SELECT
				m.maintenance_date AS expense_date,
				'Maintenance' AS expense_type,
				m.parent AS reference,
				'Truck' AS reference_doctype,
				t.branch,
				m.maintenance_type AS _maintenance_type,
				m.cost AS amount
			FROM `tabTruck Maintenance Log` m
			JOIN `tabTruck` t ON t.name = m.parent
			WHERE COALESCE(m.cost, 0) > 0
			{date_cond_maint}{branch_cond_maint}
			""",
			values,
			as_dict=True,
		)

	for r in rows:
		if r.get("_container"):
			r["description"] = _("Unload container {0}").format(r.pop("_container"))
		elif r.get("_maintenance_type"):
			r["description"] = f"{_(r.pop('_maintenance_type'))} — {_('Truck')} {r['reference']}"
		r["expense_type"] = _(r["expense_type"])

	rows.sort(key=lambda r: str(r.expense_date or ""), reverse=True)
	return rows
