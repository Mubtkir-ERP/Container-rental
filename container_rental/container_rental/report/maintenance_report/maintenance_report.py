# S12 — maintenance follow-up: flattened Truck Maintenance Log child rows.
import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "vehicle_no", "label": _("Vehicle No"), "fieldtype": "Link", "options": "Truck", "width": 130},
		{"fieldname": "maintenance_date", "label": _("Maintenance Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "maintenance_type", "label": _("Maintenance Type"), "fieldtype": "Data", "width": 120},
		{"fieldname": "cost", "label": _("Cost"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "odometer_km", "label": _("Odometer at Maintenance"), "fieldtype": "Int", "width": 140},
		{"fieldname": "next_maintenance_date", "label": _("Next Maintenance Date"), "fieldtype": "Date", "width": 140},
		{"fieldname": "next_maintenance_km", "label": _("Next Maintenance Km"), "fieldtype": "Int", "width": 150},
		{"fieldname": "notes", "label": _("Notes"), "fieldtype": "Data", "width": 180},
	]


def get_data(filters):
	conditions = ["1=1"]
	values = {}
	if filters.get("vehicle"):
		conditions.append("m.parent = %(vehicle)s")
		values["vehicle"] = filters["vehicle"]
	if filters.get("maintenance_type"):
		conditions.append("m.maintenance_type = %(maintenance_type)s")
		values["maintenance_type"] = filters["maintenance_type"]
	if filters.get("from_date"):
		conditions.append("m.maintenance_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		conditions.append("m.maintenance_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	return frappe.db.sql(
		f"""
		SELECT
			m.parent AS vehicle_no, m.maintenance_date, m.maintenance_type,
			m.cost, m.odometer_km, m.next_maintenance_date, m.next_maintenance_km, m.notes
		FROM `tabTruck Maintenance Log` m
		WHERE {" AND ".join(conditions)}
		ORDER BY m.maintenance_date DESC
		""",
		values,
		as_dict=True,
	)
