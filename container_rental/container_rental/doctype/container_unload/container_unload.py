import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

from container_rental.container_rental import customer_utils, whatsapp
from container_rental.container_rental.doctype.rental_record.rental_record import get_open_record


class ContainerUnload(Document):
	def validate(self):
		info = frappe.db.get_value("Container", self.container, "status")
		if info not in ("Rented", "Overdue"):
			frappe.throw(_("الحاوية {0} ليست مؤجرة أو متأخرة (حالتها: {1})").format(self.container, info))
		self.rental_record = get_open_record(self.container)
		if not self.rental_record:
			frappe.throw(_("لا يوجد سجل تأجير مفتوح للحاوية {0}").format(self.container))
		if not self.driver:
			# Default to the driver who delivered this container — he is the one
			# the unload request goes to, and the list view shows his name
			self.driver = frappe.db.get_value("Rental Record", self.rental_record, "driver")
		# fetch_from fills this on the form only; set it here so the list view
		# shows a name for documents created by scripts and controllers too
		self.driver_name = frappe.db.get_value("Employee", self.driver, "employee_name") if self.driver else None

	def after_insert(self):
		"""Recording an unload asks the delivering driver to do it: he gets the
		WhatsApp request and confirms from the link, which submits THIS
		document. Office staff can still submit it directly instead."""
		from container_rental.container_rental.doctype.container_unload_request.container_unload_request import (
			create_unload_request,
		)

		if self.docstatus != 0 or self.flags.skip_driver_request:
			return
		request = create_unload_request(
			self.rental_record,
			source="Period Expired" if self.unload_reason == "Specified Period Expired" else "Customer Request",
			unload_doc=self,
		)
		self.db_set("request_status", request.status)
		if request.assigned_driver and not self.driver:
			self.db_set("driver", request.assigned_driver)

	def on_submit(self):
		# Document rule (S5): container becomes available, rental closes,
		# contract trip was already decremented at delivery time.
		unloaded_on = get_datetime(f"{self.unload_date} {now_datetime().time()}")
		container = frappe.get_doc("Container", self.container)
		container.db_set("status", "Available")
		container.db_set("last_unload_datetime", unloaded_on)

		record = frappe.get_doc("Rental Record", self.rental_record)
		record.db_set("status", "Unloaded")
		record.db_set("unloaded_on", unloaded_on)

		customer_utils.refresh_balance(record.client)
		self.close_driver_request()

		if self.send_whatsapp_confirmation and record.client:
			client_name = frappe.db.get_value("Customer", record.client, "customer_name")
			whatsapp.send_event(
				"unload_done",
				record.mobile_no,
				{
					"client_name": client_name,
					"container_no": self.container,
					"container_size": record.container_size,
					"unload_date": frappe.format(self.unload_date, {"fieldtype": "Date"}),
				},
				reference_doc=record,
			)

	def close_driver_request(self):
		"""Submitting the unload (by the driver's confirmation or directly by the
		office) closes the request that asked for it."""
		name = frappe.db.get_value(
			"Container Unload Request",
			{"unload_reference": self.name, "status": ("not in", ["Confirmed", "Cancelled"])},
		)
		if name:
			frappe.db.set_value("Container Unload Request", name, "status", "Confirmed", update_modified=False)
		self.db_set("request_status", "Confirmed")

	def on_cancel(self):
		record = frappe.get_doc("Rental Record", self.rental_record)
		record.db_set("status", "Rented")
		record.db_set("unloaded_on", None)
		frappe.db.set_value("Container", self.container, "status", "Rented")
