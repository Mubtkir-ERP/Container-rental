# S10 — تقرير العقود: all 16 columns of the reference screen.
import frappe
from frappe import _


def execute(filters=None):
	return get_columns(), get_data(filters or {})


def get_columns():
	return [
		{"fieldname": "idx", "label": _("#"), "fieldtype": "Int", "width": 50},
		{"fieldname": "contract_no", "label": _("Contract No"), "fieldtype": "Link", "options": "Container Contract", "width": 140},
		{"fieldname": "client_name", "label": _("Client Name"), "fieldtype": "Data", "width": 160},
		{"fieldname": "mobile_no", "label": _("Client Phone"), "fieldtype": "Data", "width": 120},
		{"fieldname": "duration_days", "label": _("Contract Duration (Days)"), "fieldtype": "Int", "width": 110},
		{"fieldname": "start_date", "label": _("Contract Start Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "end_date", "label": _("Contract End Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "contract_value", "label": _("Contract Total"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "payment_method", "label": _("Payment Method"), "fieldtype": "Data", "width": 110},
		{"fieldname": "total_trips", "label": _("Trips Count"), "fieldtype": "Int", "width": 100},
		{"fieldname": "remaining_trips", "label": _("Remaining Trips"), "fieldtype": "Int", "width": 110},
		{"fieldname": "last_container", "label": _("Last Container No"), "fieldtype": "Link", "options": "Container", "width": 120},
		{"fieldname": "owner_user", "label": _("Added By"), "fieldtype": "Link", "options": "User", "width": 140},
		{"fieldname": "contract_status", "label": _("Contract Status"), "fieldtype": "Data", "width": 90},
		{"fieldname": "actions", "label": _("Actions"), "fieldtype": "Data", "width": 200},
	]


def get_data(filters):
	conditions = ["c.docstatus = 1"]
	values = {}

	if filters.get("client"):
		conditions.append("c.client = %(client)s")
		values["client"] = filters["client"]
	if filters.get("contract"):
		conditions.append("c.name = %(contract)s")
		values["contract"] = filters["contract"]
	if filters.get("status"):
		conditions.append("c.contract_status = %(status)s")
		values["status"] = filters["status"]
	if filters.get("from_date"):
		conditions.append("c.start_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		conditions.append("c.start_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	rows = frappe.db.sql(
		f"""
		SELECT
			c.name AS contract_no, cl.customer_name AS client_name, cl.mobile_no AS mobile_no,
			DATEDIFF(c.end_date, c.start_date) AS duration_days,
			c.start_date, c.end_date, c.contract_value, c.payment_method,
			c.total_trips, c.remaining_trips, c.last_container,
			c.owner AS owner_user, c.contract_status
		FROM `tabContainer Contract` c
		LEFT JOIN `tabCustomer` cl ON cl.name = c.client
		WHERE {" AND ".join(conditions)}
		ORDER BY c.start_date DESC
		""",
		values,
		as_dict=True,
	)
	for i, row in enumerate(rows, 1):
		row["idx"] = i
	return rows
