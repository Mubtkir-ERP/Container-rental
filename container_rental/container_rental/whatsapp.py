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
			"اسم العميل: {{ client_name }}\n"
			"جوال العميل: {{ client_mobile }}\n"
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
	"supervisor_new_order": {
		"title": "طلب جديد بانتظار إسناد سائق — لمشرف السواقين",
		"body": (
			"طلب جديد بانتظار إسناد سائق:\n"
			"رقم الطلب: {{ order_no }}\n"
			"رابط الطلب: {{ order_link }}\n"
			"العميل: {{ client_name }} — {{ client_mobile }}\n"
			"حجم الحاوية: {{ container_size }}\n"
			"{% if address %}العنوان: {{ address }}\n{% endif %}"
			"{% if google_maps_link %}الموقع على الخريطة: {{ google_maps_link }}\n{% endif %}"
			"{% if delivery_date %}موعد التوصيل المطلوب: {{ delivery_date }} {{ delivery_time }}\n{% endif %}"
			"يرجى إسناد الطلب لسائق."
		),
	},
	"unload_driver_request": {
		"title": "طلب تفريغ حاوية — للسائق الموصّل",
		"body": (
			"الأخ {{ driver_name }}،\n"
			"{% if replacement %}طلب تفريغ واستبدال حاوية:{% else %}طلب تفريغ حاوية:{% endif %}\n"
			"رقم الحاوية: {{ container_no }}\n"
			"العميل: {{ client_name }}\n"
			"جوال العميل: {{ client_mobile }}\n"
			"{% if google_maps_link %}موقع العميل: {{ google_maps_link }}\n{% endif %}"
			"رابط طلب التفريغ: {{ request_link }}\n"
			"يرجى الدخول على الرابط والضغط على تأكيد بعد إزالة الحاوية، أو إلغاء إن تعذّر التنفيذ."
		),
	},
	"unload_reassign_request": {
		"title": "إعادة إسناد طلب تفريغ — لمشرف السواقين",
		"body": (
			"طلب التفريغ بحاجة لإسناد سائق:\n"
			"{% if driver_name %}اعتذر السائق {{ driver_name }} عن التنفيذ.\n{% endif %}"
			"رقم الحاوية: {{ container_no }}\n"
			"العميل: {{ client_name }} — {{ client_mobile }}\n"
			"{% if address %}العنوان: {{ address }}\n{% endif %}"
			"{% if google_maps_link %}الموقع على الخريطة: {{ google_maps_link }}\n{% endif %}"
			"رابط طلب التفريغ: {{ request_link }}\n"
			"يرجى إسناد سائق آخر."
		),
	},
	"unload_done": {
		"title": "تأكيد إزالة الحاوية — للعميل",
		"body": (
			"عزيزنا {{ client_name }}،\n"
			"تم إزالة الحاوية{% if container_no %} رقم {{ container_no }}{% endif %} وشكرًا لتعاملكم معنا."
		),
	},
	"supervisor_unload_request": {
		"title": "طلب إرسال سائق للتفريغ — لمشرف السواقين",
		"body": (
			"طلب تفريغ حاوية:\n"
			"الحاوية: {{ container_no }}\n"
			"العميل: {{ client_name }}\n"
			"{% if order_link %}رابط الطلب: {{ order_link }}\n{% endif %}"
			"العنوان: {{ address }}\n"
			"{% if google_maps_link %}الموقع على الخريطة: {{ google_maps_link }}\n{% endif %}"
			"{% if due_date %}تاريخ الاستحقاق: {{ due_date }}\n{% endif %}"
			"{% if overdue_days and overdue_days > 0 %}متأخرة {{ overdue_days }} يوم.\n{% endif %}"
			"يرجى إرسال سائق للتفريغ."
		),
	},
}

DEFAULT_COUNTRY_CODE = "966"


# Templates are edited by admins, who reasonably write {{ delivery_address }}
# where the code sends "address" (and the same for the client/map keys). Every
# spelling of the same value is filled in before rendering so a hand-edited
# template never comes out with a blank line.
CONTEXT_ALIASES = {
	"address": ("delivery_address", "client_address", "location", "customer_address"),
	"google_maps_link": ("map_link", "location_link", "maps_link", "google_map_link"),
	"client_name": ("customer_name",),
	"client_mobile": ("customer_mobile", "mobile_no", "client_phone"),
	"container_no": ("container", "container_number"),
	"order_link": ("order_url",),
	"order_no": ("order_number",),
	"request_link": ("request_url",),
}


def expand_aliases(context):
	"""Fill every known alias of a value the caller provided (and back-fill the
	canonical key when only an alias was given)."""
	out = dict(context or {})
	for canonical, aliases in CONTEXT_ALIASES.items():
		names = (canonical,) + aliases
		value = next((out[n] for n in names if out.get(n) not in (None, "")), None)
		if value in (None, ""):
			continue
		for name in names:
			if not out.get(name):
				out[name] = value
	return out


def is_meta_configured():
	"""True when frappe_whatsapp's Meta Cloud API credentials are filled."""
	try:
		settings = frappe.get_cached_doc("WhatsApp Settings")
	except Exception:
		return False
	token = settings.get_password("token", raise_exception=False)
	return bool(settings.url and settings.version and settings.phone_id and token)


def instances_available():
	return ("frappe_whatsapp" in frappe.get_installed_apps()
		and frappe.db.table_exists("Whatsapp Instance"))


def resolve_instance(instance=None):
	"""Sending Whatsapp Instance (Evolution API) for messages that belong to no
	particular container — contract and invoice notices. An explicit instance
	wins; otherwise the site's single instance is used. With several instances
	and no container size to choose by, nothing is sent: picking one at random
	is what made clients receive messages from the wrong number."""
	if not instances_available():
		return None
	if instance:
		# A sender someone configured must never be swapped for another number
		if frappe.db.exists("Whatsapp Instance", instance):
			return instance
		frappe.log_error(
			message=f"Configured WhatsApp Instance does not exist: {instance}",
			title="Container Rental: WhatsApp instance missing",
		)
		return None
	connected = frappe.get_all("Whatsapp Instance", filters={"connection_status": "Connected"}, pluck="name")
	if len(connected) == 1:
		return connected[0]
	return None


def instance_for_size(container_size):
	"""Sending instance tied to a container size (big / small truck number).
	Returns None when the size has no number, or names one that no longer
	exists — the caller must not silently fall back to another number."""
	if not container_size or not instances_available() or not frappe.db.table_exists("Container Size"):
		return None
	instance = frappe.db.get_value("Container Size", container_size, "whatsapp_instance")
	if instance and frappe.db.exists("Whatsapp Instance", instance):
		return instance
	if instance:
		frappe.log_error(
			message=f"Container Size {container_size} points at missing Whatsapp Instance {instance}",
			title="Container Rental: WhatsApp instance missing",
		)
	return None


def is_configured(instance=None):
	"""A message can go out either through an Evolution instance or Meta."""
	return bool(resolve_instance(instance)) or is_meta_configured()


def render_event(template_key, context):
	"""Render the editable WhatsApp Templates body for an event key.

	Looked up by template_name (the doc name carries a language suffix).
	Falls back to the built-in bodies when frappe_whatsapp is not installed."""
	context = expand_aliases(context)
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

	# Every message about a container leaves from the number of that container's
	# size — client, supervisor and driver alike — and from no other. A size
	# whose number is missing or unlinked blocks the send (logged) rather than
	# borrowing a different number, which is how the two lines got mixed up.
	size = context.get("container_size")
	if instance and frappe.db.exists("Whatsapp Instance", instance):
		sender = instance
	elif size:
		sender = instance_for_size(size)
		if not sender:
			frappe.log_error(
				message=f"No WhatsApp number set for container size {size}; '{template_key}' not sent to {mobile_no}",
				title="Container Rental: WhatsApp number not configured",
			)
			return
	else:
		sender = resolve_instance(instance)
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
	"""Send through frappe_whatsapp's unified Evolution sender: its stable
	operation key stops a retry after a timeout from delivering the same
	message twice. Builds of frappe_whatsapp that predate that helper fall
	back to a direct Evolution call. The WhatsApp Message audit row is written
	only once the send has actually succeeded."""
	inst = frappe.get_doc("Whatsapp Instance", instance)
	to = normalize_number(mobile_no)
	try:
		from frappe_whatsapp.utils.delivery_guard import delivery_key
		from frappe_whatsapp.utils.evolution import send_text as evolution_send_text
	except ImportError:
		message_id = _post_to_evolution(inst, to, body)
	else:
		operation_key = delivery_key(
			"container-rental", "whatsapp-text", inst.instance_name,
			to, reference_doc.doctype if reference_doc else "",
			reference_doc.name if reference_doc else "", body,
		)
		message_id = evolution_send_text(
			number=to,
			text=body,
			instance_name=inst.instance_name,
			operation_key=operation_key,
		)

	log = frappe.get_doc({
		"doctype": "WhatsApp Message",
		"type": "Outgoing",
		"message_type": "Template",  # with message_id set → stored without a Meta send
		"content_type": "text",
		"to": to,
		"message": body,
		"message_id": message_id or "evolution",
		"status": "Sent",
		"reference_doctype": reference_doc.doctype if reference_doc else None,
		"reference_name": reference_doc.name if reference_doc else None,
	})
	log.flags.ignore_permissions = True
	log.insert()


def _post_to_evolution(inst, to, body):
	"""Direct Evolution API call, used only where frappe_whatsapp has no
	unified sender — it carries no duplicate-send guard."""
	import requests

	server = frappe.get_doc("Evolution Server", inst.evolution_server)
	api_key = inst.get_password("api_key", raise_exception=False) or server.get_password("api_key", raise_exception=False)
	base_url = (server.base_url or "").rstrip("/")
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
	return data.get("key", {}).get("id") or data.get("message", {}).get("key", {}).get("id") or "evolution"


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
