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
		"customer_type": "Individual", "mobile_no": "0559999999", "cr_account_type": "نقدي",
	}).insert(ignore_permissions=True)

	container = frappe.get_doc({
		"doctype": "Container", "container_no": f"C-TEST-{suffix}", "size": "10 ياردة",
		"branch": "الفرع الرئيسي", "status": "متاحة",
	}).insert(ignore_permissions=True)
	results["barcode_svg"] = container.barcode.startswith("<svg")

	order = frappe.get_doc({
		"doctype": "Container Order", "client": client.name,
		"order_type": "Short Credit", "container_size": "10 ياردة",
		"container": container.name, "rental_days": 10, "rental_value": 350,
		"payment_method": "تحويل بنكي", "rental_start_date": frappe.utils.today(),
		"delivery_address": "موقع الاختبار",
	}).insert(ignore_permissions=True)

	# after_insert auto-advances every new order to "بانتظار تحديد سائق"
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
	frappe.get_doc({"doctype": "Container", "container_no": "C-REN-1", "size": "10 ياردة", "status": "متاحة"}).insert(ignore_permissions=True)
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
	entry = frappe.db.get_value("Driver Commission Entry", {"payout_status": "مستحقة", "commission_amount": (">", 0)})
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
	order = frappe.get_doc("Container Order", frappe.get_all("Container Order", filters={"status": "مُسنَد لسائق"}, limit=1)[0].name)
	ctx = order.get_whatsapp_context(); ctx["driver_name"] = "سواق1"
	print("---"); print(whatsapp.render_event("driver_assignment", ctx))


def supervisor_check():
	from frappe.utils import add_days, now_datetime
	from container_rental.container_rental import tasks
	rec = frappe.get_all("Rental Record", filters={"status": "مؤجرة", "source_doctype": "Container Order"}, limit=1)[0].name
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
	free = frappe.get_all("Container", filters={"status": "متاحة", "size": "10 ياردة"}, limit=1, pluck="name")[0]
	order.driver_confirm_delivery(free)
	order.reload()
	rec = frappe.get_doc("Rental Record", {"source_name": order.name})
	print("start == today (delivery day):", str(order.rental_start_date) == today(),
		"| end:", order.rental_end_date, "| record due:", rec.due_on)
	# متأخرة row with NULL due must still appear in the overdue report
	nodate = frappe.get_doc({"doctype": "Rental Record", "container": free, "container_size": "10 ياردة",
		"client": customer, "status": "متأخرة", "delivered_on": add_days(today(), -20),
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
	free = frappe.get_all("Container", filters={"status": "متاحة", "size": "10 ياردة"}, limit=1, pluck="name")[0]
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
	free = frappe.get_all("Container", filters={"status": "متاحة", "size": "10 ياردة"}, limit=1, pluck="name")[0]
	# office path: a Container Delivery form submitted directly (order.container stays empty)
	d = frappe.get_doc({"doctype": "Container Delivery", "order": order.name, "container": free,
		"driver": driver, "delivery_datetime": now_datetime()})
	d.insert(ignore_permissions=True); d.submit()
	print("status:", frappe.db.get_value("Container Order", order.name, "status"),
		"| container backfilled:", frappe.db.get_value("Container Order", order.name, "container"))
	# stuck-order patch check: force it back then run the patch
	frappe.db.set_value("Container Order", order.name, "status", "مُسنَد لسائق", update_modified=False)
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
	free = frappe.get_all("Container", filters={"status": "متاحة", "size": size}, limit=1, pluck="name")[0]
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
		free = frappe.get_all("Container", filters={"status": "متاحة", "size": "10 ياردة"}, limit=1, pluck="name")[0]
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
