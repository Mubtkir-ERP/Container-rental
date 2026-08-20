import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, get_datetime

from container_rental.container_rental.doctype.driver_commission_entry.driver_commission_entry import (
	create_commission_entry,
)
from container_rental.container_rental.doctype.rental_record.rental_record import create_rental_record


class ContainerDelivery(Document):
	def validate(self):
		self.resolve_source()
		self.validate_container()
		self.compute_due()
		from container_rental.container_rental import hr_utils
		hr_utils.ensure_driver(self.driver)

	def resolve_source(self):
		if self.order:
			order = frappe.get_doc("Container Order", self.order)
			if order.status != "مُسنَد لسائق":
				frappe.throw(_("الطلب {0} ليس في حالة مُسنَد لسائق (حالته: {1})").format(order.name, order.status))
			self.client = order.client
			self.address = self.address or order.delivery_address
			self.contract = self.contract or order.contract
			if not self.agreed_days:
				self.agreed_days = order.rental_days
			if not self.driver:
				self.driver = order.assigned_driver
			if not self.vehicle:
				self.vehicle = order.assigned_vehicle
		if self.contract and not self.agreed_days:
			self.agreed_days = frappe.db.get_value("Container Contract", self.contract, "trip_duration_days")
		if self.contract and not self.order:
			contract_client = frappe.db.get_value("Container Contract", self.contract, "client")
			if self.client and self.client != contract_client:
				frappe.throw(_("العميل لا يطابق عميل العقد {0}").format(self.contract))
			self.client = contract_client

	def validate_container(self):
		info = frappe.db.get_value("Container", self.container, ["size", "status"], as_dict=True)
		if info.status != "متاحة":
			frappe.throw(_("الحاوية {0} غير متاحة (حالتها: {1})").format(self.container, info.status))
		if self.order:
			order = frappe.get_doc("Container Order", self.order)
			allowed = [c for _f, _s, c in order._container_rows() if c]
			sizes = {c: s for _f, s, c in order._container_rows() if c}
			if allowed and self.container not in allowed:
				if info.size not in {s for _f, s, _c in order._container_rows()}:
					frappe.throw(_("الحاوية {0} ليست ضمن حاويات الطلب ولا تطابق أحجامه").format(self.container))
			elif self.container in sizes and info.size != sizes[self.container]:
				frappe.throw(_("حجم الحاوية لا يطابق حجم الطلب"))

	def compute_due(self):
		if self.delivery_datetime and self.agreed_days:
			self.due_datetime = add_days(get_datetime(self.delivery_datetime), int(self.agreed_days))
		else:
			self.due_datetime = None

	def on_submit(self):
		if not self.due_datetime and self.agreed_days:
			self.compute_due()

		container = frappe.get_doc("Container", self.container)
		container.db_set("status", "مؤجرة")
		container.db_set("last_delivery_datetime", self.delivery_datetime)

		rental_value = 0
		payment_method = None
		if self.order:
			rental_value, payment_method = frappe.db.get_value(
				"Container Order", self.order, ["rental_value", "payment_method"]
			)

		create_rental_record(
			container=self.container,
			client=self.client,
			delivered_on=self.delivery_datetime,
			due_on=self.due_datetime,
			source_doctype="Container Order" if self.order else "Container Contract",
			source_name=self.order or self.contract,
			driver=self.driver,
			contract=self.contract,
			address=self.address,
			rental_value=rental_value,
			payment_method=payment_method,
		)

		# Section 6: commission frozen at the driver's current per-delivery rate
		create_commission_entry(self.driver, "Container Delivery", self.name, self.container, self.client)

		if self.contract:
			frappe.get_doc("Container Contract", self.contract).register_delivery(self.container)

		if self.order:
			frappe.get_doc("Container Order", self.order).mark_delivered_if_complete()

	def on_cancel(self):
		record_name = frappe.db.get_value(
			"Rental Record", {"container": self.container, "source_name": self.order or self.contract},
			order_by="delivered_on desc",
		)
		if record_name:
			record = frappe.get_doc("Rental Record", record_name)
			if record.status not in ("مؤجرة", "متأخرة"):
				frappe.throw(_("لا يمكن إلغاء توصيل حاوية تم تفريغها/سحبها"))
			record.flags.ignore_permissions = True
			record.delete()

		frappe.db.set_value("Container", self.container, "status", "متاحة")

		for entry in frappe.get_all(
			"Driver Commission Entry",
			filters={"delivery_reference_doctype": "Container Delivery", "delivery_reference": self.name},
			pluck="name",
		):
			frappe.delete_doc("Driver Commission Entry", entry, force=True, ignore_permissions=True)

		if self.contract:
			frappe.get_doc("Container Contract", self.contract).unregister_delivery()

		if self.order:
			order = frappe.get_doc("Container Order", self.order)
			if order.status == "تم التوصيل":
				order.db_set("status", "مُسنَد لسائق")
