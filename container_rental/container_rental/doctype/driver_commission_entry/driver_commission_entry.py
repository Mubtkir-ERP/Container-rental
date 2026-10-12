import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today


class DriverCommissionEntry(Document):
	pass


def create_commission_entry(driver, reference_doctype, reference_name, container=None, client=None,
	base_amount=0, container_size=None):
	"""Driver commission per the container size's rule (a percentage of the
	order value or a fixed amount per delivery), falling back to the default
	percent. Frozen on the entry — with its basis and expense account — when
	it is created, so later rate changes never rewrite history."""
	from container_rental.container_rental import hr_utils

	sales_person, amount, basis, expense_account = hr_utils.resolve_commission(
		driver, container_size, base_amount)
	entry = frappe.get_doc({
		"doctype": "Driver Commission Entry",
		"driver": driver,
		"sales_person": sales_person,
		"commission_amount": amount,
		"commission_basis": basis,
		"expense_account": expense_account,
		"entry_date": today(),
		"container": container,
		"client": client,
		"delivery_reference_doctype": reference_doctype,
		"delivery_reference": reference_name,
		"payout_status": "Due",
	})
	entry.flags.ignore_permissions = True
	entry.insert()
	return entry


@frappe.whitelist()
def mark_paid(names, payout_account=None, posting_date=None):
	"""Pay out commissions: one submitted Journal Entry per driver
	(Dr commission expense / Cr payout account, e.g. the driver's cash box).
	Entries are marked مصروفة and linked to the Journal Entry."""
	from frappe.utils import flt, today as _today

	if not set(frappe.get_roles()) & {"Container Manager", "Accounts Manager", "System Manager"}:
		frappe.throw(_("صرف العمولات يتطلب صلاحية مدير الحاويات"), frappe.PermissionError)
	if isinstance(names, str):
		names = frappe.parse_json(names)
	default_account = frappe.db.get_single_value("Container Rental Settings", "commission_expense_account")
	if not payout_account:
		frappe.throw(_("اختر حساب الصرف (صندوق السائق أو البنك)"))

	posting_date = posting_date or _today()
	# Each size can book its commissions to its own expense account, so entries
	# are grouped by (driver, account) — one Journal Entry per combination
	by_driver = {}
	for name in names:
		doc = frappe.get_doc("Driver Commission Entry", name)
		if doc.payout_status != "Due" or flt(doc.commission_amount) <= 0:
			continue
		account = doc.expense_account or default_account
		if not account:
			frappe.throw(_("حدد حساب مصروف العمولات في حجم الحاوية أو في إعدادات النظام أولًا"))
		by_driver.setdefault((doc.driver, account), []).append(doc)

	count = 0
	for (driver, expense_account), docs in by_driver.items():
		total = sum(flt(d.commission_amount) for d in docs)
		company = frappe.db.get_value("Account", expense_account, "company")
		driver_name = frappe.db.get_value("Employee", driver, "employee_name")
		je = frappe.get_doc({
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"company": company,
			"posting_date": posting_date,
			"user_remark": _("عمولة السائق {0} — {1} توصيلة").format(driver_name, len(docs)),
			"accounts": [
				{"account": expense_account, "debit_in_account_currency": total},
				{"account": payout_account, "credit_in_account_currency": total},
			],
		})
		je.flags.ignore_permissions = True
		je.insert()
		je.submit()
		for d in docs:
			d.db_set("payout_status", "Paid Out")
			d.db_set("paid_on", posting_date)
			d.db_set("journal_entry", je.name)
			count += 1
	return count
