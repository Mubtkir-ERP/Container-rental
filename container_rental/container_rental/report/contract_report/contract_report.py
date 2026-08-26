# S10 — تقرير العقود: all 16 columns of the reference screen.
import frappe
from frappe import _


def execute(filters=None):
	return get_columns(), get_data(filters or {})


def get_columns():
	return [
		{"fieldname": "idx", "label": _("#"), "fieldtype": "Int", "width": 50},
		{"fieldname": "contract_no", "label": _("رقم العقد"), "fieldtype": "Link", "options": "Container Contract", "width": 140},
		{"fieldname": "client_name", "label": _("اسم العميل"), "fieldtype": "Data", "width": 160},
		{"fieldname": "mobile_no", "label": _("رقم تليفون العميل"), "fieldtype": "Data", "width": 120},
		{"fieldname": "duration_days", "label": _("مدة التعاقد (أيام)"), "fieldtype": "Int", "width": 110},
		{"fieldname": "start_date", "label": _("تاريخ بداية العقد"), "fieldtype": "Date", "width": 110},
		{"fieldname": "end_date", "label": _("تاريخ انتهاء العقد"), "fieldtype": "Date", "width": 110},
		{"fieldname": "contract_value", "label": _("إجمالي التعاقد"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "paid_amount", "label": _("المدفوع"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "tax_on_paid", "label": _("الضرائب على المدفوع"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "outstanding", "label": _("المتبقي (عليه)"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "total_trips", "label": _("عدد الرحلات"), "fieldtype": "Int", "width": 100},
		{"fieldname": "remaining_trips", "label": _("الرحلات المتبقية"), "fieldtype": "Int", "width": 110},
		{"fieldname": "last_container", "label": _("رقم آخر حاوية"), "fieldtype": "Link", "options": "Container", "width": 120},
		{"fieldname": "owner_user", "label": _("أُضيف بواسطة"), "fieldtype": "Link", "options": "User", "width": 140},
		{"fieldname": "contract_status", "label": _("حالة العقد"), "fieldtype": "Data", "width": 90},
		{"fieldname": "actions", "label": _("إجراءات"), "fieldtype": "Data", "width": 200},
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
	if filters.get("status") and filters["status"] != "الكل":
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
			c.start_date, c.end_date, c.contract_value,
			c.paid_amount, c.tax_on_paid, c.outstanding,
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
