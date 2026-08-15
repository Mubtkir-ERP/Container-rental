import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today


class DriverCommissionEntry(Document):
	pass


def create_commission_entry(driver, reference_doctype, reference_name, container=None, client=None):
	"""Create a commission entry frozen at the driver's current per-delivery rate.

	Called by delivery controllers on every successful container delivery (section 6).
	"""
	rate = flt(frappe.db.get_value("CR Employee", driver, "commission_per_delivery"))
	entry = frappe.get_doc({
		"doctype": "Driver Commission Entry",
		"driver": driver,
		"commission_amount": rate,
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
