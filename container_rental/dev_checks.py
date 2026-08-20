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
		"customer_type": "Individual", "cr_mobile_no": "0559999999", "cr_account_type": "نقدي",
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
