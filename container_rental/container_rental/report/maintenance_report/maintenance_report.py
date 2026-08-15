# S12 — maintenance follow-up: flattened Truck Maintenance Log child rows.
import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "vehicle_no", "label": _("رقم السيارة"), "fieldtype": "Link", "options": "Truck", "width": 130},
		{"fieldname": "maintenance_date", "label": _("تاريخ الصيانة"), "fieldtype": "Date", "width": 110},
		{"fieldname": "maintenance_type", "label": _("نوع الصيانة"), "fieldtype": "Data", "width": 120},
		{"fieldname": "cost", "label": _("التكلفة"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "odometer_km", "label": _("الكيلومتر عند الصيانة"), "fieldtype": "Int", "width": 140},
		{"fieldname": "next_maintenance_date", "label": _("تاريخ الصيانة القادمة"), "fieldtype": "Date", "width": 140},
		{"fieldname": "next_maintenance_km", "label": _("كيلومتر الصيانة القادمة"), "fieldtype": "Int", "width": 150},
		{"fieldname": "notes", "label": _("ملاحظات"), "fieldtype": "Data", "width": 180},
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
