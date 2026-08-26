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
		"order_type": "أجل قصير المدى", "container_size": "10 ياردة",
		"container": container.name, "rental_days": 10, "rental_value": 350,
		"payment_method": "تحويل بنكي", "rental_start_date": frappe.utils.today(),
		"delivery_address": "موقع الاختبار",
	}).insert(ignore_permissions=True)

	order.confirm_order()
	results["after_confirm"] = order.status  # بانتظار تأكيد الحوالة
	order.confirm_transfer()
	results["after_transfer"] = order.status
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
	results["commission_created"] = bool(frappe.db.exists(
		"Driver Commission Entry",
		{"delivery_reference_doctype": "Container Delivery", "delivery_reference": delivery.name},
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
		"unload_date": frappe.utils.today(), "unload_reason": "انتهاء المدة المحددة",
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
	order = frappe.get_doc({"doctype": "Container Order", "client": customer, "order_type": "دفع عند الاستلام",
		"container_size": "10 ياردة", "rental_days": 10, "rental_value": 500, "payment_method": "نقدي",
		"rental_start_date": frappe.utils.today(), "delivery_address": "حي النخيل"}).insert(ignore_permissions=True)
	print("status:", order.status, "| supervisor notifications +", frappe.db.count("Notification Log", {"for_user": sup}) - before)
	from container_rental.container_rental import whatsapp
	print(whatsapp.render_event("supervisor_new_order", dict(order.get_whatsapp_context(), driver_name="المشرف")))
	frappe.db.rollback()
