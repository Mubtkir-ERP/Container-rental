import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today


class DriverCommissionEntry(Document):
	pass


def create_commission_entry(driver, reference_doctype, reference_name, container=None, client=None):
	"""Commission per successful delivery (section 6), leveraging ERPNext
	Sales Person: the driver's Sales Person record (linked via its employee
	field) carries the flat rate in the custom field cr_commission_per_delivery.
	The amount is frozen on the entry at delivery time."""
	from container_rental.container_rental import hr_utils

	sales_person, rate = hr_utils.get_commission_per_delivery(driver)
	entry = frappe.get_doc({
		"doctype": "Driver Commission Entry",
		"driver": driver,
		"sales_person": sales_person,
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
