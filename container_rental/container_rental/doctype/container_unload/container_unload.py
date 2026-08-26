import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

from container_rental.container_rental import customer_utils, whatsapp
from container_rental.container_rental.doctype.rental_record.rental_record import get_open_record


class ContainerUnload(Document):
	def validate(self):
		info = frappe.db.get_value("Container", self.container, "status")
		if info not in ("مؤجرة", "متأخرة"):
			frappe.throw(_("الحاوية {0} ليست مؤجرة أو متأخرة (حالتها: {1})").format(self.container, info))
		self.rental_record = get_open_record(self.container)
		if not self.rental_record:
			frappe.throw(_("لا يوجد سجل تأجير مفتوح للحاوية {0}").format(self.container))

	def on_submit(self):
		# Document rule (S5): container becomes available, rental closes,
		# contract trip was already decremented at delivery time.
		unloaded_on = get_datetime(f"{self.unload_date} {now_datetime().time()}")
		container = frappe.get_doc("Container", self.container)
		container.db_set("status", "متاحة")
		container.db_set("last_unload_datetime", unloaded_on)

		record = frappe.get_doc("Rental Record", self.rental_record)
		record.db_set("status", "تم التفريغ")
		record.db_set("unloaded_on", unloaded_on)

		customer_utils.refresh_balance(record.client)

		if self.send_whatsapp_confirmation and record.client:
			client_name = frappe.db.get_value("Customer", record.client, "customer_name")
			whatsapp.send_event(
				"unload_reminder",
				record.mobile_no,
				{
					"client_name": client_name,
					"container_no": self.container,
					"container_size": record.container_size,
					"due_date": frappe.format(record.due_on, {"fieldtype": "Datetime"}) if record.due_on else "",
					"address": record.address or "",
					"unload_date": frappe.format(self.unload_date, {"fieldtype": "Date"}),
					"confirmation": 1,
				},
				reference_doc=record,
			)

	def on_cancel(self):
		record = frappe.get_doc("Rental Record", self.rental_record)
		record.db_set("status", "مؤجرة")
		record.db_set("unloaded_on", None)
		frappe.db.set_value("Container", self.container, "status", "مؤجرة")
