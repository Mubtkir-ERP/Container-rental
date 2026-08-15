import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, today


class ContainerContract(Document):
	def validate(self):
		self.compute_items()
		self.compute_trips()
		self.compute_payments()
		self.set_contract_status()

	def compute_items(self):
		for item in self.items:
			item.total = flt(item.trips_count) * flt(item.price)
		self.contract_value = sum(flt(i.total) for i in self.items)

	def compute_trips(self):
		self.total_trips = sum(int(i.trips_count or 0) for i in self.items)
		self.consumed_trips = int(self.consumed_trips or 0)
		self.remaining_trips = self.total_trips - self.consumed_trips

	def compute_payments(self):
		self.paid_amount = sum(flt(p.amount) for p in (self.payments or []))
		self.tax_on_paid = sum(flt(p.tax_amount) for p in (self.payments or []))
		self.outstanding = flt(self.contract_value) - flt(self.paid_amount)

	def set_contract_status(self):
		if self.end_date and getdate(self.end_date) < getdate(today()):
			self.contract_status = "منتهٍ"
		else:
			self.contract_status = "ساري"

	def on_update_after_submit(self):
		# Payments table is editable after submit; keep totals + client balance fresh
		self.compute_payments()
		self.db_set("paid_amount", self.paid_amount)
		self.db_set("tax_on_paid", self.tax_on_paid)
		self.db_set("outstanding", self.outstanding)
		from container_rental.container_rental import customer_utils
		customer_utils.refresh_balance(self.client)

	def on_submit(self):
		from container_rental.container_rental import customer_utils
		customer_utils.refresh_balance(self.client)

	def on_cancel(self):
		if self.consumed_trips:
			frappe.throw(_("لا يمكن إلغاء عقد نُفذت عليه رحلات ({0} رحلة)").format(self.consumed_trips))
		from container_rental.container_rental import customer_utils
		customer_utils.refresh_balance(self.client)

	def register_delivery(self, container):
		"""Called by Container Delivery.on_submit for contract-based deliveries."""
		if self.remaining_trips <= 0:
			frappe.msgprint(
				_("تنبيه: العقد {0} استنفد رحلاته المتعاقد عليها — التوصيل سيُسجل كرحلة إضافية").format(self.name)
			)
		self.db_set("consumed_trips", int(self.consumed_trips or 0) + 1)
		self.db_set("remaining_trips", int(self.total_trips or 0) - self.consumed_trips)
		self.db_set("last_container", container)

	def unregister_delivery(self):
		"""Reverse a cancelled contract delivery."""
		self.db_set("consumed_trips", max(0, int(self.consumed_trips or 0) - 1))
		self.db_set("remaining_trips", int(self.total_trips or 0) - self.consumed_trips)

	@frappe.whitelist()
	def renew_contract(self, new_end_date):
		"""S10 row action 'تجديد التعاقد' — extend the contract period."""
		if not set(frappe.get_roles()) & {"Container Manager", "System Manager"}:
			frappe.throw(_("تجديد التعاقد يتطلب صلاحية مدير الحاويات"), frappe.PermissionError)
		if getdate(new_end_date) <= getdate(self.end_date):
			frappe.throw(_("تاريخ التجديد يجب أن يكون بعد تاريخ الانتهاء الحالي"))
		old_end = self.end_date
		self.db_set("end_date", getdate(new_end_date))
		self.db_set("contract_status", "ساري" if getdate(new_end_date) >= getdate(today()) else "منتهٍ")
		self.db_set("expiry_alert_sent_on", None, update_modified=False)
		self.add_comment("Info", _("تجديد التعاقد: تمديد النهاية من {0} إلى {1}").format(old_end, new_end_date))
		return self.end_date
