import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class ContractMonthlyInvoice(Document):
	def validate(self):
		for line in self.lines:
			line.amount = flt(line.trips_delivered) * flt(line.price)
		self.total_amount = sum(flt(line.amount) for line in self.lines)
		self.validate_unique_month()
		self.sync_payment_status()

	def validate_unique_month(self):
		# Idempotency guard: one invoice per contract per month
		if self.month_key and frappe.db.exists(
			"Contract Monthly Invoice",
			{
				"contract": self.contract,
				"month_key": self.month_key,
				"docstatus": ("<", 2),
				"name": ("!=", self.name),
			},
		):
			frappe.throw(
				_("توجد فاتورة شهرية بالفعل للعقد {0} عن شهر {1}").format(self.contract, self.month_key)
			)

	def sync_payment_status(self):
		paid = flt(self.paid_amount)
		if paid <= 0:
			self.payment_status = "غير مسددة"
		elif paid < flt(self.total_amount):
			self.payment_status = "مسددة جزئيًا"
		else:
			self.payment_status = "مسددة"

	def on_update_after_submit(self):
		self.sync_payment_status()
		self.db_set("payment_status", self.payment_status)
