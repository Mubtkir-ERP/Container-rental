"""Role Profiles for the container-rental jobs + Custom DocPerms that let the
app roles use the ERPNext doctypes they depend on (Customer, Employee, Sales
Person, Sales Invoice, Account, Mode of Payment...). Idempotent."""

import frappe
from frappe.permissions import add_permission, update_permission_property

# doctype → {role: [ptypes]}  (read is always granted with the row, except
# "select"-only rows: link search / titles without access to the documents)
ERPNEXT_PERMS = {
	"Customer": {
		"Customer Service": ["read", "write", "create"],
		"Transfer Follow-up": ["read"],
		"Driver Supervisor": ["read"],
		"Container Manager": ["read", "write", "create"],
		"Driver": ["select"],  # the order list filters on the customer title field
	},
	"Employee": {
		"Customer Service": ["read"],
		"Driver Supervisor": ["read", "write"],
		"Container Manager": ["read", "write", "create"],
	},
	"Sales Person": {
		"Driver Supervisor": ["read"],
		"Container Manager": ["read", "write", "create"],
	},
	"Sales Invoice": {
		"Customer Service": ["read", "write", "create"],
		"Transfer Follow-up": ["read", "write", "create", "submit"],
		"Container Manager": ["read", "write", "create", "submit", "cancel"],
	},
	"Account": {
		"Customer Service": ["read"],
		"Transfer Follow-up": ["read"],
		"Container Manager": ["read"],
	},
	"Mode of Payment": {
		"Customer Service": ["read"],
		"Transfer Follow-up": ["read"],
		"Driver Supervisor": ["read"],
		"Driver": ["read"],
		"Container Manager": ["read"],
	},
	"Journal Entry": {
		"Container Manager": ["read"],
	},
	"WhatsApp Templates": {
		"Container Manager": ["read", "write"],
	},
	"WhatsApp Message": {
		"Container Manager": ["read"],
	},
}

ROLE_PROFILES = {
	"Container Rental - Customer Service": ["Customer Service"],
	"Container Rental - Transfer Follow-up": ["Transfer Follow-up"],
	"Container Rental - Drivers Supervisor": ["Driver Supervisor"],
	"Container Rental - Driver": ["Driver"],
	"Container Rental - Manager": [
		"Container Manager", "Customer Service", "Transfer Follow-up",
		"Driver Supervisor", "Accounts User", "Sales User",
	],
}


def execute():
	for doctype, roles in ERPNEXT_PERMS.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		for role, ptypes in roles.items():
			if not frappe.db.exists("Role", role):
				continue
			if not frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0}):
				add_permission(doctype, role, 0)
			if ptypes == ["select"]:
				update_permission_property(doctype, role, 0, "read", 0)
			for ptype in ptypes:
				update_permission_property(doctype, role, 0, ptype, 1)

	for name, roles in ROLE_PROFILES.items():
		roles = [r for r in roles if frappe.db.exists("Role", r)]
		if frappe.db.exists("Role Profile", name):
			profile = frappe.get_doc("Role Profile", name)
			profile.set("roles", [])
		else:
			profile = frappe.new_doc("Role Profile")
			profile.role_profile = name
		for r in roles:
			profile.append("roles", {"role": r})
		profile.flags.ignore_permissions = True
		profile.save()
	frappe.db.commit()
