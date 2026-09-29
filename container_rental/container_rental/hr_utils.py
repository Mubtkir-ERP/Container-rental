"""ERPNext HR/Selling integration helpers.

Drivers and supervisors are ERPNext Employees (designation سائق / مشرف سواقين).
Per-delivery commissions live on the driver's Sales Person record
(custom field cr_commission_per_delivery, linked to the Employee)."""

import frappe
from frappe import _

DRIVER_DESIGNATION = "سائق"
SUPERVISOR_DESIGNATION = "مشرف سواقين"


def is_driver(employee):
	"""A driver is an employee whose designation is سائق OR who is flagged as
	also driving (cr_is_driver) — supervisors are commonly 2-in-1: they
	supervise and drive, so they can take an order themselves."""
	info = frappe.db.get_value("Employee", employee, ["designation", "cr_is_driver"], as_dict=True)
	if not info:
		return False
	return info.designation == DRIVER_DESIGNATION or bool(info.cr_is_driver)


def ensure_driver(employee):
	if not is_driver(employee):
		frappe.throw(_(
			"الموظف المختار ليس سائقًا — اجعل مسماه الوظيفي (سائق) أو فعّل خيار "
			"(يعمل كسائق أيضًا) في بطاقة الموظف"
		))


def get_session_employee(user=None):
	"""Employee linked to the logged-in user, if any."""
	return frappe.db.get_value("Employee", {"user_id": user or frappe.session.user, "status": "Active"})


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def driver_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link-field query for driver pickers: active employees who drive, by
	designation or by the (works as a driver too) flag."""
	like = f"%{txt or ''}%"
	return frappe.db.sql(
		"""
		SELECT name, employee_name, designation
		FROM `tabEmployee`
		WHERE status = 'Active'
		  AND (designation = %(designation)s OR IFNULL(cr_is_driver, 0) = 1)
		  AND (name LIKE %(txt)s OR employee_name LIKE %(txt)s)
		ORDER BY employee_name
		LIMIT %(start)s, %(page_len)s
		""",
		{"designation": DRIVER_DESIGNATION, "txt": like, "start": start, "page_len": page_len},
	)


@frappe.whitelist()
def get_my_driver_employee():
	"""Employee id of the logged-in user when he drives (a 2-in-1 supervisor
	included) — lets the desk offer him self-assignment and the delivery
	confirmation on his own orders."""
	employee = get_session_employee()
	if employee and is_driver(employee):
		return employee
	return None


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


def get_supervisor_contact(container_size=None):
	"""Supervisor is a system User. Each container size can have its own
	supervisor (Container Size.supervisor — e.g. big vs small containers);
	Container Rental Settings.default_supervisor is the fallback."""
	user = None
	if container_size:
		user = frappe.db.get_value("Container Size", container_size, "supervisor")
	if not user:
		user = frappe.get_cached_doc("Container Rental Settings").default_supervisor
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
