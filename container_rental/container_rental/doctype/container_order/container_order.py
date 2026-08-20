import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, now_datetime

from container_rental.container_rental import hr_utils, whatsapp

SHORT_TERM = "أجل قصير المدى"
LONG_TERM = "أجل طويل المدى"
COD = "دفع عند الاستلام"

STATUS_NEW = "جديد"
STATUS_AWAITING_TRANSFER = "بانتظار تأكيد الحوالة"
STATUS_AWAITING_DRIVER = "بانتظار تحديد سائق"
STATUS_ASSIGNED = "مُسنَد لسائق"
STATUS_DELIVERED = "تم التوصيل"
STATUS_CANCELLED = "ملغي"


def _require_roles(*roles):
	if not set(frappe.get_roles()) & set(roles + ("System Manager",)):
		frappe.throw(_("هذا الإجراء يتطلب أحد الأدوار: {0}").format("، ".join(roles)), frappe.PermissionError)


class ContainerOrder(Document):
	def validate(self):
		self.set_defaults()
		self.compute_end_date()
		self.validate_rental_days()
		self.validate_containers()

	def set_defaults(self):
		if not self.status:
			# get_doc(dict) does not apply field defaults — guard for API/script creation
			self.status = STATUS_NEW
		if not self.entered_by:
			self.entered_by = frappe.session.user
		if not self.rental_days and self.order_type != LONG_TERM:
			self.rental_days = frappe.db.get_single_value("Container Rental Settings", "default_rental_days") or 10

	def compute_end_date(self):
		if self.rental_start_date and self.rental_days:
			self.rental_end_date = add_days(getdate(self.rental_start_date), int(self.rental_days))
		elif not self.rental_days:
			self.rental_end_date = None

	def validate_rental_days(self):
		# Fixed duration is mandatory for cash/transfer clients; open-ended only for long-term credit
		if self.order_type != LONG_TERM and not self.rental_days:
			frappe.throw(_("مدة التأجير مطلوبة لطلبات النقدي/التحويل والأجل قصير المدى"))

	def validate_containers(self):
		for fieldname, size, container in self._container_rows():
			if not container:
				continue
			info = frappe.db.get_value("Container", container, ["size", "status"], as_dict=True)
			if not info:
				continue
			if info.size != size:
				frappe.throw(_("الحاوية {0} حجمها {1} ولا يطابق الحجم المطلوب {2}").format(container, info.size, size))
			if self.status in (STATUS_NEW, STATUS_AWAITING_TRANSFER, STATUS_AWAITING_DRIVER) and info.status != "متاحة":
				frappe.throw(_("الحاوية {0} غير متاحة (حالتها: {1})").format(container, info.status))

	def _container_rows(self):
		"""Yield (fieldname, size, container) for the primary + additional container rows."""
		rows = [("container", self.container_size, self.container)]
		for item in self.additional_containers or []:
			rows.append(("additional_containers", item.container_size, item.container))
		return rows

	# ── Status machine (section 3 routing) ──────────────────────────────────

	def _transition(self, from_statuses, to_status):
		if self.status not in from_statuses:
			frappe.throw(
				_("لا يمكن الانتقال من الحالة الحالية ({0}) إلى {1}").format(self.status, to_status)
			)
		self.db_set("status", to_status)
		self.add_comment("Info", _("تغيير حالة الطلب إلى: {0}").format(to_status))

	@frappe.whitelist()
	def confirm_order(self):
		"""جديد → بانتظار تأكيد الحوالة (أجل قصير) أو بانتظار تحديد سائق (المسارين الآخرين)."""
		_require_roles("Customer Service", "Container Manager")
		target = STATUS_AWAITING_TRANSFER if self.order_type == SHORT_TERM else STATUS_AWAITING_DRIVER
		self._transition([STATUS_NEW], target)
		whatsapp.send_event(
			"order_confirmation",
			self.mobile_no,
			self.get_whatsapp_context(),
			reference_doc=self,
		)
		return target

	@frappe.whitelist()
	def confirm_transfer(self):
		"""Transfer follow-up confirms the bank transfer arrived (short-term orders only)."""
		_require_roles("Transfer Follow-up", "Container Manager")
		self._transition([STATUS_AWAITING_TRANSFER], STATUS_AWAITING_DRIVER)
		self.db_set("transfer_confirmed_by", frappe.session.user)
		self.db_set("transfer_confirmed_on", now_datetime())
		return STATUS_AWAITING_DRIVER

	@frappe.whitelist()
	def assign_driver(self, driver, vehicle=None):
		"""Driver supervisor assigns the delivery driver."""
		_require_roles("Driver Supervisor", "Container Manager")
		hr_utils.ensure_driver(driver)
		self._transition([STATUS_AWAITING_DRIVER], STATUS_ASSIGNED)
		self.db_set("assigned_driver", driver)
		if vehicle:
			self.db_set("assigned_vehicle", vehicle)
		driver_mobile = hr_utils.get_employee_mobile(driver)
		context = self.get_whatsapp_context()
		context["driver_name"] = hr_utils.get_employee_name(driver)
		whatsapp.send_event("driver_assignment", driver_mobile, context, reference_doc=self)
		return STATUS_ASSIGNED

	@frappe.whitelist()
	def cancel_order(self):
		_require_roles("Customer Service", "Container Manager")
		self._transition(
			[STATUS_NEW, STATUS_AWAITING_TRANSFER, STATUS_AWAITING_DRIVER, STATUS_ASSIGNED],
			STATUS_CANCELLED,
		)
		return STATUS_CANCELLED

	@frappe.whitelist()
	def mark_payment_received(self, cash_box=None):
		"""Record collection of a credit / cash-on-delivery order amount."""
		_require_roles("Customer Service", "Transfer Follow-up", "Container Manager")
		self.db_set("payment_received", 1)
		self.db_set("payment_date", getdate())
		if cash_box:
			self.db_set("cash_box", cash_box)
		from container_rental.container_rental import customer_utils
		customer_utils.refresh_balance(self.client)
		return True

	def mark_delivered_if_complete(self):
		"""Called by Container Delivery.on_submit — closes the order when all
		its container rows have a submitted delivery."""
		expected = [c for _, _, c in self._container_rows() if c]
		delivered = frappe.get_all(
			"Container Delivery",
			filters={"order": self.name, "docstatus": 1},
			pluck="container",
		)
		if expected and set(expected) <= set(delivered):
			self.db_set("status", STATUS_DELIVERED)

	def get_whatsapp_context(self):
		client_name = frappe.db.get_value("Customer", self.client, "customer_name")
		return {
			"order_no": self.name,
			"client_name": client_name,
			"container_no": self.container or "",
			"container_size": self.container_size,
			"address": self.delivery_address or "",
			"rental_days": self.rental_days or "",
			"rental_value": self.rental_value or 0,
			"delivery_date": frappe.format(self.required_delivery_date, {"fieldtype": "Date"})
			if self.required_delivery_date
			else "",
			"delivery_time": self.delivery_time or "",
		}
