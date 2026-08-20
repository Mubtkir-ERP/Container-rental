# S7 — employee document alerts from the Employee "المستندات" child table.
import frappe
from frappe import _
from frappe.utils import add_days, today


def execute(filters=None):
	filters = filters or {}
	settings = frappe.get_cached_doc("Container Rental Settings")
	horizon = add_days(today(), settings.expiry_alert_days or 30)
	message = _("الصفوف الملونة بالأحمر مستنداتها منتهية أو ستنتهي قبل {0}").format(
		frappe.format(horizon, {"fieldtype": "Date"})
	)
	return get_columns(), get_data(filters), message


def get_columns():
	return [
		{"fieldname": "employee", "label": _("الكود"), "fieldtype": "Link", "options": "Employee", "width": 110},
		{"fieldname": "employee_name", "label": _("اسم الموظف"), "fieldtype": "Data", "width": 160},
		{"fieldname": "branch", "label": _("الفرع"), "fieldtype": "Data", "width": 110},
		{"fieldname": "designation", "label": _("الوظيفة"), "fieldtype": "Data", "width": 130},
		{"fieldname": "cell_number", "label": _("رقم الجوال"), "fieldtype": "Data", "width": 110},
		{"fieldname": "document_name", "label": _("المستند"), "fieldtype": "Data", "width": 150},
		{"fieldname": "expiry_date", "label": _("تاريخ الانتهاء"), "fieldtype": "Date", "width": 120},
		{"fieldname": "attachment", "label": _("الملف"), "fieldtype": "Data", "width": 120},
		{"fieldname": "status", "label": _("حالة الموظف"), "fieldtype": "Data", "width": 100},
		{"fieldname": "actions", "label": _("إجراءات"), "fieldtype": "Data", "width": 140},
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
