import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, get_datetime, now_datetime

from container_rental.container_rental import customer_utils, whatsapp
from container_rental.container_rental.doctype.driver_commission_entry.driver_commission_entry import (
	create_commission_entry,
)
from container_rental.container_rental.doctype.rental_record.rental_record import create_rental_record


class ContainerRental(Document):
	def validate(self):
		# Quick entry shows only (size, container, driver) — fill the rest here
		if not self.rental_type:
			self.rental_type = "Cash"
		if not self.payment_method:
			self.payment_method = "نقدي"
		if not self.period_from:
			self.period_from = now_datetime()
		if not self.period_to:
			days = frappe.db.get_single_value("Container Rental Settings", "default_rental_days") or 10
			self.period_to = add_days(get_datetime(self.period_from), int(days))
		self.validate_container()
		if self.driver:
			from container_rental.container_rental import hr_utils
			hr_utils.ensure_driver(self.driver)

	def before_submit(self):
		# Deferred mandatory checks so the 3-field quick entry can save a draft
		if not self.client:
			frappe.throw(_("Client is required before submitting the rental"))
		if self.payment_method == "نقدي" and not self.cash_box:
			frappe.throw(_("Cash Account is required for cash payment"))

	def validate_container(self):
		info = frappe.db.get_value("Container", self.container, ["size", "status"], as_dict=True)
		if info.size != self.container_size:
			frappe.throw(
				_("Container {0} has size {1} which does not match requested size {2}").format(
					self.container, info.size, self.container_size
				)
			)
		if info.status != "Available":
			frappe.throw(_("Container {0} is not available (status: {1})").format(self.container, info.status))

	def on_submit(self):
		# Container goes out immediately (walk-in rental, no order workflow)
		container = frappe.get_doc("Container", self.container)
		container.db_set("status", "Rented")
		container.db_set("last_delivery_datetime", self.period_from)

		create_rental_record(
			container=self.container,
			client=self.client,
			delivered_on=self.period_from,
			due_on=self.period_to,
			source_doctype="Container Rental",
			source_name=self.name,
			driver=self.driver,
			address=self.address,
			rental_value=self.amount,
			payment_method=self.payment_method,
		)

		if self.driver:
			create_commission_entry(self.driver, "Container Rental", self.name, self.container, self.client,
				base_amount=self.amount, container_size=self.container_size)

		customer_utils.refresh_balance(self.client)

		client_name, mobile_no = customer_utils.get_name_and_mobile(self.client)
		whatsapp.send_event(
			"order_confirmation",
			mobile_no,
			{
				"order_no": self.name,
				"client_name": client_name,
				"container_no": self.container,
				"container_size": self.container_size,
				"address": self.address or "",
				"rental_days": "",
				"rental_value": self.amount or 0,
				"delivery_date": frappe.format(self.period_from, {"fieldtype": "Datetime"}),
				"delivery_time": "",
			},
			reference_doc=self,
		)

	def on_cancel(self):
		record_name = frappe.db.get_value(
			"Rental Record", {"source_doctype": "Container Rental", "source_name": self.name}
		)
		if record_name:
			record = frappe.get_doc("Rental Record", record_name)
			if record.status not in ("Rented", "Overdue"):
				frappe.throw(_("Cannot cancel a rental whose container has been unloaded or withdrawn"))
			record.flags.ignore_permissions = True
			record.delete()

		frappe.db.set_value("Container", self.container, "status", "Available")

		for entry in frappe.get_all(
			"Driver Commission Entry",
			filters={"delivery_reference_doctype": "Container Rental", "delivery_reference": self.name},
			pluck="name",
		):
			frappe.delete_doc("Driver Commission Entry", entry, force=True, ignore_permissions=True)

		customer_utils.refresh_balance(self.client)
