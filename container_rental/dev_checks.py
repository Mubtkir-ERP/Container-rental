"""Temporary developer verification helpers (safe to remove in production)."""

import json
import traceback

import frappe


def counts():
	doctypes = [
		"Container", "Customer", "Employee", "Truck", "Container Order",
		"Container Contract", "Container Rental", "Rental Record",
		"Container Delivery", "Container Unload", "Container Withdrawal",
		"Driver Commission Entry", "Contract Monthly Invoice",
		"WhatsApp Templates", "WhatsApp Message",
	]
	out = {dt: frappe.db.count(dt) for dt in doctypes}
	out["container_statuses"] = frappe.db.sql(
		"select status, count(*) from tabContainer group by status", as_list=True
	)
	out["order_statuses"] = frappe.db.sql(
		"select status, count(*) from `tabContainer Order` group by status", as_list=True
	)
	out["rental_record_statuses"] = frappe.db.sql(
		"select status, count(*) from `tabRental Record` group by status", as_list=True
	)
	print(json.dumps(out, ensure_ascii=False, default=str))
	return out


def run_seed():
	from container_rental.patches import seed_demo_data

	try:
		seed_demo_data.execute()
		frappe.db.commit()
		print("SEED_OK")
	except Exception:
		frappe.db.rollback()
		traceback.print_exc()
		print("SEED_FAILED")


def e2e():
	"""End-to-end scenario: client → short-term order → transfer confirm →
	assign → deliver → overdue → S11 API → unload request → unload with fee →
	monthly invoicing idempotency → daily alerts."""
	from frappe.utils import add_days, now_datetime

	from container_rental import api
	from container_rental.container_rental import tasks

	results = {}
	suffix = frappe.generate_hash(length=5).upper()

	client = frappe.get_doc({
		"doctype": "Customer", "customer_name": f"عميل اختبار E2E {suffix}",
		"customer_type": "Individual", "mobile_no": "0559999999", "cr_account_type": "Cash",
	}).insert(ignore_permissions=True)

	container = frappe.get_doc({
		"doctype": "Container", "container_no": f"C-TEST-{suffix}", "size": "10 ياردة",
		"branch": "الفرع الرئيسي", "status": "Available",
	}).insert(ignore_permissions=True)
	results["barcode_svg"] = container.barcode.startswith("<svg")

	order = frappe.get_doc({
		"doctype": "Container Order", "client": client.name,
		"order_type": "Short Credit", "container_size": "10 ياردة",
		"container": container.name, "rental_days": 10, "rental_value": 350,
		"payment_method": "تحويل بنكي", "rental_start_date": frappe.utils.today(),
		"delivery_address": "موقع الاختبار",
	}).insert(ignore_permissions=True)

	# after_insert auto-advances every new order to "Awaiting Driver"
	results["after_insert_status"] = order.status
	driver = frappe.db.get_value("Employee", {"employee_name": "سالم القحطاني"})
	order.assign_driver(driver)
	results["after_assign"] = order.status

	delivery = frappe.get_doc({
		"doctype": "Container Delivery", "order": order.name, "container": container.name,
		"driver": driver, "delivery_datetime": now_datetime(),
	})
	delivery.insert(ignore_permissions=True)
	delivery.submit()
	order.reload()
	results["after_delivery_order"] = order.status
	results["after_delivery_container"] = frappe.db.get_value("Container", container.name, "status")
	record = frappe.db.get_value(
		"Rental Record", {"source_doctype": "Container Order", "source_name": order.name}
	)
	results["rental_record_created"] = bool(record)
	# Commission is earned at assignment, referenced to the order
	results["commission_created"] = bool(frappe.db.exists(
		"Driver Commission Entry",
		{"delivery_reference_doctype": "Container Order", "delivery_reference": order.name},
	))

	# Force overdue and run the hourly job
	frappe.db.set_value("Rental Record", record, "due_on", add_days(now_datetime(), -3), update_modified=False)
	tasks.mark_overdue_rentals()
	results["overdue_record"] = frappe.db.get_value("Rental Record", record, "status")
	results["overdue_container"] = frappe.db.get_value("Container", container.name, "status")

	# S11 API + quick action
	overdue = api.get_overdue_rentals({})
	results["s11_rows"] = overdue["stats"]["total"]
	results["s11_has_test"] = any(r["container"] == container.name for r in overdue["rows"])
	api.send_unload_request(record)
	results["unload_request_stamped"] = bool(
		frappe.db.get_value("Rental Record", record, "unload_request_sent_on")
	)

	# Unload with municipality fee → back to available
	unload = frappe.get_doc({
		"doctype": "Container Unload", "container": container.name,
		"unload_date": frappe.utils.today(), "unload_reason": "Specified Period Expired",
		"municipality_fee": 175, "send_whatsapp_confirmation": 1,
	})
	unload.insert(ignore_permissions=True)
	unload.submit()
	results["after_unload_container"] = frappe.db.get_value("Container", container.name, "status")
	results["after_unload_record"] = frappe.db.get_value("Rental Record", record, "status")

	# Monthly invoicing idempotency: second run creates nothing new
	before = frappe.db.count("Contract Monthly Invoice")
	tasks.generate_monthly_invoices()
	results["invoice_idempotent"] = frappe.db.count("Contract Monthly Invoice") == before

	# Daily alerts run clean and produce in-system notifications
	notif_before = frappe.db.count("Notification Log")
	tasks.daily_alerts()
	results["daily_alerts_notifications"] = frappe.db.count("Notification Log") - notif_before

	results["dashboard_keys"] = sorted(api.get_dashboard_counts().keys())
	results["whatsapp_configured"] = frappe.get_all(
		"WhatsApp Templates", pluck="name", order_by="name"
	)

	frappe.db.commit()
	import json
	print(json.dumps(results, ensure_ascii=False, indent=1, default=str))


def rename_check():
	"""Verify Container rename keeps container_no + barcode in sync (rolled back)."""
	frappe.get_doc({"doctype": "Container", "container_no": "C-REN-1", "size": "10 ياردة", "status": "Available"}).insert(ignore_permissions=True)
	frappe.rename_doc("Container", "C-REN-1", "C-REN-2", force=True)
	d = frappe.get_doc("Container", "C-REN-2")
	print("renamed:", d.name, "| field:", d.container_no, "| barcode ok:", d.barcode.startswith("<svg"))
	frappe.db.rollback()


def payout_check():
	"""Commission payout → Journal Entry (rolled back)."""
	from container_rental.container_rental.doctype.driver_commission_entry.driver_commission_entry import mark_paid
	from container_rental.container_rental import whatsapp

	print("workspace Driver Deliveries:", bool(frappe.db.exists("Workspace", "Driver Deliveries")))
	print("settings has expense acct field:", frappe.get_meta("Container Rental Settings").has_field("commission_expense_account"))
	expense = frappe.db.get_value("Account", {"account_name": "Commission on Sales", "is_group": 0})
	cash = frappe.db.get_value("Account", {"account_type": "Cash", "is_group": 0})
	frappe.db.set_value("Container Rental Settings", None, "commission_expense_account", expense)
	frappe.clear_cache(doctype="Container Rental Settings")
	entry = frappe.db.get_value("Driver Commission Entry", {"payout_status": "Due", "commission_amount": (">", 0)})
	amount = frappe.db.get_value("Driver Commission Entry", entry, "commission_amount")
	n = mark_paid([entry], payout_account=cash)
	je = frappe.db.get_value("Driver Commission Entry", entry, "journal_entry")
	jed = frappe.get_doc("Journal Entry", je)
	print(f"paid {n} | JE {je} docstatus={jed.docstatus} total_debit={jed.total_debit} (entry amount {amount}) | accounts:",
		[(a.account, a.debit, a.credit) for a in jed.accounts])
	print("size instance lookup:", whatsapp.instance_for_size("10 ياردة"))
	frappe.db.rollback()


def link_check():
	from container_rental.container_rental import whatsapp
	from container_rental.container_rental.doctype.rental_record.rental_record import get_order_link
	rec = frappe.get_doc("Rental Record", frappe.get_all("Rental Record", filters={"source_doctype": "Container Order"}, limit=1)[0].name)
	print(whatsapp.render_event("supervisor_unload_request", {"client_name": "x", "container_no": rec.container,
		"address": "y", "order_link": get_order_link(rec), "google_maps_link": "https://maps.app.goo.gl/x", "due_date": "", "overdue_days": 0}))
	order = frappe.get_doc("Container Order", frappe.get_all("Container Order", filters={"status": "Assigned"}, limit=1)[0].name)
	ctx = order.get_whatsapp_context(); ctx["driver_name"] = "سواق1"
	print("---"); print(whatsapp.render_event("driver_assignment", ctx))


def supervisor_check():
	from frappe.utils import add_days, now_datetime
	from container_rental.container_rental import tasks
	rec = frappe.get_all("Rental Record", filters={"status": "Rented", "source_doctype": "Container Order"}, limit=1)[0].name
	frappe.db.set_value("Rental Record", rec, {"due_on": add_days(now_datetime(), -1), "unload_request_sent_on": None}, update_modified=False)
	frappe.db.set_value("Rental Record", rec, "payment_method", "نقدي", update_modified=False)
	sup = frappe.db.get_single_value("Container Rental Settings", "default_supervisor")
	frappe.db.set_value("User", sup, "mobile_no", "0551000004", update_modified=False)
	n = tasks.mark_overdue_rentals()
	r = frappe.get_doc("Rental Record", rec)
	print("overdue flagged:", n, "| status:", r.status, "| supervisor request stamped:", bool(r.unload_request_sent_on))
	frappe.db.rollback()


def new_order_supervisor_check():
	sup = frappe.db.get_single_value("Container Rental Settings", "default_supervisor")
	frappe.db.set_value("User", sup, "mobile_no", "0551000004", update_modified=False)
	before = frappe.db.count("Notification Log", {"for_user": sup})
	customer = frappe.get_all("Customer", limit=1, pluck="name")[0]
	order = frappe.get_doc({"doctype": "Container Order", "client": customer, "order_type": "Cash",
		"container_size": "10 ياردة", "rental_days": 10, "rental_value": 500, "payment_method": "نقدي",
		"rental_start_date": frappe.utils.today(), "delivery_address": "حي النخيل"}).insert(ignore_permissions=True)
	print("status:", order.status, "| supervisor notifications +", frappe.db.count("Notification Log", {"for_user": sup}) - before)
	from container_rental.container_rental import whatsapp
	print(whatsapp.render_event("supervisor_new_order", dict(order.get_whatsapp_context(), driver_name="المشرف")))
	frappe.db.rollback()


def delivery_flow_check():
	from frappe.utils import add_days, today
	customer = frappe.get_all("Customer", limit=1, pluck="name")[0]
	driver = frappe.db.get_value("Employee", {"designation": "سائق", "status": "Active"})
	order = frappe.get_doc({"doctype": "Container Order", "client": customer, "order_type": "Cash",
		"container_size": "10 ياردة", "rental_days": 10, "rental_value": 750, "payment_method": "نقدي",
		"rental_start_date": add_days(today(), -5)}).insert(ignore_permissions=True)
	order.assign_driver(driver)
	free = frappe.get_all("Container", filters={"status": "Available", "size": "10 ياردة"}, limit=1, pluck="name")[0]
	order.driver_confirm_delivery(free)
	order.reload()
	rec = frappe.get_doc("Rental Record", {"source_name": order.name})
	print("start == today (delivery day):", str(order.rental_start_date) == today(),
		"| end:", order.rental_end_date, "| record due:", rec.due_on)
	# متأخرة row with NULL due must still appear in the overdue report
	nodate = frappe.get_doc({"doctype": "Rental Record", "container": free, "container_size": "10 ياردة",
		"client": customer, "status": "Overdue", "delivered_on": add_days(today(), -20),
		"source_doctype": "Container Order", "source_name": order.name})
	nodate.flags.ignore_permissions = True; nodate.insert()
	from container_rental import api
	rows = api.get_overdue_rentals({})["rows"]
	print("NULL-due overdue row in report:", any(r["rental_record"] == nodate.name for r in rows))
	frappe.db.rollback()


def driver_close_check():
	import traceback
	from frappe.utils import today
	customer = frappe.get_all("Customer", limit=1, pluck="name")[0]
	driver = frappe.db.get_value("Employee", {"designation": "سائق", "status": "Active"})
	order = frappe.get_doc({"doctype": "Container Order", "client": customer, "order_type": "Cash",
		"container_size": "10 ياردة", "rental_days": 10, "rental_value": 900, "payment_method": "نقدي",
		"rental_start_date": today()}).insert(ignore_permissions=True)
	order.assign_driver(driver)
	free = frappe.get_all("Container", filters={"status": "Available", "size": "10 ياردة"}, limit=1, pluck="name")[0]
	# Simulate the driver's run_doc_method path: fresh doc from dict like the client form sends
	client_doc = frappe.get_doc("Container Order", order.name)
	try:
		dn = client_doc.driver_confirm_delivery(free)
		status = frappe.db.get_value("Container Order", order.name, "status")
		print("delivery:", dn, "| status after confirm:", status)
		d = frappe.get_doc("Container Delivery", dn)
		print("delivery docstatus:", d.docstatus, "| delivered for order:",
			frappe.get_all("Container Delivery", filters={"order": order.name, "docstatus": 1}, pluck="container"),
			"| expected:", [c for _f, _s, c in frappe.get_doc("Container Order", order.name)._container_rows() if c])
	except Exception:
		traceback.print_exc()
	frappe.db.rollback()


def no_container_close_check():
	from frappe.utils import today, now_datetime
	customer = frappe.get_all("Customer", limit=1, pluck="name")[0]
	driver = frappe.db.get_value("Employee", {"designation": "سائق", "status": "Active"})
	# order WITHOUT a container number (the real new-scenario shape)
	order = frappe.get_doc({"doctype": "Container Order", "client": customer, "order_type": "Cash",
		"container_size": "10 ياردة", "rental_days": 10, "rental_value": 400, "payment_method": "نقدي",
		"rental_start_date": today()}).insert(ignore_permissions=True)
	order.assign_driver(driver)
	free = frappe.get_all("Container", filters={"status": "Available", "size": "10 ياردة"}, limit=1, pluck="name")[0]
	# office path: a Container Delivery form submitted directly (order.container stays empty)
	d = frappe.get_doc({"doctype": "Container Delivery", "order": order.name, "container": free,
		"driver": driver, "delivery_datetime": now_datetime()})
	d.insert(ignore_permissions=True); d.submit()
	print("status:", frappe.db.get_value("Container Order", order.name, "status"),
		"| container backfilled:", frappe.db.get_value("Container Order", order.name, "container"))
	# stuck-order patch check: force it back then run the patch
	frappe.db.set_value("Container Order", order.name, "status", "Assigned", update_modified=False)
	from container_rental.patches.close_delivered_orders import execute as fix
	fix()
	print("after patch:", frappe.db.get_value("Container Order", order.name, "status"))
	frappe.db.rollback()

def reassign_invoice_supervisor_check():
	"""Covers the four fixes: per-size supervisor, driver re-assignment with
	commission transfer + counter, delivery close, and Sales Invoice item
	resolution (site-language-independent group/UOM)."""
	from frappe.utils import today
	from container_rental.container_rental import hr_utils
	customer = frappe.get_all("Customer", limit=1, pluck="name")[0]
	drivers = frappe.get_all("Employee", filters={"designation": "سائق", "status": "Active"}, limit=2, pluck="name")
	if len(drivers) < 2:
		emp = frappe.get_doc({"doctype": "Employee", "first_name": "سائق ثاني للتجربة",
			"designation": "سائق", "status": "Active", "gender": "Male",
			"date_of_birth": "1990-01-01", "date_of_joining": "2020-01-01"})
		emp.flags.ignore_permissions = True
		emp.insert()
		drivers.append(emp.name)
	a, b = drivers[0], drivers[1]
	size = "10 ياردة"

	# 1) supervisor per size, with settings fallback
	su = frappe.get_all("User", filters={"enabled": 1}, limit=5, pluck="name")[-1]
	frappe.db.set_value("Container Size", size, "supervisor", su)
	print("size supervisor:", hr_utils.get_supervisor_contact(size)[0],
		"| fallback (no size):", hr_utils.get_supervisor_contact()[0])

	# 2) assign then re-assign
	order = frappe.get_doc({"doctype": "Container Order", "client": customer, "order_type": "Cash",
		"container_size": size, "rental_days": 10, "rental_value": 1000, "payment_method": "نقدي",
		"rental_start_date": today()}).insert(ignore_permissions=True)
	order.assign_driver(a)
	order.reload()
	print("after 1st assign — driver:", order.assigned_driver == a, "| count:", order.assignment_count)
	order.assign_driver(b)
	order.reload()
	entries = frappe.get_all("Driver Commission Entry",
		filters={"delivery_reference_doctype": "Container Order", "delivery_reference": order.name},
		fields=["driver", "commission_amount"])
	print("after reassign — driver:", order.assigned_driver == b, "| count:", order.assignment_count,
		"| commission entries:", [(e.driver == b, e.commission_amount) for e in entries])

	# 3) driver B delivers → order closes
	free = frappe.get_all("Container", filters={"status": "Available", "size": size}, limit=1, pluck="name")[0]
	frappe.get_doc("Container Order", order.name).driver_confirm_delivery(free)
	print("status after delivery:", frappe.db.get_value("Container Order", order.name, "status"))

	# 4) Sales Invoice with resolved item group / uom
	inv = frappe.get_doc("Container Order", order.name).make_sales_invoice()
	item = frappe.db.get_value("Sales Invoice Item", {"parent": inv}, "item_code")
	print("invoice:", bool(inv), "| item:", item,
		"| group/uom:", frappe.db.get_value("Item", item, ["item_group", "stock_uom"]))
	frappe.db.rollback()

def unload_flow_check():
	"""Driver-first unload requests: deliver → request to delivering driver →
	decline → reassign → confirm; replace flow duplicates the order; reminders
	skip requested rentals; extension gate honors the authorized user."""
	from frappe.utils import today, now_datetime
	from container_rental import api
	from container_rental.container_rental.doctype.container_unload_request import container_unload_request as cur

	customer = frappe.get_all("Customer", limit=1, pluck="name")[0]
	drivers = frappe.get_all("Employee", filters={"designation": "سائق", "status": "Active"}, limit=2, pluck="name")
	a, b = drivers[0], drivers[-1]

	def delivered_order():
		order = frappe.get_doc({"doctype": "Container Order", "client": customer, "order_type": "Cash",
			"container_size": "10 ياردة", "rental_days": 10, "rental_value": 300, "payment_method": "نقدي",
			"rental_start_date": today(), "google_maps_link": "https://maps.app.goo.gl/test"}).insert(ignore_permissions=True)
		order.assign_driver(a)
		free = frappe.get_all("Container", filters={"status": "Available", "size": "10 ياردة"}, limit=1, pluck="name")[0]
		frappe.get_doc("Container Order", order.name).driver_confirm_delivery(free)
		record = frappe.db.get_value("Rental Record", {"source_name": order.name}, ["name", "driver"], as_dict=True)
		return order, free, record

	# 1) unload request goes to the delivering driver
	order, container, record = delivered_order()
	res = api.send_unload_request(record.name)
	req = frappe.get_doc("Container Unload Request", res["request"])
	print("request → delivering driver:", req.assigned_driver == a == record.driver,
		"| status:", req.status, "| maps:", bool(req.google_maps_link), "| mobile:", bool(req.mobile_no))

	# idempotent: second call returns the same active request
	print("no duplicate request:", api.send_unload_request(record.name)["request"] == req.name)

	# 2) reminders skip rentals that have a request
	frappe.db.set_value("Rental Record", record.name, "due_on", now_datetime(), update_modified=False)
	from container_rental.container_rental import tasks
	tasks.send_unload_reminders(frappe.get_cached_doc("Container Rental Settings"))
	last = frappe.db.get_value("Rental Record", record.name, "last_whatsapp_message")
	print("client reminder suppressed:", last != "unload_reminder")

	# 3) decline → supervisor reassign → confirm by the new driver
	req.driver_decline()
	print("after decline:", frappe.db.get_value("Container Unload Request", req.name, "status"))
	req.reload(); req.assign_driver(b)
	print("after reassign:", req.status, "| driver B:", req.assigned_driver == b)
	req.reload(); out = req.driver_confirm()
	print("after confirm — request:", frappe.db.get_value("Container Unload Request", req.name, "status"),
		"| unload docstatus:", frappe.db.get_value("Container Unload", out["unload"], "docstatus"),
		"| container:", frappe.db.get_value("Container", container, "status"),
		"| rental:", frappe.db.get_value("Rental Record", record.name, "status"))

	# 4) replace flow duplicates the order on confirmation
	order2, container2, record2 = delivered_order()
	res2 = api.send_unload_request(record2.name, request_type="Replace")
	req2 = frappe.get_doc("Container Unload Request", res2["request"])
	out2 = req2.driver_confirm()
	new_order = frappe.get_doc("Container Order", out2["new_order"])
	commission = frappe.db.exists("Driver Commission Entry",
		{"delivery_reference_doctype": "Container Order", "delivery_reference": new_order.name,
		 "driver": req2.assigned_driver})
	print("replace — new order:", bool(new_order), "| same client:", new_order.client == customer,
		"| same size:", new_order.container_size == "10 ياردة",
		"| auto-assigned to confirming driver:", new_order.assigned_driver == req2.assigned_driver,
		"| status:", new_order.status, "| commission:", bool(commission),
		"| old container freed:", frappe.db.get_value("Container", container2, "status"))
	notified = frappe.db.count("Notification Log",
		{"document_name": new_order.name, "subject": ("like", "%بانتظار إسناد سائق%")})
	print("supervisor skipped on replace:", notified == 0)

	# the driver can hand the replacement order back to the supervisor
	new_order.driver_return_to_supervisor()
	new_order.reload()
	commission_after = frappe.db.exists("Driver Commission Entry",
		{"delivery_reference_doctype": "Container Order", "delivery_reference": new_order.name})
	print("after return — status:", new_order.status, "| driver cleared:", not new_order.assigned_driver,
		"| commission dropped:", not commission_after,
		"| supervisor notified:", frappe.db.count("Notification Log",
			{"document_name": new_order.name, "subject": ("like", "%أعاد السائق%")}) > 0)

	# 5) extension authorized user gate
	order3, container3, record3 = delivered_order()
	rakan = "cs@containers.demo"  # stands in for راكان: an office user set as the authorized one
	frappe.db.set_value("Container Rental Settings", None, "extension_authorized_user", rakan)
	frappe.get_cached_doc("Container Rental Settings")  # refresh cache
	frappe.clear_cache(doctype="Container Rental Settings")
	other = "manager@containers.demo"
	frappe.set_user(other)
	try:
		api.extend_rental(record3.name, 5, 100)
		print("gate blocks others: FAIL")
	except frappe.PermissionError:
		print("gate blocks others: True")
	frappe.set_user(rakan)
	try:
		ok = api.extend_rental(record3.name, 5, 100)
		print("authorized user extends:", bool(ok.get("order")))
	except Exception as e:
		print("authorized extend failed:", e)
	frappe.set_user("Administrator")
	frappe.db.rollback()

def payment_tax_supervisor_check():
	"""This round's fixes: the driver's payment method reaches the order, the
	invoice carries the tax template + method, and a supervisor flagged as a
	driver can take an order himself."""
	from frappe.utils import today
	from container_rental.container_rental import hr_utils

	customer = frappe.get_all("Customer", limit=1, pluck="name")[0]
	driver = frappe.db.get_value("Employee", {"designation": "سائق", "status": "Active"})
	cash, transfer = "نقدي", "تحويل بنكي"

	order = frappe.get_doc({"doctype": "Container Order", "client": customer, "order_type": "Cash",
		"container_size": "10 ياردة", "rental_days": 10, "rental_value": 800, "payment_method": cash,
		"rental_start_date": today()}).insert(ignore_permissions=True)
	order.assign_driver(driver)
	free = frappe.get_all("Container", filters={"status": "Available", "size": "10 ياردة"}, limit=1, pluck="name")[0]
	# the driver switches the method on site
	frappe.get_doc("Container Order", order.name).driver_confirm_delivery(
		free, payment_method=transfer)
	order.reload()
	print("driver's payment method saved:", order.payment_method == transfer,
		"| status:", order.status)

	# invoice: tax template + collected method (seed a default template when the
	# site has none, so the lookup path is actually exercised)
	company = frappe.defaults.get_user_default("Company") or frappe.db.get_value("Company", {})
	if not frappe.db.get_value("Sales Taxes and Charges Template", {"is_default": 1, "company": company}):
		vat = frappe.db.get_value("Account", {"account_type": "Tax", "is_group": 0, "company": company}) \
			or frappe.db.get_value("Account", {"is_group": 0, "root_type": "Liability", "company": company})
		tpl = frappe.get_doc({
			"doctype": "Sales Taxes and Charges Template", "title": "VAT 15% Test",
			"company": company, "is_default": 1,
			"taxes": [{"charge_type": "On Net Total", "account_head": vat, "description": "VAT 15%", "rate": 15}],
		})
		tpl.flags.ignore_permissions = True
		tpl.insert()
	inv_name = frappe.get_doc("Container Order", order.name).make_sales_invoice()
	inv = frappe.get_doc("Sales Invoice", inv_name)
	default_tpl = frappe.db.get_value("Sales Taxes and Charges Template", {"is_default": 1, "company": inv.company})
	print("invoice taxes template:", inv.taxes_and_charges, "| rows:", len(inv.taxes),
		"| tax total:", inv.total_taxes_and_charges, "| site default:", default_tpl)
	print("invoice carries method:", inv.get("cr_payment_method") == transfer,
		"| links order:", inv.get("cr_container_order") == order.name)

	# supervisor who also drives
	supervisor = frappe.db.get_value("Employee", {"designation": "مشرف سواقين", "status": "Active"})
	if not supervisor:
		supervisor = frappe.get_all("Employee", filters={"status": "Active"}, limit=1, pluck="name")[0]
	print("before flag — is_driver:", hr_utils.is_driver(supervisor))
	frappe.db.set_value("Employee", supervisor, "cr_is_driver", 1)
	print("after flag — is_driver:", hr_utils.is_driver(supervisor))
	order2 = frappe.get_doc({"doctype": "Container Order", "client": customer, "order_type": "Cash",
		"container_size": "10 ياردة", "rental_days": 5, "rental_value": 200, "payment_method": cash,
		"rental_start_date": today()}).insert(ignore_permissions=True)
	order2.assign_driver(supervisor)  # supervisor assigns the order to himself
	order2.reload()
	print("supervisor self-assign:", order2.assigned_driver == supervisor, "| status:", order2.status)
	names = [r[0] for r in hr_utils.driver_query("Employee", "", "name", 0, 50, None)]
	print("supervisor in driver picker:", supervisor in names, "| picker size:", len(names))
	frappe.db.rollback()

def supervisor_confirm_check():
	"""A supervisor flagged as a driver assigns an order to himself and then
	confirms the delivery from his own screen — the order must close."""
	from frappe.utils import today
	from container_rental.container_rental import hr_utils

	customer = frappe.get_all("Customer", limit=1, pluck="name")[0]
	supervisor = frappe.db.get_value("Employee", {"designation": "مشرف سواقين", "status": "Active"}) \
		or frappe.get_all("Employee", filters={"status": "Active"}, limit=1, pluck="name")[0]
	frappe.db.set_value("Employee", supervisor, "cr_is_driver", 1)
	user = frappe.db.get_value("Employee", supervisor, "user_id")
	print("supervisor:", supervisor, "| user:", user, "| roles:", sorted(set(frappe.get_roles(user)) & {
		"Driver", "Driver Supervisor", "Container Manager", "System Manager", "Customer Service"}) if user else None)

	order = frappe.get_doc({"doctype": "Container Order", "client": customer, "order_type": "Cash",
		"container_size": "10 ياردة", "rental_days": 7, "rental_value": 500, "payment_method": "نقدي",
		"rental_start_date": today()}).insert(ignore_permissions=True)
	order.assign_driver(supervisor)
	free = frappe.get_all("Container", filters={"status": "Available", "size": "10 ياردة"}, limit=1, pluck="name")[0]

	if user:
		frappe.set_user(user)
	try:
		fresh = frappe.get_doc("Container Order", order.name)
		dn = fresh.driver_confirm_delivery(free, payment_method="نقدي")
		print("confirm returned delivery:", dn,
			"| order status:", frappe.db.get_value("Container Order", order.name, "status"),
			"| container:", frappe.db.get_value("Container", free, "status"))
	except Exception as exc:
		print("confirm FAILED:", type(exc).__name__, exc)
	finally:
		frappe.set_user("Administrator")
	print("my driver employee (as supervisor):", hr_utils.get_my_driver_employee() if not user else "n/a")
	frappe.db.rollback()

def unload_from_screen_check():
	"""Creating a Container Unload draft must ask the delivering driver first:
	the request carries his name, the list shows it, and his confirmation
	submits that same draft (no duplicate unload)."""
	from frappe.utils import today
	from container_rental.container_rental import hr_utils

	customer = frappe.get_all("Customer", limit=1, pluck="name")[0]
	driver = frappe.db.get_value("Employee", {"designation": "سائق", "status": "Active"})
	order = frappe.get_doc({"doctype": "Container Order", "client": customer, "order_type": "Cash",
		"container_size": "10 ياردة", "rental_days": 10, "rental_value": 600, "payment_method": "نقدي",
		"rental_start_date": today()}).insert(ignore_permissions=True)
	order.assign_driver(driver)
	free = frappe.get_all("Container", filters={"status": "Available", "size": "10 ياردة"}, limit=1, pluck="name")[0]
	frappe.get_doc("Container Order", order.name).driver_confirm_delivery(free)

	before = frappe.db.count("Container Unload")
	unload = frappe.get_doc({"doctype": "Container Unload", "container": free,
		"unload_date": today(), "unload_reason": "Customer Request"})
	unload.flags.ignore_permissions = True
	unload.insert()
	unload.reload()
	req = frappe.db.get_value("Container Unload Request", {"unload_reference": unload.name},
		["name", "status", "assigned_driver"], as_dict=True)
	print("draft unload → request:", bool(req), "| to delivering driver:", req and req.assigned_driver == driver,
		"| unload.driver:", unload.driver == driver, "| driver_name:", unload.driver_name,
		"| request_status on unload:", unload.request_status)

	request = frappe.get_doc("Container Unload Request", req.name)
	request.driver_confirm()
	unload.reload()
	print("after driver confirm — same unload submitted:", unload.docstatus == 1,
		"| no duplicate unload:", frappe.db.count("Container Unload") == before + 1,
		"| container:", frappe.db.get_value("Container", free, "status"),
		"| request:", frappe.db.get_value("Container Unload Request", req.name, "status"),
		"| unload.request_status:", frappe.db.get_value("Container Unload", unload.name, "request_status"))
	frappe.db.rollback()

def template_address_check():
	"""The admin-edited supervisor template uses {{ delivery_address }} while the
	code sends "address" — rendering must fill either spelling, and fall back to
	the customer's saved location when the order has no address typed."""
	from frappe.utils import today
	from container_rental.container_rental import whatsapp

	customer = frappe.get_all("Customer", limit=1, pluck="name")[0]
	cust = frappe.get_doc("Customer", customer)
	if not cust.get("cr_delivery_locations"):
		cust.append("cr_delivery_locations", {"address_title": "الفرع", "address": "حي الورود - شارع 20", "is_default": 1})
		cust.flags.ignore_permissions = True
		cust.save()

	# order WITHOUT a typed address (the real production shape) + with one
	for typed in (None, "حي النخيل - مستودع 5"):
		order = frappe.get_doc({"doctype": "Container Order", "client": customer, "order_type": "Cash",
			"container_size": "10 ياردة", "rental_days": 5, "rental_value": 300, "payment_method": "نقدي",
			"rental_start_date": today(), "delivery_address": typed,
			"google_maps_link": "https://maps.app.goo.gl/x"}).insert(ignore_permissions=True)
		ctx = whatsapp.expand_aliases(order.get_whatsapp_context())
		body = frappe.render_template(
			"Location: {{ delivery_address }} | Addr: {{ address }} | Map: {{ map_link }} | Cust: {{ customer_name }}", ctx)
		print(("typed  " if typed else "no addr"), "→", body)

	# the real stored template, rendered through the adapter
	rendered = whatsapp.render_event("supervisor_new_order", order.get_whatsapp_context())
	print("stored template has address line:", "حي النخيل" in (rendered or "") or "الورود" in (rendered or ""))
	frappe.db.rollback()

def replace_after_unload_check():
	"""Production path: operator saves a Container Unload (which already asks
	the driver), then presses Replace Container. The driver's confirmation must
	still create the replacement order and assign it to him."""
	from frappe.utils import today
	from container_rental import api

	customer = frappe.get_all("Customer", limit=1, pluck="name")[0]
	driver = frappe.db.get_value("Employee", {"designation": "سائق", "status": "Active"})
	order = frappe.get_doc({"doctype": "Container Order", "client": customer, "order_type": "Cash",
		"container_size": "10 ياردة", "rental_days": 10, "rental_value": 700, "payment_method": "نقدي",
		"rental_start_date": today()}).insert(ignore_permissions=True)
	order.assign_driver(driver)
	free = frappe.get_all("Container", filters={"status": "Available", "size": "10 ياردة"}, limit=1, pluck="name")[0]
	frappe.get_doc("Container Order", order.name).driver_confirm_delivery(free)
	record = frappe.db.get_value("Rental Record", {"source_name": order.name})

	# 1) operator saves the unload → request goes out as a plain unload
	unload = frappe.get_doc({"doctype": "Container Unload", "container": free,
		"unload_date": today(), "unload_reason": "Customer Request"})
	unload.flags.ignore_permissions = True
	unload.insert()
	req_name = frappe.db.get_value("Container Unload Request", {"unload_reference": unload.name})
	print("after save — request type:", frappe.db.get_value("Container Unload Request", req_name, "request_type"))

	# 2) operator presses Replace Container on the same unload
	res = api.send_unload_request(record, request_type="Replace")
	print("replace reuses same request:", res["request"] == req_name,
		"| type now:", frappe.db.get_value("Container Unload Request", req_name, "request_type"))

	# 3) driver confirms → unload submitted + replacement order assigned to him
	out = frappe.get_doc("Container Unload Request", req_name).driver_confirm()
	new_order = frappe.get_doc("Container Order", out["new_order"]) if out.get("new_order") else None
	print("replacement order created:", bool(new_order),
		"| assigned to same driver:", bool(new_order) and new_order.assigned_driver == driver,
		"| status:", new_order.status if new_order else "-",
		"| container freed:", frappe.db.get_value("Container", free, "status"))
	frappe.db.rollback()

def commission_rule_check():
	"""Commission is configured per container size: a percentage of the order
	value or a fixed amount per delivery, each with its own expense account."""
	from frappe.utils import today
	from container_rental.container_rental import hr_utils
	from container_rental.container_rental.doctype.driver_commission_entry.driver_commission_entry import mark_paid

	size = "10 ياردة"
	customer = frappe.get_all("Customer", limit=1, pluck="name")[0]
	driver = frappe.db.get_value("Employee", {"designation": "سائق", "status": "Active"})
	expense = frappe.db.get_value("Account", {"account_name": "Commission on Sales", "is_group": 0})
	cash = frappe.db.get_value("Account", {"account_type": "Cash", "is_group": 0})
	frappe.db.set_value("Container Rental Settings", None, "commission_expense_account", expense)
	frappe.clear_cache(doctype="Container Rental Settings")

	def place(value=1000):
		order = frappe.get_doc({"doctype": "Container Order", "client": customer, "order_type": "Cash",
			"container_size": size, "rental_days": 5, "rental_value": value, "payment_method": "نقدي",
			"rental_start_date": today()}).insert(ignore_permissions=True)
		order.assign_driver(driver)
		return frappe.db.get_value("Driver Commission Entry",
			{"delivery_reference": order.name}, ["commission_amount", "commission_basis", "expense_account"], as_dict=True)

	# a) nothing configured on the size → settings default percent (4%)
	frappe.db.set_value("Container Size", size, {"commission_type": None, "commission_percent": 0,
		"commission_amount": 0, "commission_expense_account": None})
	e = place()
	print("fallback percent:", e.commission_amount, "|", e.commission_basis, "| acct:", e.expense_account == expense)

	# b) percentage on the size
	frappe.db.set_value("Container Size", size, {"commission_type": "Percentage", "commission_percent": 7})
	e = place()
	print("size percentage :", e.commission_amount, "|", e.commission_basis)

	# c) fixed amount on the size + its own expense account
	other = frappe.db.get_value("Account", {"is_group": 0, "root_type": "Expense",
		"name": ("!=", expense)}) or expense
	frappe.db.set_value("Container Size", size, {"commission_type": "Fixed Amount",
		"commission_amount": 35, "commission_expense_account": other})
	e = place(9999)
	print("size fixed      :", e.commission_amount, "|", e.commission_basis, "| own acct:", e.expense_account == other)

	# payout uses the entry's own account
	entry = frappe.db.get_value("Driver Commission Entry",
		{"expense_account": other, "payout_status": "Due"})
	mark_paid([entry], payout_account=cash)
	je = frappe.db.get_value("Driver Commission Entry", entry, "journal_entry")
	accounts = [(a.account, a.debit, a.credit) for a in frappe.get_doc("Journal Entry", je).accounts]
	print("payout JE uses size account:", any(a[0] == other and a[1] for a in accounts), "|", accounts)
	frappe.db.rollback()

def truck_expense_voucher_check():
	"""Maintenance / oil-change rows are paid with a submitted Journal Entry
	(Dr vehicle expense / Cr cash), linked back on the row and never twice."""
	from frappe.utils import today
	from container_rental.container_rental.doctype.truck import truck as truck_api

	expense = frappe.db.get_value("Account", {"is_group": 0, "root_type": "Expense"})
	cash = frappe.db.get_value("Account", {"account_type": "Cash", "is_group": 0})
	frappe.db.set_value("Container Rental Settings", None, "maintenance_expense_account", expense)
	frappe.clear_cache(doctype="Container Rental Settings")

	name = frappe.db.get_value("Truck", {})
	doc = frappe.get_doc("Truck", name) if name else frappe.get_doc({
		"doctype": "Truck", "vehicle_no": "TRK-TEST-1"}).insert(ignore_permissions=True)
	doc.append("maintenance_log", {"maintenance_date": today(), "maintenance_type": "Brakes", "cost": 450})
	doc.append("oil_changes", {"change_date": today(), "cost": 120, "odometer_km": 90000})
	doc.flags.ignore_permissions = True
	doc.save()
	doc.reload()
	m_row = doc.maintenance_log[-1]
	o_row = doc.oil_changes[-1]

	unpaid = truck_api.get_unpaid_expense_rows(doc.name)
	print("unpaid rows found:", len(unpaid), "| labels:", [u["label"] for u in unpaid][:4])

	je = truck_api.make_expense_voucher(doc.name, "maintenance_log", m_row.name, payout_account=cash)
	jed = frappe.get_doc("Journal Entry", je)
	print("maintenance voucher:", je, "| submitted:", jed.docstatus == 1,
		"| accounts:", [(a.account, a.debit, a.credit) for a in jed.accounts])
	doc.reload()
	row = next(r for r in doc.maintenance_log if r.name == m_row.name)
	print("row linked:", row.journal_entry == je, "| paid_on:", bool(row.paid_on))

	try:
		truck_api.make_expense_voucher(doc.name, "maintenance_log", m_row.name, payout_account=cash)
		print("double pay blocked: FAIL")
	except frappe.ValidationError:
		print("double pay blocked: True")

	je2 = truck_api.make_expense_voucher(doc.name, "oil_changes", o_row.name, payout_account=cash,
		expense_account=expense)
	print("oil voucher:", bool(je2), "| remaining unpaid:", len(truck_api.get_unpaid_expense_rows(doc.name)))
	frappe.db.rollback()

def unload_type_flow_check():
	"""One message per unload: the type is chosen on the document itself.
	A) Unload → one request, driver confirms, closed.
	B) Unload and Replace → one request worded as a replacement, driver
	   confirms → the unload closes AND a new order is assigned to him; his
	   delivery confirmation on that order marks it Delivered."""
	from frappe.utils import today

	customer = frappe.get_all("Customer", limit=1, pluck="name")[0]
	driver = frappe.db.get_value("Employee", {"designation": "سائق", "status": "Active"})

	def rented_container(value=500):
		order = frappe.get_doc({"doctype": "Container Order", "client": customer, "order_type": "Cash",
			"container_size": "10 ياردة", "rental_days": 10, "rental_value": value, "payment_method": "نقدي",
			"rental_start_date": today()}).insert(ignore_permissions=True)
		order.assign_driver(driver)
		free = frappe.get_all("Container", filters={"status": "Available", "size": "10 ياردة"},
			limit=1, pluck="name")[0]
		frappe.get_doc("Container Order", order.name).driver_confirm_delivery(free)
		return free

	def messages_for(request_name):
		return frappe.db.count("WhatsApp Message",
			{"reference_doctype": "Container Unload Request", "reference_name": request_name})

	# ── A) plain unload
	c1 = rented_container()
	u1 = frappe.get_doc({"doctype": "Container Unload", "container": c1, "unload_date": today(),
		"unload_reason": "Customer Request", "unload_type": "Unload"})
	u1.flags.ignore_permissions = True
	u1.insert()
	r1 = frappe.db.get_value("Container Unload Request", {"unload_reference": u1.name},
		["name", "request_type"], as_dict=True)
	print("A: type:", r1.request_type, "| messages:", messages_for(r1.name))
	out1 = frappe.get_doc("Container Unload Request", r1.name).driver_confirm()
	u1.reload()
	print("A: unload submitted:", u1.docstatus == 1, "| new order:", out1.get("new_order"),
		"| container:", frappe.db.get_value("Container", c1, "status"))

	# ── B) unload and replace
	c2 = rented_container(650)
	u2 = frappe.get_doc({"doctype": "Container Unload", "container": c2, "unload_date": today(),
		"unload_reason": "Customer Request", "unload_type": "Unload and Replace"})
	u2.flags.ignore_permissions = True
	u2.insert()
	r2 = frappe.db.get_value("Container Unload Request", {"unload_reference": u2.name},
		["name", "request_type"], as_dict=True)
	print("B: type:", r2.request_type, "| messages:", messages_for(r2.name))
	out2 = frappe.get_doc("Container Unload Request", r2.name).driver_confirm()
	new_order = frappe.get_doc("Container Order", out2["new_order"])
	print("B: new order:", new_order.name, "| assigned to same driver:",
		new_order.assigned_driver == driver, "| status:", new_order.status,
		"| old container:", frappe.db.get_value("Container", c2, "status"))

	# driver delivers the replacement → order must become Delivered
	free = frappe.get_all("Container", filters={"status": "Available", "size": "10 ياردة"},
		limit=1, pluck="name")[0]
	frappe.get_doc("Container Order", new_order.name).driver_confirm_delivery(free)
	print("B: replacement delivered:", frappe.db.get_value("Container Order", new_order.name, "status"),
		"| total messages on request:", messages_for(r2.name))
	frappe.db.rollback()

def unload_message_count_check():
	"""Count the actual WhatsApp sends per unload: exactly one request message
	for either type, plus the assignment message when a replacement order is
	created (and the client's thank-you on unload)."""
	from frappe.utils import today
	from container_rental.container_rental import whatsapp

	sent = []
	real = whatsapp.send_event
	whatsapp.send_event = lambda key, mobile, ctx, **kw: sent.append(key)
	try:
		customer = frappe.get_all("Customer", limit=1, pluck="name")[0]
		driver = frappe.db.get_value("Employee", {"designation": "سائق", "status": "Active"})

		def rented():
			order = frappe.get_doc({"doctype": "Container Order", "client": customer, "order_type": "Cash",
				"container_size": "10 ياردة", "rental_days": 10, "rental_value": 400,
				"payment_method": "نقدي", "rental_start_date": today()}).insert(ignore_permissions=True)
			order.assign_driver(driver)
			free = frappe.get_all("Container", filters={"status": "Available", "size": "10 ياردة"},
				limit=1, pluck="name")[0]
			frappe.get_doc("Container Order", order.name).driver_confirm_delivery(free)
			return free

		for unload_type in ("Unload", "Unload and Replace"):
			container = rented()
			sent.clear()
			u = frappe.get_doc({"doctype": "Container Unload", "container": container,
				"unload_date": today(), "unload_reason": "Customer Request", "unload_type": unload_type})
			u.flags.ignore_permissions = True
			u.insert()
			print(f"{unload_type:18} on save  →", sent or ["(none)"])
			req = frappe.db.get_value("Container Unload Request", {"unload_reference": u.name})
			sent.clear()
			frappe.get_doc("Container Unload Request", req).driver_confirm()
			print(f"{unload_type:18} on confirm →", sent or ["(none)"])
	finally:
		whatsapp.send_event = real
		frappe.db.rollback()

def reminder_once_check():
	"""The client reminder must land on the exact day (N days before due,
	whatever time the container went out) and never repeat."""
	from frappe.utils import add_days, today
	from container_rental.container_rental import tasks, whatsapp

	sent = []
	real = whatsapp.send_event
	whatsapp.send_event = lambda key, mobile, ctx, **kw: sent.append((key, ctx.get("container_no")))
	try:
		settings = frappe.get_cached_doc("Container Rental Settings")
		days = settings.unload_reminder_after_days or 2
		customer = frappe.get_all("Customer", limit=1, pluck="name")[0]
		driver = frappe.db.get_value("Employee", {"designation": "سائق", "status": "Active"})

		def rented(due_in_days):
			order = frappe.get_doc({"doctype": "Container Order", "client": customer,
				"order_type": "Cash", "container_size": "10 ياردة", "rental_days": due_in_days,
				"rental_value": 300, "payment_method": "نقدي",
				"rental_start_date": today()}).insert(ignore_permissions=True)
			order.assign_driver(driver)
			free = frappe.get_all("Container", filters={"status": "Available", "size": "10 ياردة"},
				limit=1, pluck="name")[0]
			frappe.get_doc("Container Order", order.name).driver_confirm_delivery(free)
			rec = frappe.db.get_value("Rental Record", {"source_name": order.name})
			# a late-evening due time is what made the old window job slip a day
			frappe.db.set_value("Rental Record", rec,
				"due_on", f"{add_days(today(), due_in_days)} 23:50:00", update_modified=False)
			return rec, free

		rec, container = rented(days)
		sent.clear()
		tasks.send_unload_reminders(settings)
		first = [k for k, c in sent if c == container]
		stamped = frappe.db.get_value("Rental Record", rec, "reminder_sent_on")
		sent.clear()
		tasks.send_unload_reminders(settings)
		tasks.send_unload_reminders(settings)
		repeats = [k for k, c in sent if c == container]
		print("reminder on target day:", first, "| stamped:", bool(stamped), "| repeats:", repeats or "none")

		rec2, container2 = rented(days + 1)
		sent.clear()
		tasks.send_unload_reminders(settings)
		print("rental due a day later skipped:",
			not frappe.db.get_value("Rental Record", rec2, "reminder_sent_on"))
	finally:
		whatsapp.send_event = real
		frappe.db.rollback()


def whatsapp_number_check():
	"""Every container message must leave from its size's number — never from
	another size's number or a site default."""
	from container_rental.container_rental import whatsapp

	sizes = frappe.get_all("Container Size", fields=["name", "whatsapp_instance"])
	print("sizes:", [(s.name, s.whatsapp_instance) for s in sizes])
	print("settings field removed:", not frappe.get_meta("Container Rental Settings").has_field("default_whatsapp_instance"))

    # a size pointing at a missing instance must resolve to nothing
	size = sizes[0].name
	frappe.db.set_value("Container Size", size, "whatsapp_instance", "does-not-exist")
	print("missing instance → no sender:", whatsapp.instance_for_size(size) is None)

	sent = []
	real = whatsapp._send_via_evolution
	whatsapp._send_via_evolution = lambda inst, mobile, body, ref=None: sent.append(inst)
	try:
		whatsapp._send_event("order_confirmation", "0559999999",
			{"container_size": size, "client_name": "x"}, None)
		print("blocked instead of borrowing a number:", sent == [])
	finally:
		whatsapp._send_via_evolution = real
		frappe.db.rollback()

def contract_fields_check():
	"""Contract: duration drives the end date, payment method / terms are free
	text, VAT is shown but never posted, and the payments table is gone."""
	from frappe.utils import add_months, today
	meta = frappe.get_meta("Container Contract")
	print("payments table removed:", not meta.has_field("payments"),
		"| paid/outstanding gone:", not meta.has_field("paid_amount") and not meta.has_field("outstanding"))
	print("new fields:", [f for f in ("contract_duration", "duration_unit", "payment_method",
		"payment_terms", "apply_vat", "vat_percent", "vat_amount", "total_with_vat") if meta.has_field(f)])

	customer = frappe.get_all("Customer", limit=1, pluck="name")[0]
	c = frappe.get_doc({"doctype": "Container Contract", "client": customer,
		"start_date": today(), "contract_duration": 6, "duration_unit": "Months",
		"end_date": today(), "trip_duration_days": 5,
		"payment_method": "تحويل بنكي على دفعتين", "payment_terms": "50% مقدمًا والباقي بعد شهرين",
		"apply_vat": 1, "vat_percent": 15,
		"items": [{"container_size": "10 ياردة", "trips_count": 10, "price": 200}]})
	c.flags.ignore_permissions = True
	c.insert()
	print("end date from duration:", str(c.end_date) == str(add_months(today(), 6)), "→", c.end_date)
	print("value:", c.contract_value, "| vat:", c.vat_amount, "| with vat:", c.total_with_vat)
	print("free text kept:", c.payment_method, "|", c.payment_terms)

	c.apply_vat = 0
	c.save()
	print("vat off → amount:", c.vat_amount, c.total_with_vat)

	# the VAT shown here must not reach any ledger
	c.apply_vat = 1
	c.save()
	c.submit()
	gl = frappe.db.count("GL Entry", {"voucher_type": "Container Contract", "voucher_no": c.name}) \
		if frappe.db.table_exists("GL Entry") else 0
	print("no accounting impact:", gl == 0)

	from container_rental.container_rental import customer_utils
	print("client balance still computes:", customer_utils.refresh_balance(customer) is not None)
	frappe.db.rollback()

def evolution_sender_check():
	"""The unified frappe_whatsapp sender (with its duplicate-send guard) is
	used when available; older builds fall back to the direct call."""
	import sys, types
	from container_rental.container_rental import whatsapp

	existing = frappe.get_all("Whatsapp Instance", limit=1, pluck="name") if frappe.db.table_exists("Whatsapp Instance") else []
	inst = existing[0] if existing else None
	if not inst:
		server = frappe.get_doc({"doctype": "Evolution Server", "server_label": "test",
			"base_url": "https://example.test", "api_key": "x"})
		server.flags.ignore_permissions = True
		server.insert()
		doc = frappe.get_doc({"doctype": "Whatsapp Instance", "instance_name": "test-inst",
			"evolution_server": server.name, "connection_status": "Connected"})
		doc.flags.ignore_permissions = True
		doc.insert()
		inst = doc.name

	# a) unified sender present → used, with an operation key
	calls = {}
	ev = types.ModuleType("frappe_whatsapp.utils.evolution")

	def fake_send(number, text, instance_name, operation_key):
		calls["unified"] = {"to": number, "instance": instance_name, "key": bool(operation_key)}
		return "MSG-1"

	ev.send_text = fake_send
	dg = types.ModuleType("frappe_whatsapp.utils.delivery_guard")
	dg.delivery_key = lambda *parts: "key-" + str(len(parts))
	sys.modules["frappe_whatsapp.utils.evolution"] = ev
	sys.modules["frappe_whatsapp.utils.delivery_guard"] = dg
	try:
		whatsapp._send_via_evolution(inst, "0559999999", "hello", None)
		logged = frappe.db.get_value("WhatsApp Message", {"message": "hello"}, "message_id")
		print("unified sender used:", calls.get("unified"), "| logged id:", logged)
	finally:
		sys.modules.pop("frappe_whatsapp.utils.evolution", None)
		sys.modules.pop("frappe_whatsapp.utils.delivery_guard", None)

	# b) older build → direct call fallback
	posted = {}
	real_post = whatsapp._post_to_evolution
	def fake_post(i, to, body):
		posted["direct"] = to
		return "MSG-2"

	whatsapp._post_to_evolution = fake_post
	try:
		whatsapp._send_via_evolution(inst, "0559999999", "fallback", None)
		print("fallback used when helper missing:", posted.get("direct") is not None,
			"| logged id:", frappe.db.get_value("WhatsApp Message", {"message": "fallback"}, "message_id"))
	finally:
		whatsapp._post_to_evolution = real_post
		frappe.db.rollback()

def representative_routing_check():
	"""Client-facing messages go to the representative's number when the order
	says so, and to the client's own otherwise — through the whole lifecycle."""
	from frappe.utils import today
	from container_rental.container_rental import tasks, whatsapp

	sent = []
	real = whatsapp.send_event
	whatsapp.send_event = lambda key, mobile, ctx, **kw: sent.append((key, mobile))
	try:
		customer = frappe.get_all("Customer", limit=1, pluck="name")[0]
		client_mobile = frappe.db.get_value("Customer", customer, "mobile_no")
		driver = frappe.db.get_value("Employee", {"designation": "سائق", "status": "Active"})
		rep = "0590001111"

		def run(use_rep):
			order = frappe.get_doc({"doctype": "Container Order", "client": customer,
				"order_type": "Cash", "container_size": "10 ياردة", "rental_days": 3,
				"rental_value": 250, "payment_method": "نقدي", "rental_start_date": today(),
				"use_representative": 1 if use_rep else 0,
				"representative_mobile": rep if use_rep else None}).insert(ignore_permissions=True)
			order.reload()
			order.assign_driver(driver)
			free = frappe.get_all("Container", filters={"status": "Available", "size": "10 ياردة"},
				limit=1, pluck="name")[0]
			sent.clear()
			frappe.get_doc("Container Order", order.name).driver_confirm_delivery(free)
			confirm_to = [m for k, m in sent if k == "order_confirmation"]
			rec = frappe.db.get_value("Rental Record", {"source_name": order.name}, "mobile_no")
			return order, confirm_to, rec

		o1, to1, rec1 = run(False)
		print("client number kept from the card:", o1.mobile_no == client_mobile,
			"| confirmation to:", to1, "| rental stores:", rec1)

		o2, to2, rec2 = run(True)
		print("representative used:", to2 == [rep], "| rental stores:", rec2 == rep,
			"| client field untouched:", o2.mobile_no == client_mobile)

		# the reminder for that rental also follows the representative
		settings = frappe.get_cached_doc("Container Rental Settings")
		days = settings.unload_reminder_after_days or 2
		frappe.db.set_value("Rental Record", frappe.db.get_value("Rental Record", {"source_name": o2.name}),
			"due_on", f"{frappe.utils.add_days(today(), days)} 09:00:00", update_modified=False)
		sent.clear()
		tasks.send_unload_reminders(settings)
		print("reminder to:", [m for k, m in sent if k == "unload_reminder"])
	finally:
		whatsapp.send_event = real
		frappe.db.rollback()


def no_double_send_check():
	import io

	"""The audit row must be log-only: WhatsApp Message's own before_insert
	would otherwise send the text a second time, from the session user's
	instance instead of the container size's."""
	import sys, types
	from container_rental.container_rental import whatsapp

	server = frappe.db.get_value("Evolution Server", {"name": ("is", "set")}) or frappe.get_doc({
		"doctype": "Evolution Server", "server_label": "dbl",
		"base_url": "https://example.test", "api_key": "x"}).insert(ignore_permissions=True).name
	if not frappe.db.exists("Whatsapp Instance", "inst-dbl"):
		frappe.get_doc({"doctype": "Whatsapp Instance", "instance_name": "inst-dbl",
			"evolution_server": server, "connection_status": "Connected"}).insert(ignore_permissions=True)

	ev = types.ModuleType("frappe_whatsapp.utils.evolution")
	ev.send_text = lambda number, text, instance_name, operation_key: "MSG-X"
	dg = types.ModuleType("frappe_whatsapp.utils.delivery_guard")
	dg.delivery_key = lambda *parts: "k"
	sys.modules["frappe_whatsapp.utils.evolution"] = ev
	sys.modules["frappe_whatsapp.utils.delivery_guard"] = dg
	try:
		whatsapp._send_via_evolution("inst-dbl", "0559999999", "trace-body", None)
		meta = frappe.get_meta("WhatsApp Message")
		fields = ["name", "message_id"] + [f for f in ("channel", "send_from_instance") if meta.has_field(f)]
		rows = frappe.get_all("WhatsApp Message", filters={"message": "trace-body"}, fields=fields)
		print("rows logged:", len(rows), "| id:", rows[0].message_id)
		if meta.has_field("send_from_instance"):
			print("channel:", rows[0].channel, "| instance recorded:", rows[0].send_from_instance)
		else:
			print("routing columns absent on this frappe_whatsapp build (production has them)")
		src = io.open("/home/frappe/bench-2/apps/container_rental/container_rental/container_rental/whatsapp.py",
			encoding="utf-8").read()
		print("log-only flag set in sender:", "log.flags.skip_meta_send = True" in src,
			"| instance passed:", '"send_from_instance": instance' in src)
	finally:
		sys.modules.pop("frappe_whatsapp.utils.evolution", None)
		sys.modules.pop("frappe_whatsapp.utils.delivery_guard", None)
		frappe.db.rollback()
