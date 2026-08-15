"""Whitelisted endpoints for the S9 dashboard and S11 overdue-containers page."""

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, get_datetime, now_datetime, today

from container_rental.container_rental import whatsapp


# ─── S9: dashboard cards ─────────────────────────────────────────────────────

@frappe.whitelist()
def get_dashboard_counts():
	"""All 13 dashboard card numbers in a single call."""
	now = now_datetime()
	counts = {}

	counts["total_containers"] = frappe.db.count("Container")
	counts["available_containers"] = frappe.db.count("Container", {"status": "متاحة"})
	counts["rented_containers"] = frappe.db.count("Container", {"status": "مؤجرة"})
	counts["withdrawn_containers"] = frappe.db.count("Container", {"status": "مسحوبة"})

	# Overdue = due date passed and not unloaded (rule from the requirements doc)
	counts["overdue_containers"] = frappe.db.count(
		"Rental Record",
		{"status": ("in", ["مؤجرة", "متأخرة"]), "due_on": ("<", now)},
	)

	# Payment delays: credit orders delivered, unpaid, past rental end + unpaid monthly invoices
	counts["payment_delays"] = frappe.db.count(
		"Container Order",
		{
			"payment_method": "آجل",
			"status": "تم التوصيل",
			"payment_received": 0,
			"rental_end_date": ("<", today()),
		},
	) + frappe.db.count(
		"Contract Monthly Invoice",
		{"docstatus": 1, "payment_status": ("!=", "مسددة")},
	)

	counts["oil_change_delays"] = len(
		frappe.db.sql(
			"""
			SELECT name FROM `tabTruck`
			WHERE (next_oil_change_date IS NOT NULL AND next_oil_change_date < %s)
			   OR (next_oil_change_km IS NOT NULL AND next_oil_change_km > 0
			       AND current_odometer_km >= next_oil_change_km)
			""",
			today(),
		)
	)

	settings = frappe.get_cached_doc("Container Rental Settings")
	horizon = add_days(today(), settings.expiry_alert_days or 30)

	counts["expired_permits"] = _expiry_count(upper=today())
	counts["truck_alerts"] = _truck_expiry_count(upper=horizon)
	counts["employee_alerts"] = _employee_expiry_count(upper=horizon)

	counts["expired_contracts"] = frappe.db.count(
		"Container Contract", {"docstatus": 1, "end_date": ("<", today())}
	)
	counts["expired_contracts_with_trips"] = frappe.db.count(
		"Container Contract",
		{"docstatus": 1, "end_date": ("<", today()), "remaining_trips": (">", 0)},
	)

	counts["credit_rentals"] = frappe.db.count(
		"Container Order",
		{"payment_method": "آجل", "status": ("not in", ["ملغي", "تم التوصيل"])},
	) + frappe.db.count(
		"Container Contract", {"docstatus": 1, "contract_status": "ساري"}
	)

	return counts


def _employee_expiry_count(upper):
	return len(
		frappe.db.sql(
			"""
			SELECT name FROM `tabCR Employee`
			WHERE status = 'نشط' AND (
				(iqama_expiry IS NOT NULL AND iqama_expiry <= %(upper)s)
				OR (insurance_expiry IS NOT NULL AND insurance_expiry <= %(upper)s)
				OR (driver_card_expiry IS NOT NULL AND driver_card_expiry <= %(upper)s)
			)
			""",
			{"upper": upper},
		)
	)


def _truck_expiry_count(upper):
	return len(
		frappe.db.sql(
			"""
			SELECT DISTINCT t.name FROM `tabTruck` t
			LEFT JOIN `tabTruck License` l ON l.parent = t.name
			WHERE (t.insurance_expiry IS NOT NULL AND t.insurance_expiry <= %(upper)s)
			   OR (t.registration_expiry IS NOT NULL AND t.registration_expiry <= %(upper)s)
			   OR (t.operating_card_expiry IS NOT NULL AND t.operating_card_expiry <= %(upper)s)
			   OR (l.expiry_date IS NOT NULL AND l.expiry_date <= %(upper)s)
			""",
			{"upper": upper},
		)
	)


def _expiry_count(upper):
	return _employee_expiry_count(upper) + _truck_expiry_count(upper)


# ─── S11: overdue containers (shared with the export report) ────────────────

def get_overdue_data(filters=None):
	"""Open rentals past due, most-overdue first. Shared by the S11 page and
	the 'تقرير الحاويات المتأخرة' script report so both show identical data."""
	filters = filters or {}
	conditions = ["r.status IN ('مؤجرة', 'متأخرة')", "r.due_on IS NOT NULL", "r.due_on < %(now)s"]
	values = {"now": now_datetime()}

	for field in ("classification", "container_size", "branch", "driver"):
		if filters.get(field):
			conditions.append(f"r.{field} = %({field})s")
			values[field] = filters[field]

	delay_range = filters.get("delay_range")
	if delay_range == "0-2":
		conditions.append("TIMESTAMPDIFF(HOUR, r.due_on, %(now)s) < 48")
	elif delay_range == "3-7":
		conditions.append("TIMESTAMPDIFF(HOUR, r.due_on, %(now)s) BETWEEN 48 AND 168")
	elif delay_range == "7+":
		conditions.append("TIMESTAMPDIFF(HOUR, r.due_on, %(now)s) > 168")

	rows = frappe.db.sql(
		f"""
		SELECT
			r.name AS rental_record,
			r.container, r.container_size, r.classification, r.branch,
			r.client, c.customer_name AS client_name, r.mobile_no, r.address,
			r.driver, e.employee_name AS driver_name,
			r.delivered_on, r.due_on,
			TIMESTAMPDIFF(HOUR, r.due_on, %(now)s) AS overdue_hours,
			r.last_whatsapp_message, r.last_whatsapp_on, r.unload_request_sent_on
		FROM `tabRental Record` r
		LEFT JOIN `tabCustomer` c ON c.name = r.client
		LEFT JOIN `tabCR Employee` e ON e.name = r.driver
		WHERE {" AND ".join(conditions)}
		ORDER BY overdue_hours DESC
		""",
		values,
		as_dict=True,
	)

	for row in rows:
		hours = max(0, row.overdue_hours or 0)
		row["overdue_days"] = hours // 24
		row["overdue_hours_part"] = hours % 24
		row["overdue_text"] = _("متأخرة {0} يوم {1} ساعة").format(hours // 24, hours % 24)
		if hours < 48:
			row["severity"] = "yellow"
			row["severity_label"] = _("أقل من يومين")
		elif hours <= 168:
			row["severity"] = "orange"
			row["severity_label"] = _("2 – 7 أيام")
		else:
			row["severity"] = "red"
			row["severity_label"] = _("أكثر من أسبوع")

	return rows


@frappe.whitelist()
def get_overdue_rentals(filters=None):
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)
	rows = get_overdue_data(filters)
	total = len(rows)
	avg_hours = sum(max(0, r.overdue_hours or 0) for r in rows) / total if total else 0
	over_week = len([r for r in rows if (r.overdue_hours or 0) > 168])
	return {
		"rows": rows,
		"stats": {
			"total": total,
			"avg_days": round(avg_hours / 24, 1),
			"over_week": over_week,
		},
	}


@frappe.whitelist()
def send_unload_request(rental_record):
	"""S11 quick action: WhatsApp + in-system notification to the supervisor."""
	record = frappe.get_doc("Rental Record", rental_record)
	settings = frappe.get_cached_doc("Container Rental Settings")
	if not settings.default_supervisor:
		frappe.throw(_("حدد مشرف السواقين الافتراضي في إعدادات النظام أولًا"))

	supervisor_mobile, supervisor_name, supervisor_user = frappe.db.get_value(
		"CR Employee", settings.default_supervisor, ["mobile_no", "employee_name", "user"]
	)
	client_name = frappe.db.get_value("Customer", record.client, "customer_name")
	overdue_hours = max(
		0, int((now_datetime() - get_datetime(record.due_on)).total_seconds() // 3600)
	) if record.due_on else 0

	whatsapp.send_event(
		"supervisor_unload_request",
		supervisor_mobile,
		{
			"client_name": client_name,
			"driver_name": supervisor_name,
			"container_no": record.container,
			"address": record.address or "",
			"due_date": frappe.format(record.due_on, {"fieldtype": "Datetime"}) if record.due_on else "",
			"overdue_days": overdue_hours // 24,
		},
		reference_doc=record,
	)

	if supervisor_user:
		frappe.get_doc({
			"doctype": "Notification Log",
			"for_user": supervisor_user,
			"subject": _("طلب تفريغ: الحاوية {0} لدى {1}").format(record.container, client_name),
			"email_content": _("العنوان: {0}").format(record.address or "-"),
			"type": "Alert",
		}).insert(ignore_permissions=True)

	record.db_set("unload_request_sent_on", now_datetime(), update_modified=False)
	return True


@frappe.whitelist()
def send_client_whatsapp(rental_record):
	"""S11 quick action: send the unload reminder to the client now.

	Returns {"sent": bool, "wa_link": url} — when the provider is not
	configured the UI falls back to opening wa.me with the rendered text.
	"""
	record = frappe.get_doc("Rental Record", rental_record)
	client_name = frappe.db.get_value("Customer", record.client, "customer_name")
	overdue_days = max(0, date_diff(today(), get_datetime(record.due_on).date())) if record.due_on else 0
	context = {
		"client_name": client_name,
		"container_no": record.container,
		"due_date": frappe.format(record.due_on, {"fieldtype": "Datetime"}) if record.due_on else "",
		"overdue_days": overdue_days,
		"address": record.address or "",
		"unload_date": "",
		"confirmation": 0,
	}

	configured = whatsapp.is_configured()
	whatsapp.send_event("unload_reminder", record.mobile_no, context, reference_doc=record)

	wa_link = None
	if not configured:
		body = whatsapp.render_event("unload_reminder", context) or ""
		number = whatsapp.normalize_number(record.mobile_no or "")
		wa_link = f"https://wa.me/{number}?text={frappe.utils.quote(body)}"
		# The user sends it manually via wa.me — still track it on the record
		whatsapp._stamp_rental_record(record, "unload_reminder")

	return {"sent": configured, "wa_link": wa_link}
