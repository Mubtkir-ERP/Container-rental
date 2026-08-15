# Section 9 — monthly contract invoices follow-up.
import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "invoice", "label": _("الفاتورة"), "fieldtype": "Link", "options": "Contract Monthly Invoice", "width": 150},
		{"fieldname": "contract", "label": _("العقد"), "fieldtype": "Link", "options": "Container Contract", "width": 140},
		{"fieldname": "client_name", "label": _("العميل"), "fieldtype": "Data", "width": 160},
		{"fieldname": "month_key", "label": _("الشهر"), "fieldtype": "Data", "width": 90},
		{"fieldname": "trips", "label": _("عدد الرحلات المفوترة"), "fieldtype": "Int", "width": 130},
		{"fieldname": "total_amount", "label": _("الإجمالي"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "paid_amount", "label": _("المدفوع"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "payment_status", "label": _("حالة السداد"), "fieldtype": "Data", "width": 110},
		{"fieldname": "whatsapp_sent", "label": _("أُرسلت واتساب"), "fieldtype": "Check", "width": 100},
	]


def get_data(filters):
	conditions = ["i.docstatus = 1"]
	values = {}
	if filters.get("contract"):
		conditions.append("i.contract = %(contract)s")
		values["contract"] = filters["contract"]
	if filters.get("client"):
		conditions.append("i.client = %(client)s")
		values["client"] = filters["client"]
	if filters.get("month_key"):
		conditions.append("i.month_key = %(month_key)s")
		values["month_key"] = filters["month_key"]
	if filters.get("payment_status"):
		conditions.append("i.payment_status = %(payment_status)s")
		values["payment_status"] = filters["payment_status"]

	return frappe.db.sql(
		f"""
		SELECT
			i.name AS invoice, i.contract, cl.customer_name AS client_name, i.month_key,
			(SELECT COALESCE(SUM(l.trips_delivered), 0)
			 FROM `tabMonthly Invoice Line` l WHERE l.parent = i.name) AS trips,
			i.total_amount, i.paid_amount, i.payment_status, i.whatsapp_sent
		FROM `tabContract Monthly Invoice` i
		LEFT JOIN `tabCustomer` cl ON cl.name = i.client
		WHERE {" AND ".join(conditions)}
		ORDER BY i.month_key DESC, i.contract
		""",
		values,
		as_dict=True,
	)
