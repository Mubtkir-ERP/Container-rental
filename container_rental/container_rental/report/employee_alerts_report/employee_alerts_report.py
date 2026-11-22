# S7 — employee document alerts from the Employee "Documentات" child table.
import frappe
from frappe import _
from frappe.utils import add_days, today


def execute(filters=None):
	filters = filters or {}
	settings = frappe.get_cached_doc("Container Rental Settings")
	horizon = add_days(today(), settings.expiry_alert_days or 30)
	message = _("Rows highlighted in red have documents that are expired or expiring before {0}").format(
		frappe.format(horizon, {"fieldtype": "Date"})
	)
	return get_columns(), get_data(filters), message


def get_columns():
	return [
		{"fieldname": "employee", "label": _("ID"), "fieldtype": "Link", "options": "Employee", "width": 110},
		{"fieldname": "employee_name", "label": _("Employee Name"), "fieldtype": "Data", "width": 160},
		{"fieldname": "branch", "label": _("Branch"), "fieldtype": "Data", "width": 110},
		{"fieldname": "designation", "label": _("Designation"), "fieldtype": "Data", "width": 130},
		{"fieldname": "cell_number", "label": _("Mobile No"), "fieldtype": "Data", "width": 110},
		{"fieldname": "document_name", "label": _("Document"), "fieldtype": "Data", "width": 150},
		{"fieldname": "expiry_date", "label": _("Expiry Date"), "fieldtype": "Date", "width": 120},
		{"fieldname": "attachment", "label": _("File"), "fieldtype": "Data", "width": 120},
		{"fieldname": "status", "label": _("Employee Status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "actions", "label": _("Actions"), "fieldtype": "Data", "width": 140},
	]


def get_data(filters):
	conditions = ["1=1"]
	values = {}
	if filters.get("employee"):
		conditions.append("e.name = %(employee)s")
		values["employee"] = filters["employee"]

	return frappe.db.sql(
		f"""
		SELECT
			e.name AS employee, e.employee_name, e.branch, e.designation,
			e.cell_number, e.status,
			d.document_name, d.expiry_date, d.attachment
		FROM `tabEmployee` e
		LEFT JOIN `tabCR Document Item` d
			ON d.parent = e.name AND d.parenttype = 'Employee'
		WHERE {" AND ".join(conditions)}
		ORDER BY e.employee_name, d.expiry_date
		""",
		values,
		as_dict=True,
	)
