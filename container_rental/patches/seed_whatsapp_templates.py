"""Seed the six event templates (requirements section 5) into frappe_whatsapp's
"WhatsApp Templates" doctype so admins can edit the Arabic bodies from the desk.

Idempotent — existing templates are left untouched so admin edits survive."""

import frappe

from container_rental.container_rental.whatsapp import DEFAULT_TEMPLATES


def execute():
	if "frappe_whatsapp" not in frappe.get_installed_apps():
		return

	language = "ar" if frappe.db.exists("Language", "ar") else frappe.db.get_default("language") or "en"
	for key, template in DEFAULT_TEMPLATES.items():
		if frappe.db.exists("WhatsApp Templates", {"template_name": key}):
			continue
		frappe.get_doc({
			"doctype": "WhatsApp Templates",
			"template_name": key,
			"actual_name": key,
			"template": template["body"],
			"language": language,
			"language_code": language,
			"category": "UTILITY",
			"status": "Local",
		}).insert(ignore_permissions=True)
	frappe.db.commit()
