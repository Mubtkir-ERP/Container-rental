"""WhatsApp notification adapter (document section 5) over the frappe_whatsapp app.

No custom doctypes here: editable message bodies live in frappe_whatsapp's
"WhatsApp Templates" (one row per event key, Arabic Jinja body in the
`template` field), sending goes through "WhatsApp Message" (its before_insert
posts to the Meta Cloud API), and the audit trail is the WhatsApp Message list.

send_event() never raises — when WhatsApp Settings is not configured the send
is skipped quietly, so business transactions are never blocked by
notification problems.
"""

import frappe
from frappe.utils import now_datetime

# Event key → default Arabic body (created in WhatsApp Templates by the seed
# patch; admins edit them there afterwards)
DEFAULT_TEMPLATES = {
	"order_confirmation": {
		"title": "تأكيد طلب التوصيل — للعميل",
		"body": (
			"عزيزنا {{ client_name }}،\n"
			"تم تأكيد طلبكم رقم {{ order_no }} لتوصيل حاوية {{ container_size }}"
			"{% if container_no %} (رقم {{ container_no }}){% endif %}.\n"
			"{% if delivery_date %}موعد التوصيل: {{ delivery_date }} {{ delivery_time }}.\n{% endif %}"
			"{% if address %}الموقع: {{ address }}.\n{% endif %}"
			"شكرًا لتعاملكم معنا."
		),
	},
	"driver_assignment": {
		"title": "إسناد طلب توصيل جديد — للسائق",
		"body": (
			"الأخ {{ driver_name }}،\n"
			"تم إسناد طلب توصيل جديد لك:\n"
			"رقم الطلب: {{ order_no }}\n"
			"رابط الطلب: {{ order_link }}\n"
			"حجم الحاوية: {{ container_size }}\n"
			"{% if payment_method %}طريقة الدفع: {{ payment_method }}\n{% endif %}"
			"{% if google_maps_link %}موقع التسليم: {{ google_maps_link }}\n{% endif %}"
			"{% if delivery_date %}الموعد المطلوب: {{ delivery_date }} {{ delivery_time }}{% endif %}"
		),
	},
	"unload_reminder": {
		"title": "تنبيه تفريغ الحاوية — للعميل",
		"body": (
			"عزيزنا {{ client_name }}،\n"
			"{% if confirmation %}"
			"تم تفريغ الحاوية {{ container_no }} بتاريخ {{ unload_date }} بنجاح. شكرًا لتعاملكم معنا."
			"{% else %}"
			"نذكّركم بضرورة تجهيز الحاوية {{ container_no }} للتفريغ.\n"
			"{% if due_date %}تاريخ الاستحقاق: {{ due_date }}.\n{% endif %}"
			"{% if overdue_days and overdue_days > 0 %}الحاوية متأخرة {{ overdue_days }} يوم.\n{% endif %}"
			"نرجو التواصل معنا لجدولة التفريغ."
			"{% endif %}"
		),
	},
	"monthly_invoice": {
		"title": "الفاتورة الشهرية — لعملاء العقود",
		"body": (
			"عزيزنا {{ client_name }}،\n"
			"صدرت فاتورتكم الشهرية {{ invoice_no }} عن شهر {{ month }} للعقد {{ contract_no }}.\n"
			"عدد الرحلات المنفذة: {{ trips_count }}\n"
			"إجمالي الفاتورة: {{ total_amount }} ريال.\n"
			"نشكر لكم حسن تعاونكم."
		),
	},
	"contract_expiry": {
		"title": "تنبيه قرب انتهاء العقد — للعميل",
		"body": (
			"عزيزنا {{ client_name }}،\n"
			"نفيدكم بأن عقدكم {{ contract_no }} ينتهي بتاريخ {{ end_date }}.\n"
			"{% if trips_count %}الرحلات المتبقية: {{ trips_count }}.\n{% endif %}"
			"يسعدنا تواصلكم معنا لتجديد التعاقد."
		),
	},
	"supervisor_unload_request": {
		"title": "طلب إرسال سائق للتفريغ — لمشرف السواقين",
		"body": (
			"طلب تفريغ حاوية:\n"
			"الحاوية: {{ container_no }}\n"
			"العميل: {{ client_name }}\n"
			"العنوان: {{ address }}\n"
			"{% if google_maps_link %}الموقع على الخريطة: {{ google_maps_link }}\n{% endif %}"
			"{% if due_date %}تاريخ الاستحقاق: {{ due_date }}\n{% endif %}"
			"{% if overdue_days and overdue_days > 0 %}متأخرة {{ overdue_days }} يوم.\n{% endif %}"
			"يرجى إرسال سائق للتفريغ."
		),
	},
}

DEFAULT_COUNTRY_CODE = "966"


def is_meta_configured():
	"""True when frappe_whatsapp's Meta Cloud API credentials are filled."""
	try:
		settings = frappe.get_cached_doc("WhatsApp Settings")
	except Exception:
		return False
	token = settings.get_password("token", raise_exception=False)
	return bool(settings.url and settings.version and settings.phone_id and token)


def resolve_instance(instance=None):
	"""Sending Whatsapp Instance (Evolution API): explicit → settings default →
	any connected instance. None when the site has no instances."""
	if "frappe_whatsapp" not in frappe.get_installed_apps() or not frappe.db.table_exists("Whatsapp Instance"):
		return None
	if instance and frappe.db.exists("Whatsapp Instance", instance):
		return instance
	default = frappe.db.get_single_value("Container Rental Settings", "default_whatsapp_instance")
	if default and frappe.db.exists("Whatsapp Instance", default):
		return default
	return frappe.db.get_value("Whatsapp Instance", {"connection_status": "Connected"})


def instance_for_size(container_size):
	"""Sending instance tied to a container size (big / small truck number)."""
	if not container_size or not frappe.db.table_exists("Container Size"):
		return None
	return frappe.db.get_value("Container Size", container_size, "whatsapp_instance")


def is_configured(instance=None):
	"""A message can go out either through an Evolution instance or Meta."""
	return bool(resolve_instance(instance)) or is_meta_configured()


def render_event(template_key, context):
	"""Render the editable WhatsApp Templates body for an event key.

	Looked up by template_name (the doc name carries a language suffix).
	Falls back to the built-in bodies when frappe_whatsapp is not installed."""
	body = None
	if "frappe_whatsapp" in frappe.get_installed_apps():
		body = frappe.db.get_value("WhatsApp Templates", {"template_name": template_key}, "template")
	if not body:
		default = DEFAULT_TEMPLATES.get(template_key)
		if not default:
			return None
		body = default["body"]
	return frappe.render_template(body, context or {})


def send_event(template_key, mobile_no, context, reference_doc=None, instance=None):
	"""Render the event template and send it — through the given Evolution
	instance (e.g. the big/small truck number), the default instance, or Meta.

	Skips quietly (with an error-log entry on real failures) — never raises.
	"""
	try:
		_send_event(template_key, mobile_no, context or {}, reference_doc, instance)
	except Exception:
		frappe.log_error(title=f"WhatsApp send_event failed: {template_key}")
		frappe.clear_last_message()


def _send_event(template_key, mobile_no, context, reference_doc, instance=None):
	if "frappe_whatsapp" not in frappe.get_installed_apps():
		return
	body = render_event(template_key, context)
	if not body or not mobile_no:
		return

	# Every message related to a container goes out from the number of that
	# container's size (client, supervisor and driver alike) unless forced.
	sender = resolve_instance(instance or instance_for_size(context.get("container_size")))
	if sender:
		_send_via_evolution(sender, mobile_no, body, reference_doc)
		_stamp_rental_record(reference_doc, template_key)
		return
	if not is_meta_configured():
		return  # no provider set up yet — skip without blocking the transaction

	message = frappe.get_doc({
		"doctype": "WhatsApp Message",
		"type": "Outgoing",
		"message_type": "Manual",
		"content_type": "text",
		"to": normalize_number(mobile_no),
		"message": body,
		"reference_doctype": reference_doc.doctype if reference_doc else None,
		"reference_name": reference_doc.name if reference_doc else None,
	})
	message.flags.ignore_permissions = True
	message.insert()  # frappe_whatsapp posts to Meta in before_insert
	_stamp_rental_record(reference_doc, template_key)


def _send_via_evolution(instance, mobile_no, body, reference_doc=None):
	"""POST the text through the Evolution API of a Whatsapp Instance and log
	it as a WhatsApp Message (message_id set so frappe_whatsapp does not
	re-send it through Meta)."""
	import requests

	inst = frappe.get_doc("Whatsapp Instance", instance)
	server = frappe.get_doc("Evolution Server", inst.evolution_server)
	api_key = inst.get_password("api_key", raise_exception=False) or server.get_password("api_key", raise_exception=False)
	base_url = (server.base_url or "").rstrip("/")
	to = normalize_number(mobile_no)
	response = requests.post(
		f"{base_url}/message/sendText/{inst.instance_name}",
		headers={"Content-Type": "application/json", "apikey": api_key},
		json={"number": to, "text": body},
		timeout=30,
	)
	data = {}
	try:
		data = response.json()
	except Exception:
		pass
	if response.status_code not in (200, 201):
		frappe.throw(f"Evolution API error {response.status_code}: {response.text[:300]}")
	message_id = data.get("key", {}).get("id") or data.get("message", {}).get("key", {}).get("id") or "evolution"
	log = frappe.get_doc({
		"doctype": "WhatsApp Message",
		"type": "Outgoing",
		"message_type": "Template",  # with message_id set → stored without a Meta send
		"content_type": "text",
		"to": to,
		"message": body,
		"message_id": message_id,
		"status": "Sent",
		"reference_doctype": reference_doc.doctype if reference_doc else None,
		"reference_name": reference_doc.name if reference_doc else None,
	})
	log.flags.ignore_permissions = True
	log.insert()


def send_text(mobile_no, body, reference_doc=None, instance=None):
	"""Send a plain WhatsApp text (no template) — used for internal digests.

	Same guarantees as send_event: never raises, skips when unconfigured."""
	try:
		if "frappe_whatsapp" not in frappe.get_installed_apps():
			return
		if not mobile_no or not body:
			return
		sender = resolve_instance(instance)
		if sender:
			_send_via_evolution(sender, mobile_no, body, reference_doc)
			return
		if not is_meta_configured():
			return
		message = frappe.get_doc({
			"doctype": "WhatsApp Message",
			"type": "Outgoing",
			"message_type": "Manual",
			"content_type": "text",
			"to": normalize_number(mobile_no),
			"message": body,
			"reference_doctype": reference_doc.doctype if reference_doc else None,
			"reference_name": reference_doc.name if reference_doc else None,
		})
		message.flags.ignore_permissions = True
		message.insert()
	except Exception:
		frappe.log_error(title="WhatsApp send_text failed")
		frappe.clear_last_message()


def normalize_number(mobile_no):
	"""Local formats → full international digits (e.g. 05x → 9665x)."""
	number = "".join(ch for ch in str(mobile_no) if ch.isdigit())
	if number.startswith("00"):
		number = number[2:]
	elif number.startswith("0"):
		number = DEFAULT_COUNTRY_CODE + number[1:]
	elif not number.startswith(DEFAULT_COUNTRY_CODE):
		number = DEFAULT_COUNTRY_CODE + number
	return number


def _stamp_rental_record(reference_doc, template_key):
	"""Track the last WhatsApp message on the related Rental Record (S11 column)."""
	if not reference_doc:
		return
	record_name = None
	if reference_doc.doctype == "Rental Record":
		record_name = reference_doc.name
	elif reference_doc.doctype in ("Container Order", "Container Rental"):
		record_name = frappe.db.get_value(
			"Rental Record",
			{"source_doctype": reference_doc.doctype, "source_name": reference_doc.name},
			order_by="delivered_on desc",
		)
	if record_name:
		frappe.db.set_value(
			"Rental Record",
			record_name,
			{"last_whatsapp_message": template_key, "last_whatsapp_on": now_datetime()},
			update_modified=False,
		)
