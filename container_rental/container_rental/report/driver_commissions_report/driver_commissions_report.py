# Section 6 — driver commissions per period: deliveries count, totals, payout status.
import frappe
from frappe import _
from frappe.utils import get_first_day, today


def execute(filters=None):
	filters = filters or {}
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "driver_name", "label": _("السائق"), "fieldtype": "Data", "width": 180},
		{"fieldname": "entry", "label": _("قيد العمولة"), "fieldtype": "Link", "options": "Driver Commission Entry", "width": 140},
		{"fieldname": "entry_date", "label": _("التاريخ"), "fieldtype": "Date", "width": 100},
		{"fieldname": "container", "label": _("الحاوية"), "fieldtype": "Link", "options": "Container", "width": 110},
		{"fieldname": "client_name", "label": _("العميل"), "fieldtype": "Data", "width": 150},
		{"fieldname": "deliveries", "label": _("عدد التوصيلات"), "fieldtype": "Int", "width": 110},
		{"fieldname": "commission_amount", "label": _("العمولة"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "due_amount", "label": _("المستحق"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "paid_amount", "label": _("المصروف"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "payout_status", "label": _("حالة الصرف"), "fieldtype": "Data", "width": 100},
	]


def get_data(filters):
	conditions = ["1=1"]
	values = {}
	if filters.get("driver"):
		conditions.append("dce.driver = %(driver)s")
		values["driver"] = filters["driver"]
	values["from_date"] = filters.get("from_date") or get_first_day(today())
	conditions.append("dce.entry_date >= %(from_date)s")
	if filters.get("to_date"):
		conditions.append("dce.entry_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]
	if filters.get("payout_status"):
		conditions.append("dce.payout_status = %(payout_status)s")
		values["payout_status"] = filters["payout_status"]

	entries = frappe.db.sql(
		f"""
		SELECT
			dce.name AS entry, dce.driver, e.employee_name AS driver_name,
			dce.entry_date, dce.container, cl.customer_name AS client_name,
			dce.commission_amount, dce.payout_status
		FROM `tabDriver Commission Entry` dce
		LEFT JOIN `tabCR Employee` e ON e.name = dce.driver
		LEFT JOIN `tabCustomer` cl ON cl.name = dce.client
		WHERE {" AND ".join(conditions)}
		ORDER BY e.employee_name, dce.entry_date
		""",
		values,
		as_dict=True,
	)

	# Group: one summary row per driver followed by detail rows (indent tree)
	data = []
	by_driver = {}
	for entry in entries:
		by_driver.setdefault(entry.driver_name or entry.driver, []).append(entry)

	for driver_name, rows in by_driver.items():
		due = sum(r.commission_amount for r in rows if r.payout_status == "مستحقة")
		paid = sum(r.commission_amount for r in rows if r.payout_status == "مصروفة")
		data.append({
			"driver_name": driver_name,
			"deliveries": len(rows),
			"due_amount": due,
			"paid_amount": paid,
			"indent": 0,
		})
		for r in rows:
			data.append({
				"driver_name": "",
				"entry": r.entry,
				"entry_date": r.entry_date,
				"container": r.container,
				"client_name": r.client_name,
				"commission_amount": r.commission_amount,
				"payout_status": r.payout_status,
				"indent": 1,
			})
	return data
