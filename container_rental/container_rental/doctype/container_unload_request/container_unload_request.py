"""Driver-first unload flow, mirroring the order flow: the request goes by
WhatsApp to the driver who delivered the container; he opens the link and
either confirms (the unload is recorded and the request closes) or declines,
which alerts the size's supervisor to assign another driver. A "Replace"
request additionally duplicates the original order on confirmation, so a
fresh container is dispatched to the same client."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_url, now_datetime, today

from container_rental.container_rental import hr_utils, whatsapp

STATUS_WAITING_DRIVER = "بانتظار تأكيد السائق"
STATUS_NEEDS_REASSIGN = "بانتظار إسناد سائق"
STATUS_CONFIRMED = "مؤكد"
STATUS_CANCELLED = "ملغي"

ACTIVE_STATUSES = (STATUS_WAITING_DRIVER, STATUS_NEEDS_REASSIGN)


def _require_roles(*roles):
	if not set(frappe.get_roles()) & set(roles + ("System Manager",)):
		frappe.throw(_("هذا الإجراء يتطلب أحد الأدوار: {0}").format("، ".join(roles)), frappe.PermissionError)


class ContainerUnloadRequest(Document):
	def validate(self):
		self.pull_rental_context()
		if not self.status:
			self.status = STATUS_WAITING_DRIVER

	def pull_rental_context(self):
		record = frappe.get_doc("Rental Record", self.rental_record)
		if record.status not in ("مؤجرة", "متأخرة"):
			frappe.throw(_("سجل التأجير {0} ليس مفتوحًا (حالته: {1})").format(record.name, record.status))
		self.container = record.container
		self.container_size = record.container_size
		self.client = record.client
		self.client_name = frappe.db.get_value("Customer", record.client, "customer_name")
		self.mobile_no = record.mobile_no
		self.address = record.address
		from container_rental.container_rental.doctype.rental_record.rental_record import get_maps_link
		self.google_maps_link = get_maps_link(record)
		if not self.assigned_driver:
			# The driver who delivered this container gets the request first
			self.assigned_driver = record.driver

	def after_insert(self):
		if self.assigned_driver:
			self.notify_driver()
		else:
			# No known delivering driver — go straight to the supervisor
			self.db_set("status", STATUS_NEEDS_REASSIGN)
			self.notify_supervisor()

	def get_whatsapp_context(self):
		return {
			"request_no": self.name,
			"request_link": get_url(f"/app/container-unload-request/{self.name}"),
			"container_no": self.container,
			"container_size": self.container_size,
			"client_name": self.client_name or self.client,
			"client_mobile": self.mobile_no or "",
			"mobile_no": self.mobile_no or "",
			"address": self.address or "",
			"google_maps_link": self.google_maps_link or "",
			"map_link": self.google_maps_link or "",
			"replacement": 1 if self.request_type == "Replace" else 0,
			"driver_name": hr_utils.get_employee_name(self.assigned_driver) if self.assigned_driver else "",
		}

	def notify_driver(self):
		context = self.get_whatsapp_context()
		whatsapp.send_event(
			"unload_driver_request",
			hr_utils.get_employee_mobile(self.assigned_driver),
			context,
			reference_doc=self,
		)
		driver_user = frappe.db.get_value("Employee", self.assigned_driver, "user_id")
		if driver_user:
			self._notification(driver_user, _("طلب تفريغ الحاوية {0} لدى {1}").format(
				self.container, context["client_name"]))

	def notify_supervisor(self, declined_by=None):
		supervisor_user, _name, supervisor_mobile = hr_utils.get_supervisor_contact(self.container_size)
		context = self.get_whatsapp_context()
		context["driver_name"] = hr_utils.get_employee_name(declined_by) if declined_by else ""
		whatsapp.send_event("unload_reassign_request", supervisor_mobile, context, reference_doc=self)
		if supervisor_user:
			self._notification(supervisor_user, _("طلب التفريغ {0} بحاجة لإسناد سائق — الحاوية {1}").format(
				self.name, self.container))

	def _notification(self, user, subject):
		frappe.get_doc({
			"doctype": "Notification Log",
			"for_user": user,
			"subject": subject,
			"email_content": _("العنوان: {0}").format(self.address or "-"),
			"document_type": self.doctype,
			"document_name": self.name,
			"type": "Alert",
		}).insert(ignore_permissions=True)

	def _check_assigned_driver_identity(self):
		roles = set(frappe.get_roles())
		if roles & {"System Manager", "Container Manager", "Driver Supervisor"}:
			return
		driver_user = frappe.db.get_value("Employee", self.assigned_driver, "user_id")
		if not driver_user or driver_user != frappe.session.user:
			frappe.throw(_("هذا الطلب مُسنَد لسائق آخر"), frappe.PermissionError)

	@frappe.whitelist()
	def driver_confirm(self):
		"""The driver removed the container: record the unload and close the
		request. A Replace request also re-orders a container for the client."""
		if self.status != STATUS_WAITING_DRIVER:
			frappe.throw(_("الطلب ليس بانتظار تأكيد السائق (حالته: {0})").format(self.status))
		self._check_assigned_driver_identity()

		unload = frappe.get_doc({
			"doctype": "Container Unload",
			"container": self.container,
			"unload_date": today(),
			"unload_reason": "Specified Period Expired" if self.source == "Period Expired" else "Customer Request",
			"driver": self.assigned_driver,
			"send_whatsapp_confirmation": 1,
			"notes": _("تأكيد السائق عبر طلب التفريغ {0}").format(self.name),
		})
		unload.flags.ignore_permissions = True
		unload.insert()
		unload.submit()
		self.db_set("unload_reference", unload.name)

		if self.request_type == "Replace":
			self.db_set("new_order", self._create_replacement_order())

		self.db_set("status", STATUS_CONFIRMED)
		self.add_comment("Info", _("أكد السائق {0} التفريغ — التوثيق: {1}").format(
			hr_utils.get_employee_name(self.assigned_driver) or "", unload.name))
		return {"unload": unload.name, "new_order": self.new_order}

	def _create_replacement_order(self):
		"""Duplicate the original order for the same client (fresh container,
		normal flow: the supervisor is notified to assign a driver)."""
		record = frappe.get_doc("Rental Record", self.rental_record)
		source = {}
		if record.source_doctype == "Container Order" and record.source_name:
			source = frappe.db.get_value(
				"Container Order", record.source_name,
				["order_type", "payment_method", "rental_value", "rental_days",
				 "delivery_address", "google_maps_link", "mobile_no"],
				as_dict=True,
			) or {}
		order = frappe.get_doc({
			"doctype": "Container Order",
			"client": record.client,
			"order_type": source.get("order_type") or "Cash",
			"container_size": record.container_size,
			"rental_days": source.get("rental_days") or None,
			"rental_value": source.get("rental_value") or record.rental_value,
			"payment_method": source.get("payment_method") or record.payment_method,
			"rental_start_date": today(),
			"delivery_address": source.get("delivery_address") or record.address,
			"google_maps_link": source.get("google_maps_link") or self.google_maps_link,
			"mobile_no": source.get("mobile_no") or record.mobile_no,
		})
		order.flags.ignore_permissions = True
		order.insert()
		order.add_comment("Info", _("طلب استبدال للحاوية {0} — عبر طلب التفريغ {1}").format(
			self.container, self.name))
		return order.name

	@frappe.whitelist()
	def driver_decline(self):
		"""The assigned driver cannot do the unload — hand it to the supervisor."""
		if self.status != STATUS_WAITING_DRIVER:
			frappe.throw(_("الطلب ليس بانتظار تأكيد السائق (حالته: {0})").format(self.status))
		self._check_assigned_driver_identity()
		declined_by = self.assigned_driver
		self.db_set("status", STATUS_NEEDS_REASSIGN)
		self.add_comment("Info", _("اعتذر السائق {0} عن التنفيذ").format(
			hr_utils.get_employee_name(declined_by) or declined_by))
		self.notify_supervisor(declined_by=declined_by)
		return STATUS_NEEDS_REASSIGN

	@frappe.whitelist()
	def assign_driver(self, driver):
		"""Supervisor (or office) sends the request to another driver."""
		_require_roles("Driver Supervisor", "Customer Service", "Container Manager")
		hr_utils.ensure_driver(driver)
		if self.status not in ACTIVE_STATUSES:
			frappe.throw(_("لا يمكن الإسناد — حالة الطلب: {0}").format(self.status))
		self.db_set("assigned_driver", driver)
		self.db_set("status", STATUS_WAITING_DRIVER)
		self.add_comment("Info", _("أُسند طلب التفريغ إلى السائق {0}").format(
			hr_utils.get_employee_name(driver) or driver))
		self.notify_driver()
		return STATUS_WAITING_DRIVER

	@frappe.whitelist()
	def cancel_request(self):
		_require_roles("Driver Supervisor", "Customer Service", "Container Manager")
		if self.status not in ACTIVE_STATUSES:
			frappe.throw(_("لا يمكن إلغاء الطلب — حالته: {0}").format(self.status))
		self.db_set("status", STATUS_CANCELLED)
		self.add_comment("Info", _("أُلغي طلب التفريغ بواسطة {0}").format(frappe.session.user))
		return STATUS_CANCELLED


def get_active_request(rental_record):
	"""Active (non-cancelled) unload request for a rental record, if any."""
	return frappe.db.get_value(
		"Container Unload Request",
		{"rental_record": rental_record, "status": ("in", ACTIVE_STATUSES + (STATUS_CONFIRMED,))},
	)


def create_unload_request(rental_record, request_type="Unload", source="Customer Request"):
	"""Create (or return the already-active) driver-first unload request."""
	existing = frappe.db.get_value(
		"Container Unload Request",
		{"rental_record": rental_record, "status": ("in", ACTIVE_STATUSES)},
	)
	if existing:
		return frappe.get_doc("Container Unload Request", existing)
	request = frappe.get_doc({
		"doctype": "Container Unload Request",
		"rental_record": rental_record,
		"request_type": request_type,
		"source": source,
	})
	request.flags.ignore_permissions = True
	request.insert()
	return request
