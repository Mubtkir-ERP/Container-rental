# S8 — truck document alerts with red highlighting via the .js formatter.
import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "vehicle_no", "label": _("رقم السيارة"), "fieldtype": "Link", "options": "Truck", "width": 120},
		{"fieldname": "branch", "label": _("الفرع"), "fieldtype": "Data", "width": 110},
		{"fieldname": "driver_name", "label": _("السائق"), "fieldtype": "Data", "width": 140},
		{"fieldname": "next_oil_change_km", "label": _("غيار الزيت / كم"), "fieldtype": "Int", "width": 110},
		{"fieldname": "next_oil_change_date", "label": _("تاريخ غيار الزيت"), "fieldtype": "Date", "width": 120},
		{"fieldname": "battery_change_date", "label": _("تاريخ تغيير البطارية"), "fieldtype": "Date", "width": 130},
		{"fieldname": "registration_expiry", "label": _("تاريخ انتهاء الاستمارة"), "fieldtype": "Date", "width": 140},
		{"fieldname": "insurance_expiry", "label": _("تاريخ انتهاء التأمين"), "fieldtype": "Date", "width": 130},
		{"fieldname": "operating_card_expiry", "label": _("تاريخ انتهاء كارت التشغيل"), "fieldtype": "Date", "width": 150},
		{"fieldname": "actions", "label": _("إجراءات"), "fieldtype": "Data", "width": 160},
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
			t.next_oil_change_km, t.next_oil_change_date, t.battery_change_date,
			t.registration_expiry, t.insurance_expiry, t.operating_card_expiry
		FROM `tabTruck` t
		LEFT JOIN `tabCR Employee` e ON e.name = t.driver
		WHERE {" AND ".join(conditions)}
		ORDER BY t.name
		""",
		values,
		as_dict=True,
	)
