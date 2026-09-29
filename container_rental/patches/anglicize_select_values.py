"""Stored Select values moved from Arabic to English so every status follows
the user's interface language (translations/ar.csv renders them in Arabic).
Converts the rows created with the old Arabic values — order type, statuses,
payout/payment status, account type, vehicle and maintenance types — plus the
saved filters that referenced them. Idempotent."""

import json

import frappe

from container_rental.container_rental.constants import LEGACY_VALUE_MAP

# Values converted before this patch grew to cover every Select field
EARLIER_MAP = {
	("Container Order", "order_type"): {
		"دفع عند الاستلام": "Cash",
		"أجل طويل المدى": "Long Credit",
		"أجل قصير المدى": "Short Credit",
	},
	("Container Contract", "contract_status"): {
		"ساري": "Active",
		"منتهٍ": "Expire",
		"active": "Active",  # lowercase default that briefly shipped
	},
	("Container Unload", "unload_reason"): {
		"طلب من العميل": "Customer Request",
		"انتهاء المدة المحددة": "Specified Period Expired",
	},
}


def execute():
	value_map = dict(EARLIER_MAP)
	value_map.update(LEGACY_VALUE_MAP)

	for (doctype, field), mapping in value_map.items():
		table = f"tab{doctype}"
		if not frappe.db.table_exists(doctype):
			continue
		if not frappe.db.has_column(doctype, field):
			continue
		for old, new in mapping.items():
			frappe.db.sql(
				f"UPDATE `{table}` SET `{field}` = %s WHERE `{field}` = %s",
				(new, old),
			)

	_convert_saved_filters(value_map)
	frappe.db.commit()


def _convert_saved_filters(value_map):
	"""Workspace shortcuts and user list-view settings store filter values as
	JSON text — rewrite the ones pointing at the old Arabic statuses."""
	flat = {}
	for (doctype, field), mapping in value_map.items():
		flat.setdefault(field, {}).update(mapping)

	for name, stats_filter, link_to in frappe.db.sql(
		"""SELECT name, stats_filter, link_to FROM `tabWorkspace Shortcut`
		   WHERE stats_filter IS NOT NULL AND stats_filter != ''"""
	):
		try:
			parsed = json.loads(stats_filter)
		except ValueError:
			continue
		changed = False
		if isinstance(parsed, dict):
			for field, value in list(parsed.items()):
				mapping = flat.get(field) or {}
				if isinstance(value, str) and value in mapping:
					parsed[field] = mapping[value]
					changed = True
		elif isinstance(parsed, list):
			# List form: [[doctype, fieldname, operator, value], ...]
			for row in parsed:
				if not isinstance(row, list) or len(row) < 4:
					continue
				mapping = flat.get(row[-3]) or {}
				if isinstance(row[-1], str) and row[-1] in mapping:
					row[-1] = mapping[row[-1]]
					changed = True
		if changed:
			frappe.db.set_value(
				"Workspace Shortcut", name, "stats_filter", json.dumps(parsed), update_modified=False
			)
