"""Remove the app's early custom WhatsApp doctypes — messaging now goes through
the frappe_whatsapp app (WhatsApp Settings / Templates / Message).

Idempotent — skips doctypes that no longer exist."""

import frappe

OBSOLETE_DOCTYPES = [
	"Container WhatsApp Log",
	"Container WhatsApp Template",
	"Container WhatsApp Settings",
]


def execute():
	for doctype in OBSOLETE_DOCTYPES:
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, force=True, ignore_permissions=True, delete_permanently=True)
	frappe.db.commit()
