import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, getdate, today


class CREmployee(Document):
	def validate(self):
		if self.date_of_birth:
			self.age = int(date_diff(today(), getdate(self.date_of_birth)) / 365.25)
		if self.position != "سائق":
			self.driver_card_no = None
			self.driver_card_expiry = None
			self.commission_per_delivery = 0


@frappe.whitelist()
def set_status(employee, status):
	"""S7 alerts action 'تغيير الحالة'."""
	if status not in ("نشط", "غير نشط"):
		frappe.throw(_("حالة غير صحيحة"))
	doc = frappe.get_doc("CR Employee", employee)
	doc.check_permission("write")
	doc.db_set("status", status)
	return status
