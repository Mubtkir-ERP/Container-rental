# S9 "التقرير العام للحاويات" — full container list plus a status×size×classification summary.
import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	data += get_summary_rows(filters)
	return columns, data


def get_columns():
	return [
		{"fieldname": "container_no", "label": _("رقم الحاوية"), "fieldtype": "Link", "options": "Container", "width": 130},
		{"fieldname": "size", "label": _("الحجم"), "fieldtype": "Data", "width": 100},
		{"fieldname": "classification", "label": _("التصنيف"), "fieldtype": "Data", "width": 120},
		{"fieldname": "branch", "label": _("الفرع"), "fieldtype": "Data", "width": 120},
		{"fieldname": "responsible_driver_name", "label": _("السائق المسؤول"), "fieldtype": "Data", "width": 140},
		{"fieldname": "status", "label": _("الحالة"), "fieldtype": "Data", "width": 100},
		{"fieldname": "last_delivery_datetime", "label": _("آخر توصيل"), "fieldtype": "Datetime", "width": 150},
		{"fieldname": "last_unload_datetime", "label": _("آخر تفريغ"), "fieldtype": "Datetime", "width": 150},
		{"fieldname": "count", "label": _("العدد"), "fieldtype": "Int", "width": 80},
	]


def _conditions(filters, values):
	conditions = ["1=1"]
	for field in ("status", "size", "classification", "branch"):
		if filters.get(field):
			conditions.append(f"c.{field} = %({field})s")
			values[field] = filters[field]
	return " AND ".join(conditions)


def get_data(filters):
	values = {}
	return frappe.db.sql(
		f"""
		SELECT
			c.name AS container_no, c.size, c.classification, c.branch,
			e.employee_name AS responsible_driver_name, c.status,
			c.last_delivery_datetime, c.last_unload_datetime
		FROM `tabContainer` c
		LEFT JOIN `tabEmployee` e ON e.name = c.responsible_driver
		WHERE {_conditions(filters, values)}
		ORDER BY c.status, c.size, c.name
		""",
		values,
		as_dict=True,
	)


def get_summary_rows(filters):
	values = {}
	summary = frappe.db.sql(
		f"""
		SELECT c.status, c.size, COALESCE(c.classification, '-') AS classification,
		       COUNT(*) AS count
		FROM `tabContainer` c
		WHERE {_conditions(filters, values)}
		GROUP BY c.status, c.size, c.classification
		ORDER BY c.status, c.size
		""",
		values,
		as_dict=True,
	)
	if not summary:
		return []
	rows = [{}, {"container_no": _("— ملخص حسب الحالة / الحجم / التصنيف —")}]
	for row in summary:
		rows.append({
			"container_no": "",
			"status": row.status,
			"size": row.size,
			"classification": row.classification,
			"count": row.count,
		})
	return rows
