import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today


class DriverCommissionEntry(Document):
	pass


def create_commission_entry(driver, reference_doctype, reference_name, container=None, client=None, base_amount=0):
	"""Driver commission = base amount × commission % (Sales Person.commission_rate
	or the settings default). Frozen on the entry when it is created."""
	from container_rental.container_rental import hr_utils
	from frappe.utils import flt

	sales_person, percent = hr_utils.get_commission_percent(driver)
	entry = frappe.get_doc({
		"doctype": "Driver Commission Entry",
		"driver": driver,
		"sales_person": sales_person,
		"commission_amount": flt(base_amount) * flt(percent) / 100,
		"entry_date": today(),
		"container": container,
		"client": client,
		"delivery_reference_doctype": reference_doctype,
		"delivery_reference": reference_name,
		"payout_status": "مستحقة",
	})
	entry.flags.ignore_permissions = True
	entry.insert()
	return entry


@frappe.whitelist()
def mark_paid(names):
	"""Bulk payout action for the commissions report / list view."""
	if not set(frappe.get_roles()) & {"Container Manager", "System Manager"}:
		frappe.throw(_("صرف العمولات يتطلب صلاحية مدير الحاويات"), frappe.PermissionError)
	if isinstance(names, str):
		names = frappe.parse_json(names)
	count = 0
	for name in names:
		doc = frappe.get_doc("Driver Commission Entry", name)
		if doc.payout_status == "مستحقة":
			doc.db_set("payout_status", "مصروفة")
			doc.db_set("paid_on", today())
			count += 1
	return count
