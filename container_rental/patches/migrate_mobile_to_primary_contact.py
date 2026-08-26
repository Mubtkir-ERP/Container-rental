"""Move the legacy Customer.cr_mobile_no custom field into the standard
ERPNext primary Contact (Customer.mobile_no) — the field frappe_whatsapp
resolves recipients from — then drop the custom field. Idempotent."""

import frappe
from erpnext.selling.doctype.customer.customer import make_contact

LEGACY_FIELD = "cr_mobile_no"


def execute():
	if not frappe.db.has_column("Customer", LEGACY_FIELD):
		return

	customers = frappe.get_all(
		"Customer",
		filters={LEGACY_FIELD: ["is", "set"]},
		fields=["name", "customer_name", "customer_type", LEGACY_FIELD, "customer_primary_contact", "mobile_no"],
	)
	for customer in customers:
		_attach_mobile(customer, customer[LEGACY_FIELD])

	frappe.delete_doc("Custom Field", f"Customer-{LEGACY_FIELD}", ignore_missing=True, force=True)
	frappe.clear_cache(doctype="Customer")


def _attach_mobile(customer, mobile):
	contact_name = customer.customer_primary_contact or frappe.db.get_value(
		"Dynamic Link",
		{"link_doctype": "Customer", "link_name": customer.name, "parenttype": "Contact"},
		"parent",
	)
	if contact_name:
		contact = frappe.get_doc("Contact", contact_name)
		contact.add_phone(mobile, is_primary_mobile_no=1)
		contact.flags.ignore_permissions = True
		contact.save()
	else:
		doc = frappe.get_doc("Customer", customer.name)
		doc.mobile_no = mobile
		doc.flags.ignore_permissions = True
		contact = make_contact(doc)

	frappe.db.set_value(
		"Customer",
		customer.name,
		{"customer_primary_contact": contact.name, "mobile_no": contact.mobile_no or mobile},
		update_modified=False,
	)
