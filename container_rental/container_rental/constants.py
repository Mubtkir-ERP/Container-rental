"""Stored values for the app's Select fields.

Values are stored in English and rendered in the user's language through
translations/ar.csv, so the same record reads "Delivered" for an English user
and "تم التوصيل" for an Arabic one. Legacy Arabic rows are converted by
patches/anglicize_select_values.py.
"""

# Container.status
CONTAINER_AVAILABLE = "Available"
CONTAINER_RENTED = "Rented"
CONTAINER_DAMAGED = "Damaged"
CONTAINER_MAINTENANCE = "Maintenance"
CONTAINER_OVERDUE = "Overdue"
CONTAINER_WITHDRAWN = "Withdrawn"

# Container Order.status
ORDER_NEW = "New"
ORDER_AWAITING_TRANSFER = "Awaiting Transfer"
ORDER_AWAITING_DRIVER = "Awaiting Driver"
ORDER_ASSIGNED = "Assigned"
ORDER_DELIVERED = "Delivered"
ORDER_CANCELLED = "Cancelled"

# Rental Record.status
RENTAL_RENTED = "Rented"
RENTAL_OVERDUE = "Overdue"
RENTAL_UNLOADED = "Unloaded"
RENTAL_WITHDRAWN = "Withdrawn"

# Container Unload Request.status
REQUEST_AWAITING_DRIVER = "Awaiting Driver Confirmation"
REQUEST_AWAITING_REASSIGN = "Awaiting Reassignment"
REQUEST_CONFIRMED = "Confirmed"
REQUEST_CANCELLED = "Cancelled"

# Driver Commission Entry.payout_status
PAYOUT_DUE = "Due"
PAYOUT_PAID = "Paid Out"

# Contract Monthly Invoice.payment_status
INVOICE_UNPAID = "Unpaid"
INVOICE_PARTLY_PAID = "Partly Paid"
INVOICE_PAID = "Paid"

# Values replaced on existing rows (old Arabic → new English), per doctype/field
LEGACY_VALUE_MAP = {
	("Container", "status"): {
		"متاحة": CONTAINER_AVAILABLE,
		"مؤجرة": CONTAINER_RENTED,
		"تالفة": CONTAINER_DAMAGED,
		"صيانة": CONTAINER_MAINTENANCE,
		"متأخرة": CONTAINER_OVERDUE,
		"مسحوبة": CONTAINER_WITHDRAWN,
	},
	("Container Order", "status"): {
		"جديد": ORDER_NEW,
		"بانتظار تأكيد الحوالة": ORDER_AWAITING_TRANSFER,
		"بانتظار تحديد سائق": ORDER_AWAITING_DRIVER,
		"مُسنَد لسائق": ORDER_ASSIGNED,
		"تم التوصيل": ORDER_DELIVERED,
		"ملغي": ORDER_CANCELLED,
	},
	("Rental Record", "status"): {
		"مؤجرة": RENTAL_RENTED,
		"متأخرة": RENTAL_OVERDUE,
		"تم التفريغ": RENTAL_UNLOADED,
		"مسحوبة": RENTAL_WITHDRAWN,
	},
	("Container Unload Request", "status"): {
		"بانتظار تأكيد السائق": REQUEST_AWAITING_DRIVER,
		"بانتظار إسناد سائق": REQUEST_AWAITING_REASSIGN,
		"مؤكد": REQUEST_CONFIRMED,
		"ملغي": REQUEST_CANCELLED,
	},
	("Driver Commission Entry", "payout_status"): {
		"مستحقة": PAYOUT_DUE,
		"مصروفة": PAYOUT_PAID,
	},
	("Contract Monthly Invoice", "payment_status"): {
		"غير مسددة": INVOICE_UNPAID,
		"مسددة جزئيًا": INVOICE_PARTLY_PAID,
		"مسددة": INVOICE_PAID,
	},
	("Container Rental", "rental_type"): {
		"نقدي": "Cash",
		"أجل قصير": "Short Credit",
	},
	("Customer", "cr_account_type"): {
		"نقدي": "Cash",
		"آجل": "Credit",
	},
	("Truck", "vehicle_type"): {
		"قلاب": "Tipper",
		"شاحنة رفع حاويات": "Container Lifter",
		"ونش": "Crane",
		"أخرى": "Other",
	},
	("Truck Maintenance Log", "maintenance_type"): {
		"تغيير زيت": "Oil Change",
		"إطارات": "Tyres",
		"فرامل": "Brakes",
		"بطارية": "Battery",
		"صيانة دورية": "Periodic Service",
		"إصلاح عطل": "Repair",
		"أخرى": "Other",
	},
}
