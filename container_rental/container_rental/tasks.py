"""Scheduled jobs: overdue flagging (hourly), daily alerts (07:00) and
monthly contract invoicing (1st of month). All jobs are idempotent and safe to
re-run manually via `bench execute`."""

import frappe
from frappe.utils import (
	add_days,
	add_months,
	date_diff,
	get_datetime,
	get_first_day,
	get_last_day,
	getdate,
	now_datetime,
	today,
)

from container_rental.container_rental import whatsapp


# ─── Hourly: overdue detection ───────────────────────────────────────────────

def mark_overdue_rentals():
	"""Rentals past due_on and not closed become متأخرة (S9/S11 source rule:
	'تاريخ التوصيل المتوقع منقضٍ ولم تُفرَّغ')."""
	overdue = frappe.get_all(
		"Rental Record",
		filters={"status": "مؤجرة", "due_on": ("<", now_datetime())},
		fields=["name", "container"],
	)
	for row in overdue:
		frappe.db.set_value("Rental Record", row.name, "status", "متأخرة", update_modified=False)
		# Don't override damaged/maintenance flags set manually in the meantime
		if frappe.db.get_value("Container", row.container, "status") == "مؤجرة":
			frappe.db.set_value("Container", row.container, "status", "متأخرة", update_modified=False)
	if overdue:
		frappe.db.commit()
	return len(overdue)


# ─── Daily: WhatsApp reminders + document expiry alerts ─────────────────────

def daily_alerts():
	settings = frappe.get_cached_doc("Container Rental Settings")
	send_unload_reminders(settings)
	send_contract_expiry_alerts(settings)
	send_supervisor_unload_requests(settings)
	send_document_expiry_alerts(settings)


def send_unload_reminders(settings):
	"""WhatsApp event 3: remind the client to allow unloading after N days."""
	threshold = add_days(now_datetime(), -(settings.unload_reminder_after_days or 2))
	records = frappe.get_all(
		"Rental Record",
		filters={"status": ("in", ["مؤجرة", "متأخرة"]), "delivered_on": ("<=", threshold)},
		fields=["name", "client", "mobile_no", "container", "due_on", "address", "last_whatsapp_on"],
	)
	for row in records:
		if row.last_whatsapp_on and get_datetime(row.last_whatsapp_on) > add_days(now_datetime(), -1):
			continue  # already messaged in the last 24h
		record = frappe.get_doc("Rental Record", row.name)
		client_name = frappe.db.get_value("Customer", row.client, "customer_name")
		overdue_days = max(0, date_diff(today(), getdate(row.due_on))) if row.due_on else 0
		whatsapp.send_event(
			"unload_reminder",
			row.mobile_no,
			{
				"client_name": client_name,
				"container_no": row.container,
				"due_date": frappe.format(row.due_on, {"fieldtype": "Datetime"}) if row.due_on else "",
				"overdue_days": overdue_days,
				"address": row.address or "",
				"unload_date": "",
				"confirmation": 0,
			},
			reference_doc=record,
		)


def send_contract_expiry_alerts(settings):
	"""WhatsApp event 5: notify long-term clients before contract end (once)."""
	horizon = add_days(today(), settings.contract_expiry_alert_days or 30)
	contracts = frappe.get_all(
		"Container Contract",
		filters={
			"docstatus": 1,
			"contract_status": "ساري",
			"end_date": ("between", [today(), horizon]),
			"expiry_alert_sent_on": ("is", "not set"),
		},
		fields=["name", "client", "end_date", "remaining_trips"],
	)
	for row in contracts:
		contract = frappe.get_doc("Container Contract", row.name)
		client_name, mobile_no = frappe.db.get_value("Customer", row.client, ["customer_name", "cr_mobile_no"])
		whatsapp.send_event(
			"contract_expiry",
			mobile_no,
			{
				"client_name": client_name,
				"contract_no": row.name,
				"end_date": frappe.format(row.end_date, {"fieldtype": "Date"}),
				"trips_count": row.remaining_trips or 0,
			},
			reference_doc=contract,
		)
		contract.db_set("expiry_alert_sent_on", today(), update_modified=False)


def send_supervisor_unload_requests(settings):
	"""WhatsApp event 6: overdue cash/short-term rentals → ask the supervisor
	to dispatch a driver for unloading."""
	supervisor = settings.default_supervisor
	if not supervisor:
		return
	supervisor_mobile, supervisor_name = frappe.db.get_value(
		"CR Employee", supervisor, ["mobile_no", "employee_name"]
	)
	records = frappe.get_all(
		"Rental Record",
		filters={
			"status": "متأخرة",
			"source_doctype": ("in", ["Container Order", "Container Rental"]),
			"unload_request_sent_on": ("is", "not set"),
		},
		fields=["name", "client", "container", "address", "due_on", "payment_method"],
	)
	for row in records:
		if row.payment_method == "آجل":
			continue  # section 5 event 6 targets cash / short-term rentals
		record = frappe.get_doc("Rental Record", row.name)
		client_name = frappe.db.get_value("Customer", row.client, "customer_name")
		whatsapp.send_event(
			"supervisor_unload_request",
			supervisor_mobile,
			{
				"client_name": client_name,
				"driver_name": supervisor_name,
				"container_no": row.container,
				"address": row.address or "",
				"due_date": frappe.format(row.due_on, {"fieldtype": "Datetime"}) if row.due_on else "",
				"overdue_days": max(0, date_diff(today(), getdate(row.due_on))) if row.due_on else 0,
			},
			reference_doc=record,
		)
		record.db_set("unload_request_sent_on", now_datetime(), update_modified=False)


EMPLOYEE_DATE_FIELDS = [
	("iqama_expiry", "انتهاء الإقامة"),
	("insurance_expiry", "انتهاء التأمين"),
	("driver_card_expiry", "انتهاء كارت السائق"),
]

TRUCK_DATE_FIELDS = [
	("insurance_expiry", "انتهاء تأمين الشاحنة"),
	("registration_expiry", "انتهاء الاستمارة"),
	("operating_card_expiry", "انتهاء كارت التشغيل"),
	("next_oil_change_date", "موعد غيار الزيت"),
]


def send_document_expiry_alerts(settings):
	"""In-system Notification Log alerts (S7/S8 source) + optional WhatsApp
	(open question 7: in-system by default)."""
	horizon = add_days(today(), settings.expiry_alert_days or 30)
	lines = []

	for emp in frappe.get_all(
		"CR Employee",
		filters={"status": "نشط"},
		fields=["name", "employee_name"] + [f for f, _l in EMPLOYEE_DATE_FIELDS],
	):
		for field, label in EMPLOYEE_DATE_FIELDS:
			value = emp.get(field)
			if value and getdate(value) <= getdate(horizon):
				lines.append(f"الموظف {emp.employee_name}: {label} بتاريخ {value}")

	for truck in frappe.get_all(
		"Truck", fields=["name", "vehicle_no"] + [f for f, _l in TRUCK_DATE_FIELDS]
	):
		for field, label in TRUCK_DATE_FIELDS:
			value = truck.get(field)
			if value and getdate(value) <= getdate(horizon):
				lines.append(f"الشاحنة {truck.vehicle_no}: {label} بتاريخ {value}")

	licenses = frappe.db.sql(
		"""
		SELECT t.vehicle_no, l.license_type, l.expiry_date
		FROM `tabTruck License` l JOIN `tabTruck` t ON l.parent = t.name
		WHERE l.expiry_date IS NOT NULL AND l.expiry_date <= %s
		""",
		horizon,
		as_dict=True,
	)
	for row in licenses:
		lines.append(f"الشاحنة {row.vehicle_no}: انتهاء {row.license_type} بتاريخ {row.expiry_date}")

	if not lines:
		return

	subject = f"تنبيهات وثائق ({len(lines)}) — الموظفون والشاحنات"
	message = "<br>".join(lines)
	for user in _users_with_roles(["Container Manager", "Driver Supervisor"]):
		_notify_user(user, subject, message)

	if settings.send_hr_alerts_via_whatsapp and settings.default_supervisor:
		mobile = frappe.db.get_value("CR Employee", settings.default_supervisor, "mobile_no")
		whatsapp.send_event(
			"supervisor_unload_request",
			mobile,
			{"client_name": "", "driver_name": "", "container_no": "", "address": subject,
			 "due_date": "", "overdue_days": 0},
			reference_doc=None,
		)


def _users_with_roles(roles):
	users = frappe.db.sql(
		"""
		SELECT DISTINCT hr.parent FROM `tabHas Role` hr
		JOIN `tabUser` u ON u.name = hr.parent
		WHERE hr.parenttype = 'User' AND hr.role IN %(roles)s
		  AND u.enabled = 1 AND hr.parent NOT IN ('Guest', 'Administrator')
		""",
		{"roles": tuple(roles)},
		pluck=True,
	)
	return users


def _notify_user(user, subject, message):
	# One notification per user per day for the digest
	if frappe.db.exists(
		"Notification Log",
		{"for_user": user, "subject": subject, "creation": (">=", today())},
	):
		return
	frappe.get_doc({
		"doctype": "Notification Log",
		"for_user": user,
		"subject": subject,
		"email_content": message,
		"type": "Alert",
	}).insert(ignore_permissions=True)


# ─── Monthly: contract invoicing (section 8) ────────────────────────────────

@frappe.whitelist()
def generate_monthly_invoices(month_key=None):
	"""Create one invoice per contract for the actual deliveries of a month.

	`month_key` like "2026-07"; defaults to the previous calendar month.
	Idempotent via the contract+month_key uniqueness guard.
	"""
	# Scheduler runs as Administrator; manual (whitelisted) runs are role-gated
	if frappe.session.user != "Administrator" and not set(frappe.get_roles()) & {
		"Container Manager",
		"System Manager",
	}:
		frappe.throw(frappe._("توليد الفواتير يتطلب صلاحية مدير الحاويات"), frappe.PermissionError)

	if month_key:
		period_start = getdate(f"{month_key}-01")
	else:
		period_start = get_first_day(add_months(today(), -1))
	period_end = get_last_day(period_start)
	month_key = period_start.strftime("%Y-%m")

	contracts = frappe.get_all(
		"Container Contract",
		filters={
			"docstatus": 1,
			"start_date": ("<=", period_end),
			"end_date": (">=", period_start),
		},
		fields=["name", "client"],
	)

	created = []
	for contract_row in contracts:
		if frappe.db.exists(
			"Contract Monthly Invoice",
			{"contract": contract_row.name, "month_key": month_key, "docstatus": ("<", 2)},
		):
			continue

		deliveries = frappe.db.sql(
			"""
			SELECT container_size, COUNT(*) AS trips
			FROM `tabRental Record`
			WHERE contract = %s AND delivered_on BETWEEN %s AND %s
			GROUP BY container_size
			""",
			(contract_row.name, period_start, add_days(period_end, 1)),
			as_dict=True,
		)
		if not deliveries:
			continue

		contract = frappe.get_doc("Container Contract", contract_row.name)
		prices = {item.container_size: item.price for item in contract.items}

		invoice = frappe.get_doc({
			"doctype": "Contract Monthly Invoice",
			"contract": contract.name,
			"client": contract.client,
			"month_key": month_key,
			"period_start": period_start,
			"period_end": period_end,
			"generated_on": now_datetime(),
			"lines": [
				{
					"container_size": d.container_size,
					"trips_delivered": d.trips,
					"price": prices.get(d.container_size, 0),
				}
				for d in deliveries
			],
		})
		invoice.flags.ignore_permissions = True
		invoice.insert()
		invoice.submit()

		# WhatsApp event 4: monthly invoice to the client
		client_name, mobile_no = frappe.db.get_value(
			"Customer", contract.client, ["customer_name", "cr_mobile_no"]
		)
		whatsapp.send_event(
			"monthly_invoice",
			mobile_no,
			{
				"client_name": client_name,
				"contract_no": contract.name,
				"invoice_no": invoice.name,
				"month": month_key,
				"total_amount": invoice.total_amount,
				"trips_count": sum(int(line.trips_delivered) for line in invoice.lines),
			},
			reference_doc=invoice,
		)
		invoice.db_set("whatsapp_sent", 1, update_modified=False)
		created.append(invoice.name)

	if created:
		frappe.db.commit()
	return created
