import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class Truck(Document):
	def validate(self):
		self.validate_driver()
		self.sync_next_oil_change()

	def validate_driver(self):
		if self.driver:
			position = frappe.db.get_value("CR Employee", self.driver, "position")
			if position != "سائق":
				frappe.throw(_("السائق المرتبط يجب أن يكون موظفًا بوظيفة سائق"))

	def sync_next_oil_change(self):
		"""Latest oil-change row drives the truck's next oil change date/km."""
		oil_rows = [
			r for r in (self.maintenance_log or [])
			if r.maintenance_type == "تغيير زيت" and (r.next_maintenance_date or r.next_maintenance_km)
		]
		if not oil_rows:
			return
		latest = max(oil_rows, key=lambda r: getdate(r.maintenance_date))
		if latest.next_maintenance_date:
			self.next_oil_change_date = latest.next_maintenance_date
		if latest.next_maintenance_km:
			self.next_oil_change_km = latest.next_maintenance_km
