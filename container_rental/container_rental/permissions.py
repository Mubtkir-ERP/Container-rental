"""Row-level security: drivers see only the orders assigned to them."""

import frappe

OFFICE_ROLES = {"System Manager", "Container Manager", "Customer Service", "Driver Supervisor", "Transfer Follow-up"}


def _driver_employee(user):
	"""Employee of a driver-only user, else None (office users are unrestricted)."""
	if not user or user == "Administrator":
		return None
	roles = set(frappe.get_roles(user))
	if "Driver" not in roles or roles & OFFICE_ROLES:
		return None
	return frappe.db.get_value("Employee", {"user_id": user}) or "__none__"


def order_query_conditions(user=None):
	employee = _driver_employee(user or frappe.session.user)
	if employee is None:
		return ""
	return f"`tabContainer Order`.assigned_driver = {frappe.db.escape(employee)}"


def order_has_permission(doc, ptype=None, user=None):
	employee = _driver_employee(user or frappe.session.user)
	if employee is None:
		return True
	return doc.assigned_driver == employee
