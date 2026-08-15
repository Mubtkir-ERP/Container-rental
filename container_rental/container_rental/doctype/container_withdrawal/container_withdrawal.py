import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

from container_rental.container_rental.doctype.rental_record.rental_record import get_open_record


class ContainerWithdrawal(Document):
	"""Withdrawal = returning the container WITHOUT emptying it at the dump
	(documented interpretation of open question 6). No municipality fee and no
	contract-trip effect; the container waits as مسحوبة until inspection."""

	def validate(self):
		status = frappe.db.get_value("Container", self.container, "status")
		if status not in ("مؤجرة", "متأخرة"):
			frappe.throw(_("الحاوية {0} ليست مؤجرة أو متأخرة (حالتها: {1})").format(self.container, status))
		self.rental_record = get_open_record(self.container)
		if not self.rental_record:
			frappe.throw(_("لا يوجد سجل تأجير مفتوح للحاوية {0}").format(self.container))

	def on_submit(self):
		withdrawn_on = get_datetime(f"{self.withdrawal_date} {now_datetime().time()}")
		frappe.db.set_value("Container", self.container, "status", "مسحوبة")

		record = frappe.get_doc("Rental Record", self.rental_record)
		record.db_set("status", "مسحوبة")
		record.db_set("withdrawn_on", withdrawn_on)

	def on_cancel(self):
		record = frappe.get_doc("Rental Record", self.rental_record)
		record.db_set("status", "مؤجرة")
		record.db_set("withdrawn_on", None)
		frappe.db.set_value("Container", self.container, "status", "مؤجرة")
