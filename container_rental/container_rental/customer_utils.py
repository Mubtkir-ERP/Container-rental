"""ERPNext Customer integration helpers.

Clients are ERPNext Customers extended with app custom fields (module
"Container Rental", created by patches.add_customer_fields):
- cr_mobile_no          رقم الجوال (واتساب)
- cr_account_type       نوع الحساب (نقدي / آجل)
- cr_delivery_locations العناوين / المواقع (child: Client Address)
- cr_rental_balance     الرصيد الحالي (إجمالي المستحق من التأجير)
"""

import frappe


def get_mobile(customer):
	return frappe.db.get_value("Customer", customer, "cr_mobile_no")


def get_name_and_mobile(customer):
	return frappe.db.get_value("Customer", customer, ["customer_name", "cr_mobile_no"])


def refresh_balance(customer):
	"""Recompute the customer's outstanding rental balance (document 2.4:
	'الرصيد الحالي = إجمالي المستحق على العميل'). Called by transaction
	controllers; stored on the Customer custom field."""
	unpaid_orders = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(rental_value), 0) FROM `tabContainer Order`
		WHERE client = %s AND payment_method = 'آجل' AND payment_received = 0
		  AND status = 'تم التوصيل'
		""",
		customer,
	)[0][0]

	unpaid_rentals = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(amount), 0) FROM `tabContainer Rental`
		WHERE client = %s AND payment_method = 'آجل' AND docstatus = 1
		""",
		customer,
	)[0][0]

	contract_outstanding = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(outstanding), 0) FROM `tabContainer Contract`
		WHERE client = %s AND docstatus = 1
		""",
		customer,
	)[0][0]

	balance = (unpaid_orders or 0) + (unpaid_rentals or 0) + (contract_outstanding or 0)
	frappe.db.set_value("Customer", customer, "cr_rental_balance", balance, update_modified=False)
	return balance
