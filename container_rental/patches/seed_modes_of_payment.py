"""Payment methods now link to ERPNext's Mode of Payment. Seed the three
modes the app logic uses so existing stored values stay valid. Idempotent."""

import frappe

MODES = [
	("نقدي", "Cash"),
	("تحويل بنكي", "Bank"),
	("آجل", "General"),
]


def execute():
	for name, mode_type in MODES:
		if not frappe.db.exists("Mode of Payment", name):
			frappe.get_doc({
				"doctype": "Mode of Payment",
				"mode_of_payment": name,
				"type": mode_type,
				"enabled": 1,
			}).insert(ignore_permissions=True)
	frappe.db.commit()
