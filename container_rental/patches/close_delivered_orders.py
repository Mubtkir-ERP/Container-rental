"""Close orders stuck in 'assigned' although their delivery was submitted
(before mark_delivered_if_complete learned about orders without pre-chosen
container numbers). Idempotent."""

import frappe


def execute():
	stuck = frappe.db.sql(
		"""
		SELECT DISTINCT o.name FROM `tabContainer Order` o
		JOIN `tabContainer Delivery` d ON d.`order` = o.name AND d.docstatus = 1
		WHERE o.status = 'مُسنَد لسائق'
		"""
	)
	for (name,) in stuck:
		frappe.get_doc("Container Order", name).mark_delivered_if_complete()
	frappe.db.commit()
