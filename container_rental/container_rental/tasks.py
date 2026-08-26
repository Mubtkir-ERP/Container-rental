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
from container_rental.container_rental.doctype.rental_record.rental_record import get_maps_link, get_order_link


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
		# Ask the supervisor to dispatch a driver right away (not at the next 07:00 run)
		send_supervisor_request(frappe.get_doc("Rental Record", row.name))
	if overdue:
		frappe.db.commit()
	return len(overdue)


def send_supervisor_request(record):
	"""WhatsApp event 6 for one overdue rental (cash / short-term only).
	Idempotent: skipped when a request was already sent for this rental."""
	from container_rental.container_rental import hr_utils

	if record.unload_request_sent_on or record.payment_method == "آجل":
		return False
	if record.source_doctype not in ("Container Order", "Container Rental"):
		return False
	_user, supervisor_name, supervisor_mobile = hr_utils.get_supervisor_contact()
	if not supervisor_mobile:
		return False
	client_name = frappe.db.get_value("Customer", record.client, "customer_name")
	whatsapp.send_event(
		"supervisor_unload_request",
		supervisor_mobile,
		{
			"client_name": client_name,
			"driver_name": supervisor_name,
			"container_no": record.container,
			"container_size": record.container_size,
			"address": record.address or "",
			"google_maps_link": get_maps_link(record),
			"order_link": get_order_link(record),
			"due_date": frappe.format(record.due_on, {"fieldtype": "Datetime"}) if record.due_on else "",
			"overdue_days": max(0, date_diff(today(), getdate(record.due_on))) if record.due_on else 0,
		},
		reference_doc=record,
	)
	record.db_set("unload_request_sent_on", now_datetime(), update_modified=False)
	return True


# ─── Daily: WhatsApp reminders + document expiry alerts ─────────────────────

def daily_alerts():
	settings = frappe.get_cached_doc("Container Rental Settings")
	send_unload_reminders(settings)
	send_contract_expiry_alerts(settings)
	send_supervisor_unload_requests(settings)
	send_document_expiry_alerts(settings)


def send_unload_reminders(settings):
	"""WhatsApp event 3: remind the client N days BEFORE the rental due date
	(the period is counted from the actual delivery day)."""
	horizon = add_days(now_datetime(), settings.unload_reminder_after_days or 2)
	records = frappe.get_all(
		"Rental Record",
		filters={"status": "مؤجرة", "due_on": ("between", [now_datetime(), horizon])},
		fields=["name", "client", "mobile_no", "container", "container_size", "due_on", "address", "last_whatsapp_on"],
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
				"container_size": row.container_size,
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
		client_name, mobile_no = frappe.db.get_value("Customer", row.client, ["customer_name", "mobile_no"])
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
	"""Daily safety net: any overdue cash/short-term rental still without a
	supervisor request (the hourly job normally sends it immediately)."""
	for name in frappe.get_all(
		"Rental Record",
		filters={"status": "متأخرة", "unload_request_sent_on": ("is", "not set")},
		pluck="name",
	):
		send_supervisor_request(frappe.get_doc("Rental Record", name))


def send_document_expiry_alerts(settings):
	"""In-system Notification Log alerts (S7/S8 source): employee documents
	(Employee.cr_documents) and truck documents (Truck.documents) child rows,
	plus overdue oil changes from the Truck oil-change child table."""
	horizon = add_days(today(), settings.expiry_alert_days or 30)
	lines = []

	employee_docs = frappe.db.sql(
		"""
		SELECT e.employee_name, d.document_name, d.expiry_date
		FROM `tabCR Document Item` d
		JOIN `tabEmployee` e ON d.parent = e.name AND d.parenttype = 'Employee'
		WHERE e.status = 'Active' AND d.expiry_date IS NOT NULL AND d.expiry_date <= %s
		ORDER BY d.expiry_date
		""",
		horizon,
		as_dict=True,
	)
	for row in employee_docs:
		lines.append(f"الموظف {row.employee_name}: انتهاء {row.document_name} بتاريخ {row.expiry_date}")

	truck_docs = frappe.db.sql(
		"""
		SELECT t.name AS vehicle_no, d.document_name, d.expiry_date
		FROM `tabCR Document Item` d
		JOIN `tabTruck` t ON d.parent = t.name AND d.parenttype = 'Truck'
		WHERE d.expiry_date IS NOT NULL AND d.expiry_date <= %s
		ORDER BY d.expiry_date
		""",
		horizon,
		as_dict=True,
	)
	for row in truck_docs:
		lines.append(f"الشاحنة {row.vehicle_no}: انتهاء {row.document_name} بتاريخ {row.expiry_date}")

	oil_overdue = frappe.db.sql(
		"""
		SELECT t.name AS vehicle_no, o.next_change_date, o.next_change_km, t.current_odometer_km
		FROM `tabTruck` t
		JOIN `tabTruck Oil Change` o ON o.parent = t.name
		WHERE o.change_date = (
			SELECT MAX(o2.change_date) FROM `tabTruck Oil Change` o2 WHERE o2.parent = t.name
		)
		AND (
			(o.next_change_date IS NOT NULL AND o.next_change_date <= %s)
			OR (o.next_change_km IS NOT NULL AND o.next_change_km > 0
			    AND t.current_odometer_km >= o.next_change_km)
		)
		""",
		today(),
		as_dict=True,
	)
	for row in oil_overdue:
		lines.append(
			f"الشاحنة {row.vehicle_no}: موعد غيار الزيت مستحق "
			f"(التاريخ: {row.next_change_date or '-'} / الكيلومتر: {row.next_change_km or '-'})"
		)

	if not lines:
		return

	subject = f"تنبيهات وثائق ({len(lines)}) — الموظفون والشاحنات"
	message = "<br>".join(lines)
	for user in _users_with_roles(["Container Manager", "Driver Supervisor"]):
		_notify_user(user, subject, message)

	# Optional WhatsApp copy of the digest to the drivers supervisor
	if settings.send_hr_alerts_via_whatsapp:
		from container_rental.container_rental import hr_utils

		_user, _name, supervisor_mobile = hr_utils.get_supervisor_contact()
		whatsapp.send_text(supervisor_mobile, subject + "\n" + "\n".join(lines))


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
			"Customer", contract.client, ["customer_name", "mobile_no"]
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
