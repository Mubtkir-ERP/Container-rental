import frappe
from frappe.model.document import Document
from frappe.utils import getdate


class Truck(Document):
	def validate(self):
		if self.driver:
			from container_rental.container_rental import hr_utils

			hr_utils.ensure_driver(self.driver)

	def get_latest_oil_change(self):
		"""Latest row of the oil-change child table (drives the delay alerts)."""
		rows = sorted(
			self.oil_changes or [], key=lambda r: getdate(r.change_date), reverse=True
		)
		return rows[0] if rows else None


EXPENSE_TABLES = {
	"maintenance_log": ("Truck Maintenance Log", "maintenance_date", "maintenance_type"),
	"oil_changes": ("Truck Oil Change", "change_date", None),
}


@frappe.whitelist()
def make_expense_voucher(truck, table, row_name, payout_account, expense_account=None, posting_date=None):
	"""Pay one maintenance / oil-change row: a submitted Journal Entry
	(Dr vehicle expense / Cr cash or bank), the same shape the driver
	commission payout uses. The voucher is linked back on the row."""
	from frappe import _
	from frappe.utils import flt, today

	if not set(frappe.get_roles()) & {"Container Manager", "Accounts Manager", "System Manager"}:
		frappe.throw(_("صرف مصاريف السيارات يتطلب صلاحية مدير الحاويات"), frappe.PermissionError)
	if table not in EXPENSE_TABLES:
		frappe.throw(_("جدول غير معروف: {0}").format(table))
	if not payout_account:
		frappe.throw(_("اختر حساب الصرف (الصندوق أو البنك)"))

	doc = frappe.get_doc("Truck", truck)
	row = next((r for r in (doc.get(table) or []) if r.name == row_name), None)
	if not row:
		frappe.throw(_("لم يُعثر على البند المطلوب"))
	if row.journal_entry:
		frappe.throw(_("صُرف هذا البند بالفعل بالسند {0}").format(row.journal_entry))
	if flt(row.cost) <= 0:
		frappe.throw(_("أدخل تكلفة البند أولًا"))

	account = expense_account or row.expense_account or frappe.db.get_single_value(
		"Container Rental Settings", "maintenance_expense_account"
	)
	if not account:
		frappe.throw(_("حدد حساب مصروف السيارات في إعدادات النظام أو في البند"))

	_dt, date_field, type_field = EXPENSE_TABLES[table]
	label = row.get(type_field) if type_field else _("غيار زيت")
	posting_date = posting_date or row.get(date_field) or today()
	entry = frappe.get_doc({
		"doctype": "Journal Entry",
		"voucher_type": "Journal Entry",
		"company": frappe.db.get_value("Account", account, "company"),
		"posting_date": posting_date,
		"user_remark": _("مصروف السيارة {0} — {1}").format(truck, label),
		"accounts": [
			{"account": account, "debit_in_account_currency": flt(row.cost)},
			{"account": payout_account, "credit_in_account_currency": flt(row.cost)},
		],
	})
	entry.flags.ignore_permissions = True
	entry.insert()
	entry.submit()

	row.db_set("journal_entry", entry.name)
	row.db_set("paid_on", posting_date)
	if expense_account:
		row.db_set("expense_account", account)
	doc.add_comment("Info", _("سند صرف {0} لبند {1} بمبلغ {2}").format(entry.name, label, flt(row.cost)))
	return entry.name


@frappe.whitelist()
def get_unpaid_expense_rows(truck):
	"""Rows of both expense tables that still have no voucher."""
	doc = frappe.get_doc("Truck", truck)
	out = []
	for table, (_dt, date_field, type_field) in EXPENSE_TABLES.items():
		for row in doc.get(table) or []:
			if row.journal_entry or not row.cost:
				continue
			out.append({
				"table": table,
				"row_name": row.name,
				"date": row.get(date_field),
				"label": row.get(type_field) if type_field else "Oil Change",
				"cost": row.cost,
			})
	return sorted(out, key=lambda r: str(r["date"] or ""))
