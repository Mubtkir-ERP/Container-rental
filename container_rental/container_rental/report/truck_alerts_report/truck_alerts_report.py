# S8 — truck alerts: documents child table rows + latest oil-change status.
import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "vehicle_no", "label": _("Vehicle No"), "fieldtype": "Link", "options": "Truck", "width": 120},
		{"fieldname": "branch", "label": _("Branch"), "fieldtype": "Data", "width": 110},
		{"fieldname": "driver_name", "label": _("Driver"), "fieldtype": "Data", "width": 140},
		{"fieldname": "document_name", "label": _("Document"), "fieldtype": "Data", "width": 150},
		{"fieldname": "expiry_date", "label": _("Expiry Date"), "fieldtype": "Date", "width": 120},
		{"fieldname": "current_odometer_km", "label": _("Current Odometer (km)"), "fieldtype": "Int", "width": 120},
		{"fieldname": "next_oil_date", "label": _("Next Oil Change"), "fieldtype": "Date", "width": 120},
		{"fieldname": "next_oil_km", "label": _("Next Oil Change (km)"), "fieldtype": "Int", "width": 110},
		{"fieldname": "actions", "label": _("Actions"), "fieldtype": "Data", "width": 140},
	]


def get_data(filters):
	conditions = ["1=1"]
	values = {}
	if filters.get("vehicle"):
		conditions.append("t.name = %(vehicle)s")
		values["vehicle"] = filters["vehicle"]

	return frappe.db.sql(
		f"""
		SELECT
			t.name AS vehicle_no, t.branch, e.employee_name AS driver_name,
			t.current_odometer_km,
			d.document_name, d.expiry_date,
			oil.next_change_date AS next_oil_date, oil.next_change_km AS next_oil_km
		FROM `tabTruck` t
		LEFT JOIN `tabEmployee` e ON e.name = t.driver
		LEFT JOIN `tabCR Document Item` d
			ON d.parent = t.name AND d.parenttype = 'Truck'
		LEFT JOIN `tabTruck Oil Change` oil
			ON oil.parent = t.name AND oil.change_date = (
				SELECT MAX(o2.change_date) FROM `tabTruck Oil Change` o2 WHERE o2.parent = t.name
			)
		WHERE {" AND ".join(conditions)}
		ORDER BY t.name, d.expiry_date
		""",
		values,
		as_dict=True,
	)
