"""Create the app's custom roles before doctype sync so DocPerm rows resolve.

Idempotent — skips roles that already exist.
"""

import frappe

ROLES = [
	"Customer Service",
	"Transfer Follow-up",
	"Driver Supervisor",
	"Container Manager",
]


def execute():
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({
				"doctype": "Role",
				"role_name": role,
				"desk_access": 1,
			}).insert(ignore_permissions=True)
	frappe.db.commit()
