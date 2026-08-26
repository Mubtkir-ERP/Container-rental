import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, get_url, getdate, now_datetime

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

	def after_insert(self):
		# New flow: saving the order sends it straight to the drivers supervisor,
		# and the client gets the confirmation message.
		if self.status != STATUS_NEW:
			return  # e.g. rental-extension orders are inserted already closed
		self.db_set("status", STATUS_AWAITING_DRIVER)
		context = self.get_whatsapp_context()
		whatsapp.send_event("order_confirmation", self.mobile_no, context, reference_doc=self)
		self.notify_supervisor_new_order(context)

	def notify_supervisor_new_order(self, context=None):
		"""Drivers supervisor gets the order link the moment it is saved,
		so he can assign a driver (WhatsApp + in-system notification)."""
		supervisor_user, supervisor_name, supervisor_mobile = hr_utils.get_supervisor_contact()
		if not supervisor_user:
			return
		context = dict(context or self.get_whatsapp_context())
		context["driver_name"] = supervisor_name
		whatsapp.send_event("supervisor_new_order", supervisor_mobile, context, reference_doc=self)
		frappe.get_doc({
			"doctype": "Notification Log",
			"for_user": supervisor_user,
			"subject": _("طلب جديد {0} بانتظار إسناد سائق — {1}").format(self.name, context.get("client_name") or ""),
			"email_content": _("العنوان: {0}").format(self.delivery_address or "-"),
			"document_type": "Container Order",
			"document_name": self.name,
			"type": "Alert",
		}).insert(ignore_permissions=True)

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
		# The message is SENT FROM the WhatsApp number tied to this container
		# size (big truck / small truck instance) to the driver's own mobile.
		driver_mobile = hr_utils.get_employee_mobile(driver)
		sender_instance = frappe.db.get_value("Container Size", self.container_size, "whatsapp_instance")
		# Commission is a % of the order value, earned at assignment (not invoicing)
		from container_rental.container_rental.doctype.driver_commission_entry.driver_commission_entry import (
			create_commission_entry,
		)
		create_commission_entry(driver, "Container Order", self.name, self.container, self.client,
			base_amount=self.rental_value)
		context = self.get_whatsapp_context()
		context["driver_name"] = hr_utils.get_employee_name(driver)
		whatsapp.send_event("driver_assignment", driver_mobile, context, reference_doc=self,
			instance=sender_instance)
		return STATUS_ASSIGNED

	@frappe.whitelist()
	def cancel_order(self):
		_require_roles("Customer Service", "Container Manager")
		self._transition(
			[STATUS_NEW, STATUS_AWAITING_TRANSFER, STATUS_AWAITING_DRIVER, STATUS_ASSIGNED],
			STATUS_CANCELLED,
		)
		for entry in frappe.get_all("Driver Commission Entry",
			filters={"delivery_reference_doctype": "Container Order", "delivery_reference": self.name},
			pluck="name"):
			frappe.delete_doc("Driver Commission Entry", entry, force=True, ignore_permissions=True)
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

	@frappe.whitelist()
	def driver_confirm_delivery(self, container, delivery_note_no=None):
		"""The assigned driver confirms the drop-off from his limited view:
		he types the container number (known only on site) and, for credit
		orders, the delivery-note book number. Creates + submits the
		Container Delivery behind the scenes."""
		if self.status != STATUS_ASSIGNED:
			frappe.throw(_("الطلب ليس في حالة مُسنَد لسائق"))

		roles = set(frappe.get_roles())
		if not roles & {"System Manager", "Container Manager", "Driver Supervisor"}:
			driver_user = frappe.db.get_value("Employee", self.assigned_driver, "user_id")
			if not driver_user or driver_user != frappe.session.user:
				frappe.throw(_("هذا الطلب مُسنَد لسائق آخر"), frappe.PermissionError)

		container_name = frappe.db.get_value("Container", {"container_no": container}) or container
		info = frappe.db.get_value("Container", container_name, ["size", "status"], as_dict=True)
		if not info:
			frappe.throw(_("لا توجد حاوية بالرقم {0}").format(container))
		if info.size != self.container_size:
			frappe.throw(_("حجم الحاوية {0} هو {1} ولا يطابق حجم الطلب {2}").format(
				container, info.size, self.container_size))
		if info.status != "متاحة":
			frappe.throw(_("الحاوية {0} غير متاحة (حالتها: {1})").format(container, info.status))

		self.db_set("container", container_name)
		if delivery_note_no:
			self.db_set("delivery_note_no", delivery_note_no)

		delivery = frappe.get_doc({
			"doctype": "Container Delivery",
			"order": self.name,
			"container": container_name,
			"driver": self.assigned_driver,
			"vehicle": self.assigned_vehicle,
			"delivery_datetime": now_datetime(),
		})
		delivery.flags.ignore_permissions = True
		delivery.insert()
		delivery.submit()
		return delivery.name

	@frappe.whitelist()
	def make_sales_invoice(self):
		"""Draft Sales Invoice for a delivered order, carrying its data across
		(client, rental value, containers count, driver's sales person)."""
		_require_roles("Customer Service", "Transfer Follow-up", "Container Manager")
		if self.status != STATUS_DELIVERED:
			frappe.throw(_("إنشاء الفاتورة متاح بعد اكتمال التوصيل فقط"))

		item_code = _ensure_rental_item()
		containers_count = len([c for _f, _s, c in self._container_rows() if c]) or 1

		invoice = frappe.new_doc("Sales Invoice")
		invoice.customer = self.client
		invoice.append("items", {
			"item_code": item_code,
			"qty": containers_count,
			"rate": frappe.utils.flt(self.rental_value),
			"description": _("تأجير حاوية — الطلب {0} — الحاوية {1}").format(
				self.name, self.container or ""),
		})
		sales_person, _rate = hr_utils.get_commission_per_delivery(self.assigned_driver) if self.assigned_driver else (None, 0)
		if sales_person:
			invoice.append("sales_team", {"sales_person": sales_person, "allocated_percentage": 100})
		invoice.flags.ignore_permissions = True
		invoice.insert()
		self.add_comment("Info", _("أُنشئت فاتورة المبيعات {0}").format(invoice.name))
		return invoice.name

	def get_whatsapp_context(self):
		client_name = frappe.db.get_value("Customer", self.client, "customer_name")
		mobile = self.mobile_no or frappe.db.get_value("Customer", self.client, "mobile_no") or ""
		maps = self.google_maps_link or ""
		return {
			"order_no": self.name,
			"order_link": get_url(f"/app/container-order/{self.name}"),
			"client_name": client_name,
			# aliases so hand-edited templates keep working
			"customer_name": client_name,
			"client_mobile": mobile,
			"customer_mobile": mobile,
			"mobile_no": mobile,
			"map_link": maps,
			"location_link": maps,
			"container_no": self.container or "",
			"container_size": self.container_size,
			"address": self.delivery_address or "",
			"google_maps_link": self.google_maps_link or "",
			"payment_method": self.payment_method or "",
			"rental_days": self.rental_days or "",
			"rental_value": self.rental_value or 0,
			"delivery_date": frappe.format(self.required_delivery_date, {"fieldtype": "Date"})
			if self.required_delivery_date
			else "",
			"delivery_time": self.delivery_time or "",
		}


def _ensure_rental_item():
	"""Get or create the service item used on rental Sales Invoices."""
	item_code = "Container Rental Service"
	if frappe.db.exists("Item", item_code):
		return item_code
	item_group = "Services" if frappe.db.exists("Item Group", "Services") else "All Item Groups"
	frappe.get_doc({
		"doctype": "Item",
		"item_code": item_code,
		"item_name": item_code,
		"item_group": item_group,
		"is_stock_item": 0,
		"is_sales_item": 1,
		"stock_uom": "Nos",
	}).insert(ignore_permissions=True)
	return item_code
