"""The team switched stored Select values to English (order type, contract
status, unload reason) — see the option lists in the doctype JSONs. Convert
the rows created with the old Arabic values so filters, depends_on and the
Python status logic keep matching. Idempotent."""

import frappe

VALUE_MAP = [
	("Container Order", "order_type", {
		"دفع عند الاستلام": "Cash",
		"أجل طويل المدى": "Long Credit",
		"أجل قصير المدى": "Short Credit",
	}),
	("Container Contract", "contract_status", {
		"ساري": "Active",
		"منتهٍ": "Expire",
		"active": "Active",  # lowercase default that briefly shipped
	}),
	("Container Unload", "unload_reason", {
		"طلب من العميل": "Customer Request",
		"انتهاء المدة المحددة": "Specified Period Expired",
	}),
]


def execute():
	for doctype, field, mapping in VALUE_MAP:
		if not frappe.db.table_exists(doctype):
			continue
		for old, new in mapping.items():
			frappe.db.sql(
				f"UPDATE `tab{doctype}` SET `{field}` = %s WHERE `{field}` = %s",
				(new, old),
			)
	frappe.db.commit()
