import frappe
from frappe.model.document import Document
from frappe.utils import getdate


class Truck(Document):
	def validate(self):
		if self.driver:
			from container_rental.container_rental import hr_utils

			hr_utils.ensure_driver(self.driver)

	def get_latest_oil_change(self):
		"""Latest row of the oil-change child table (drives the delay alerts)."""
		rows = sorted(
			self.oil_changes or [], key=lambda r: getdate(r.change_date), reverse=True
		)
		return rows[0] if rows else None
