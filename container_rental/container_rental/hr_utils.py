"""ERPNext HR/Selling integration helpers.

Drivers and supervisors are ERPNext Employees (designation سائق / مشرف سواقين).
Per-delivery commissions live on the driver's Sales Person record
(custom field cr_commission_per_delivery, linked to the Employee)."""

import frappe
from frappe import _

DRIVER_DESIGNATION = "سائق"
SUPERVISOR_DESIGNATION = "مشرف سواقين"


def ensure_driver(employee):
	if frappe.db.get_value("Employee", employee, "designation") != DRIVER_DESIGNATION:
		frappe.throw(_("الموظف المختار ليس سائقًا (المسمى الوظيفي يجب أن يكون سائق)"))


def get_employee_name(employee):
	return frappe.db.get_value("Employee", employee, "employee_name")


def get_employee_mobile(employee):
	return frappe.db.get_value("Employee", employee, "cell_number")


def get_sales_person(employee):
	"""The driver's Sales Person record (linked via its employee field)."""
	return frappe.db.get_value("Sales Person", {"employee": employee, "enabled": 1})


def get_commission_per_delivery(employee):
	sales_person = get_sales_person(employee)
	if not sales_person:
		return None, 0
	rate = frappe.db.get_value("Sales Person", sales_person, "cr_commission_per_delivery")
	return sales_person, frappe.utils.flt(rate)


def ensure_sales_person(employee):
	"""Create (or fetch) the Sales Person for a driver employee."""
	existing = get_sales_person(employee)
	if existing:
		return existing
	employee_name = get_employee_name(employee)
	root = frappe.db.get_value("Sales Person", {"is_group": 1, "parent_sales_person": ("is", "not set")})
	doc = frappe.get_doc({
		"doctype": "Sales Person",
		"sales_person_name": employee_name,
		"parent_sales_person": root,
		"is_group": 0,
		"enabled": 1,
		"employee": employee,
	})
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert()
	return doc.name


def get_supervisor_contact():
	"""Supervisor is a system User (Container Rental Settings.default_supervisor)."""
	settings = frappe.get_cached_doc("Container Rental Settings")
	user = settings.default_supervisor
	if not user:
		return None, None, None
	full_name, mobile = frappe.db.get_value("User", user, ["full_name", "mobile_no"])
	return user, full_name, mobile


def get_commission_percent(employee):
	"""Commission % of the order value: Sales Person.commission_rate, else the
	default from Container Rental Settings (4%)."""
	sales_person = get_sales_person(employee)
	rate = 0
	if sales_person:
		rate = frappe.utils.flt(frappe.db.get_value("Sales Person", sales_person, "commission_rate"))
	if not rate:
		rate = frappe.utils.flt(
			frappe.db.get_single_value("Container Rental Settings", "default_commission_percent")
		) or 4
	return sales_person, rate
