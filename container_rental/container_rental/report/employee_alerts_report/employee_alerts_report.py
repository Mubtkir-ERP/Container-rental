# S7 — employee document alerts; expiry dates near/past are highlighted in the .js formatter.
import frappe
from frappe import _
from frappe.utils import add_days, today


def execute(filters=None):
	filters = filters or {}
	data = get_data(filters)
	settings = frappe.get_cached_doc("Container Rental Settings")
	horizon = add_days(today(), settings.expiry_alert_days or 30)
	message = _("الحقول الملونة بالأحمر منتهية أو ستنتهي قبل {0}").format(
		frappe.format(horizon, {"fieldtype": "Date"})
	)
	return get_columns(), data, message


def get_columns():
	return [
		{"fieldname": "employee", "label": _("الكود"), "fieldtype": "Link", "options": "CR Employee", "width": 110},
		{"fieldname": "employee_name", "label": _("اسم الموظف"), "fieldtype": "Data", "width": 160},
		{"fieldname": "branch", "label": _("الفرع"), "fieldtype": "Data", "width": 110},
		{"fieldname": "position", "label": _("الوظيفة"), "fieldtype": "Data", "width": 130},
		{"fieldname": "iqama_no", "label": _("رقم الإقامة"), "fieldtype": "Data", "width": 110},
		{"fieldname": "iqama_expiry", "label": _("تاريخ انتهاء الإقامة"), "fieldtype": "Date", "width": 130},
		{"fieldname": "insurance_expiry", "label": _("تاريخ انتهاء التأمين"), "fieldtype": "Date", "width": 130},
		{"fieldname": "driver_card_no", "label": _("كارت السائق"), "fieldtype": "Data", "width": 110},
		{"fieldname": "driver_card_expiry", "label": _("تاريخ انتهاء كارت السائق"), "fieldtype": "Date", "width": 150},
		{"fieldname": "status", "label": _("حالة الموظف"), "fieldtype": "Data", "width": 100},
		{"fieldname": "actions", "label": _("إجراءات"), "fieldtype": "Data", "width": 220},
	]


def get_data(filters):
	conditions = ["1=1"]
	values = {}
	if filters.get("employee"):
		conditions.append("e.name = %(employee)s")
		values["employee"] = filters["employee"]

	rows = frappe.db.sql(
		f"""
		SELECT
			e.name AS employee, e.employee_name, e.branch, e.position,
			e.iqama_no, e.iqama_expiry, e.insurance_expiry,
			e.driver_card_no, e.driver_card_expiry, e.status
		FROM `tabCR Employee` e
		WHERE {" AND ".join(conditions)}
		ORDER BY e.employee_name
		""",
		values,
		as_dict=True,
	)
	return rows
