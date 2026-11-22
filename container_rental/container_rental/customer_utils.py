"""ERPNext Customer integration helpers.

Clients are ERPNext Customers extended with app custom fields (module
"Container Rental", created by patches.add_customer_fields):
- mobile_no             رقم الجوال (واتساب) — الحقل القياسي (جهة الاتصال الرئيسية)، نفس ما يقرأه frappe_whatsapp
- cr_account_type       نوع الحساب (Cash / Credit — يُعرض بالعربية عبر ملف الترجمة)
- cr_delivery_locations العناوين / المواقع (child: Client Address)
- cr_rental_balance     الرصيد الحالي (إجمالي المستحق من التأجير)
"""

import frappe
from frappe import _


def get_mobile(customer):
	return frappe.db.get_value("Customer", customer, "mobile_no")


def get_name_and_mobile(customer):
	return frappe.db.get_value("Customer", customer, ["customer_name", "mobile_no"])


def normalize_mobile(mobile_no):
	"""Digits only, last nine — so 0501234567, +966 50 123 4567 and
	966501234567 are recognised as one and the same number."""
	digits = "".join(ch for ch in str(mobile_no or "") if ch.isdigit())
	return digits[-9:] if len(digits) >= 9 else digits


def customer_with_mobile(mobile_no, exclude=None):
	"""The other customer already holding this number, if any."""
	normalized = normalize_mobile(mobile_no)
	if not normalized:
		return None
	rows = frappe.db.sql(
		"""
		SELECT name, customer_name, mobile_no FROM `tabCustomer`
		WHERE mobile_no IS NOT NULL AND mobile_no != ''
		  AND RIGHT(REGEXP_REPLACE(mobile_no, '[^0-9]', ''), 9) = %(mobile)s
		  AND name NOT IN %(exclude)s
		LIMIT 1
		""",
		{"mobile": normalized, "exclude": tuple(exclude or ["__none__"]) or ("__none__",)},
		as_dict=True,
	)
	return rows[0] if rows else None


def _throw_duplicate(mobile_no, other):
	frappe.throw(
		_("Mobile number {0} is already registered to customer {1} ({2}) — duplicate numbers are not allowed").format(
			mobile_no, other.customer_name or "", other.name
		),
		frappe.DuplicateEntryError,
	)


def validate_unique_mobile(doc, method=None):
	"""A client's number identifies him across orders and WhatsApp replies, so
	two customers must not share one. Records that already clash stay editable
	— only a number being set or changed is checked."""
	if not doc.mobile_no:
		return
	if not doc.is_new():
		before = doc.get_doc_before_save()
		if before and normalize_mobile(before.mobile_no) == normalize_mobile(doc.mobile_no):
			return
	other = customer_with_mobile(doc.mobile_no, exclude=[doc.name] if doc.name else None)
	if other:
		_throw_duplicate(doc.mobile_no, other)


def validate_contact_mobile(doc, method=None):
	"""The number lives on the customer's primary Contact once the customer
	exists, so the same rule has to hold when it is edited there."""
	mobile = doc.mobile_no or next(
		(row.phone for row in (doc.phone_nos or []) if row.is_primary_mobile_no), None
	)
	if not mobile:
		return
	owners = [
		link.link_name for link in (doc.links or [])
		if link.link_doctype == "Customer" and link.link_name
	]
	if not owners:
		return
	# Saving a customer rewrites his primary contact; when the contact merely
	# mirrors the number that customer already holds, this is an existing
	# record rather than a new clash and must stay editable
	normalized = normalize_mobile(mobile)
	for owner in owners:
		if normalize_mobile(frappe.db.get_value("Customer", owner, "mobile_no")) == normalized:
			return
	other = customer_with_mobile(mobile, exclude=owners)
	if other:
		_throw_duplicate(mobile, other)


def get_default_address(customer):
	"""The customer's default saved delivery location (Client Address child)."""
	if not customer:
		return None
	rows = frappe.get_all(
		"Client Address",
		filters={"parent": customer, "parenttype": "Customer"},
		fields=["address", "is_default"],
		order_by="is_default desc, idx asc",
		limit=1,
	)
	return rows[0].address if rows else None


def refresh_balance(customer):
	"""Recompute the customer's outstanding rental balance (document 2.4:
	'الرصيد الحالي = إجمالي المستحق على العميل'). Called by transaction
	controllers; stored on the Customer custom field."""
	unpaid_orders = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(rental_value), 0) FROM `tabContainer Order`
		WHERE client = %s AND payment_method IN ('آجل', 'Credit', 'D.Note') AND payment_received = 0
		  AND status = 'Delivered'
		""",
		customer,
	)[0][0]

	unpaid_rentals = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(amount), 0) FROM `tabContainer Rental`
		WHERE client = %s AND payment_method IN ('آجل', 'Credit', 'D.Note') AND docstatus = 1
		""",
		customer,
	)[0][0]

	# Contracts are billed through their monthly invoices, which carry their own
	# payment status — the contract document itself no longer tracks payments
	unpaid_contract_invoices = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(total_amount - COALESCE(paid_amount, 0)), 0)
		FROM `tabContract Monthly Invoice`
		WHERE client = %s AND docstatus = 1 AND payment_status != 'Paid'
		""",
		customer,
	)[0][0]

	balance = (unpaid_orders or 0) + (unpaid_rentals or 0) + (unpaid_contract_invoices or 0)
	frappe.db.set_value("Customer", customer, "cr_rental_balance", balance, update_modified=False)
	return balance
