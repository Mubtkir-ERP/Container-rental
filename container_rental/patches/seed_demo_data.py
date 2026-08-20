"""Seed demo data so every screen (S1–S12) is demonstrable out of the box.

Data is created through the real controllers/transition methods so all side
effects (rental records, commissions, contract trips, WhatsApp logs) fire.
Idempotent — exits early if the sentinel branch exists.
"""

import frappe
from frappe.utils import add_days, add_months, get_first_day, now_datetime, today

SENTINEL_BRANCH = "الفرع الرئيسي"

DEMO_USERS = [
	("cs@containers.demo", "موظف خدمة العملاء", ["Customer Service"]),
	("transfer@containers.demo", "موظف متابعة الحوالات", ["Transfer Follow-up"]),
	("supervisor@containers.demo", "مشرف السواقين", ["Driver Supervisor"]),
	("manager@containers.demo", "مدير الحاويات", ["Container Manager"]),
]


def execute():
	if frappe.db.exists("Rental Branch", SENTINEL_BRANCH):
		return

	frappe.flags.in_import = True  # keep notifications/emails quiet

	branches = seed_branches()
	classifications = seed_classifications()
	users = seed_users()
	employees = seed_employees(branches, users)
	seed_settings(employees)
	seed_trucks(branches, employees)
	containers = seed_containers(branches, classifications, employees)
	clients = seed_clients()

	seed_orders(clients, containers, employees)
	contract = seed_active_contract(clients, containers, employees, classifications)
	seed_expired_contract(clients, classifications)
	seed_walkin_rentals(clients, containers, classifications, employees)
	seed_manual_statuses(containers)

	# Flag the backdated rentals as overdue (S11 shows yellow/orange/red rows)
	from container_rental.container_rental import tasks

	tasks.mark_overdue_rentals()
	tasks.generate_monthly_invoices()
	mark_one_commission_paid()

	frappe.flags.in_import = False
	frappe.db.commit()


# ─── Masters ─────────────────────────────────────────────────────────────────

def seed_branches():
	names = [SENTINEL_BRANCH, "فرع الشمال"]
	for name in names:
		if not frappe.db.exists("Rental Branch", name):
			frappe.get_doc({"doctype": "Rental Branch", "branch_name": name}).insert(ignore_permissions=True)
	return names


def get_cash_account():
	"""A Cash account from the chart of accounts (accountants add per-driver
	boxes manually — the app only links to existing accounts)."""
	return frappe.db.get_value("Account", {"account_type": "Cash", "is_group": 0})


def seed_classifications():
	names = ["أنقاض", "مخلفات بناء", "نفايات عامة"]
	for name in names:
		if not frappe.db.exists("Container Classification", name):
			frappe.get_doc({"doctype": "Container Classification", "classification_name": name}).insert(
				ignore_permissions=True
			)
	return names


def seed_users():
	users = {}
	for email, full_name, roles in DEMO_USERS:
		if not frappe.db.exists("User", email):
			user = frappe.get_doc({
				"doctype": "User",
				"email": email,
				"first_name": full_name,
				"enabled": 1,
				"send_welcome_email": 0,
				"language": "ar",
				"new_password": "Hwyat!Demo#2026",
				"roles": [{"role": r} for r in roles],
			})
			user.insert(ignore_permissions=True)
		users[roles[0]] = email
	frappe.db.set_value("User", users["Driver Supervisor"], "mobile_no", "0551000004", update_modified=False)
	return users


def seed_employees(branches, users):
	"""Employees are ERPNext Employees; expiring papers live in the documents
	child table; drivers get Sales Person records with the per-delivery rate."""
	from container_rental.container_rental import hr_utils

	company = frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {})
	rows = [
		# (name, designation, commission, documents[(label, expiry)], mobile, user)
		("سالم القحطاني", "سائق", 15,
		 [("كارت السائق", add_days(today(), 200)), ("التأمين", add_days(today(), 90))],
		 "0551000001", None),
		("محمد عبدالرحمن", "سائق", 20,
		 [("الإقامة", add_days(today(), 12)), ("كارت السائق", add_days(today(), -5))],
		 "0551000002", None),
		("أحمد خان", "سائق", 25,
		 [("الإقامة", add_days(today(), 100)), ("التأمين", add_days(today(), 45))],
		 "0551000003", None),
		("خالد المطيري", "مشرف سواقين", 0,
		 [("التأمين", add_days(today(), 120))], "0551000004", users.get("Driver Supervisor")),
		("نورة الشمري", "موظف خدمة عملاء", 0, [], "0551000005", users.get("Customer Service")),
		("فهد العتيبي", "موظف متابعة حوالات", 0, [], "0551000006", users.get("Transfer Follow-up")),
		("عبدالله الحربي", "إداري", 0, [], "0551000007", users.get("Container Manager")),
	]
	employees = {}
	for name, designation, commission, documents, mobile, user in rows:
		existing = frappe.db.get_value("Employee", {"employee_name": name})
		if existing:
			employees[name] = existing
			continue
		doc = frappe.get_doc({
			"doctype": "Employee",
			"first_name": name,
			"employee_name": name,
			"company": company,
			"status": "Active",
			"gender": "Male" if name != "نورة الشمري" else "Female",
			"date_of_birth": "1990-01-01",
			"date_of_joining": add_days(today(), -365),
			"designation": designation,
			"cell_number": mobile,
			"user_id": user,
			"cr_documents": [
				{"document_name": label, "expiry_date": expiry} for label, expiry in documents
			],
		})
		doc.flags.ignore_permissions = True
		doc.flags.ignore_mandatory = True
		doc.insert()
		employees[name] = doc.name

		if designation == "سائق":
			sales_person = hr_utils.ensure_sales_person(doc.name)
			frappe.db.set_value(
				"Sales Person", sales_person, "cr_commission_per_delivery", commission,
				update_modified=False,
			)
	return employees


def seed_settings(employees):
	settings = frappe.get_doc("Container Rental Settings")
	settings.default_rental_days = 10
	settings.expiry_alert_days = 30
	settings.unload_reminder_after_days = 2
	settings.contract_expiry_alert_days = 30
	settings.default_supervisor = "supervisor@containers.demo"
	settings.flags.ignore_permissions = True
	settings.save()


def seed_trucks(branches, employees):
	drivers = ["سالم القحطاني", "محمد عبدالرحمن", "أحمد خان"]
	rows = [
		{
			"vehicle_no": "أ ب ج 1234",
			"vehicle_type": "شاحنة رفع حاويات",
			"model_year": 2021,
			"current_odometer_km": 125000,
			"documents": [
				("تأمين الشاحنة", add_days(today(), 180)),
				("الاستمارة", add_days(today(), 90)),
				("كارت التشغيل", add_days(today(), 45)),
			],
			"oil_changes": [
				{"change_date": add_days(today(), -60), "odometer_km": 115000, "cost": 350,
				 "next_change_km": 120000, "next_change_date": add_days(today(), -10)},
			],
			"maintenance_log": [
				{"maintenance_date": add_days(today(), -90), "maintenance_type": "فرامل",
				 "cost": 900, "odometer_km": 110000},
			],
		},
		{
			"vehicle_no": "د هـ و 5678",
			"vehicle_type": "قلاب",
			"model_year": 2019,
			"current_odometer_km": 98000,
			"documents": [
				("تأمين الشاحنة", add_days(today(), 9)),
				("الاستمارة", add_days(today(), 200)),
			],
			"oil_changes": [
				{"change_date": add_days(today(), -20), "odometer_km": 95000, "cost": 320,
				 "next_change_km": 105000, "next_change_date": add_days(today(), 70)},
			],
			"maintenance_log": [],
		},
		{
			"vehicle_no": "ز ح ط 9012",
			"vehicle_type": "شاحنة رفع حاويات",
			"model_year": 2023,
			"current_odometer_km": 40000,
			"documents": [
				("تصريح دخول المرادم", add_days(today(), -2)),
				("الاستمارة", add_days(today(), 15)),
			],
			"oil_changes": [],
			"maintenance_log": [
				{"maintenance_date": add_days(today(), -35), "maintenance_type": "صيانة دورية",
				 "cost": 1500, "odometer_km": 38000, "next_maintenance_date": add_days(today(), 55)},
			],
		},
	]
	for i, row in enumerate(rows):
		if frappe.db.exists("Truck", row["vehicle_no"]):
			continue
		documents = row.pop("documents")
		doc = frappe.get_doc({
			"doctype": "Truck",
			"branch": branches[i % 2],
			"driver": frappe.db.get_value("Employee", {"employee_name": drivers[i]}),
			"documents": [
				{"document_name": label, "expiry_date": expiry} for label, expiry in documents
			],
			**row,
		})
		doc.flags.ignore_permissions = True
		doc.insert()


def seed_containers(branches, classifications, employees):
	drivers = [
		employees.get("سالم القحطاني"),
		employees.get("محمد عبدالرحمن"),
		employees.get("أحمد خان"),
	]
	containers = []
	for i in range(1, 21):
		container_no = f"C-{1000 + i}"
		containers.append(container_no)
		if frappe.db.exists("Container", container_no):
			continue
		frappe.get_doc({
			"doctype": "Container",
			"container_no": container_no,
			"size": "10 ياردة" if i <= 12 else "20 ياردة",
			"classification": classifications[i % 3],
			"branch": branches[i % 2],
			"responsible_driver": drivers[i % 3],
			"status": "متاحة",
		}).insert(ignore_permissions=True)
	return containers


def seed_clients():
	"""Clients are ERPNext Customers extended with the app's custom fields."""
	rows = [
		("مؤسسة البناء الحديث", "Company", "0501111111", "آجل", ["حي العليا — شارع التحلية", "حي الملز — مخرج 15"]),
		("شركة الإعمار للمقاولات", "Company", "0502222222", "آجل", ["حي النرجس — مشروع الفلل"]),
		("عبدالعزيز السبيعي", "Individual", "0503333333", "نقدي", ["حي الياسمين"]),
		("منصور الدوسري", "Individual", "0504444444", "نقدي", []),
		("مصنع الخرسانة المتحدة", "Company", "0505555555", "آجل", ["المنطقة الصناعية الثانية"]),
		("سارة العنزي", "Individual", "0506666666", "نقدي", ["حي الروضة"]),
	]
	clients = {}
	for name, ctype, mobile, account, addresses in rows:
		existing = frappe.db.get_value("Customer", {"customer_name": name})
		if existing:
			clients[name] = existing
			continue
		doc = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": name,
			"customer_type": ctype,
			"cr_mobile_no": mobile,
			"cr_account_type": account,
			"cr_delivery_locations": [
				{"address_title": f"موقع {i + 1}", "address": a, "is_default": 1 if i == 0 else 0}
				for i, a in enumerate(addresses)
			],
		})
		doc.flags.ignore_permissions = True
		doc.flags.ignore_mandatory = True
		doc.insert()
		clients[name] = doc.name
	return clients


# ─── Transactions through the real flows ────────────────────────────────────

def _driver(name):
	return frappe.db.get_value("Employee", {"employee_name": name})


def seed_orders(clients, containers, employees):
	supervisor_vehicle = frappe.db.get_value("Truck", {"vehicle_type": "شاحنة رفع حاويات"})

	def new_order(client, order_type, size, container=None, **kwargs):
		order = frappe.get_doc({
			"doctype": "Container Order",
			"client": client,
			"order_type": order_type,
			"container_size": size,
			"container": container,
			"classification": "أنقاض",
			"rental_days": None if order_type == "أجل طويل المدى" else 10,
			"rental_value": kwargs.pop("rental_value", 400),
			"payment_method": kwargs.pop("payment_method", "نقدي"),
			"rental_start_date": today(),
			"required_delivery_date": add_days(today(), 1),
			"delivery_time": "09:00:00",
			"delivery_address": kwargs.pop("delivery_address", "الرياض"),
			**kwargs,
		})
		order.insert(ignore_permissions=True)
		return order

	# 1) جديد
	new_order(clients["منصور الدوسري"], "أجل قصير المدى", "10 ياردة", payment_method="تحويل بنكي")

	# 2) بانتظار تأكيد الحوالة
	o2 = new_order(clients["عبدالعزيز السبيعي"], "أجل قصير المدى", "10 ياردة", payment_method="تحويل بنكي")
	o2.confirm_order()

	# 3) بانتظار تحديد سائق
	o3 = new_order(clients["سارة العنزي"], "دفع عند الاستلام", "10 ياردة")
	o3.confirm_order()

	# 4) مُسنَد لسائق — multi-container order (open question 2)
	o4 = new_order(
		clients["مؤسسة البناء الحديث"], "دفع عند الاستلام", "10 ياردة",
		container=containers[6],  # C-1007
		delivery_address="حي العليا — شارع التحلية",
	)
	o4.append("additional_containers", {"container_size": "20 ياردة", "container": containers[14], "rental_value": 550})
	o4.save(ignore_permissions=True)
	o4.confirm_order()
	o4.assign_driver(_driver("سالم القحطاني"), supervisor_vehicle)

	# 5) تم التوصيل (آجل — feeds the credit-rentals card)
	o5 = new_order(
		clients["مصنع الخرسانة المتحدة"], "أجل طويل المدى", "20 ياردة",
		container=containers[15],  # C-1016
		payment_method="آجل", rental_value=600,
		delivery_address="المنطقة الصناعية الثانية",
	)
	o5.rental_days = 10
	o5.save(ignore_permissions=True)
	o5.confirm_order()
	o5.assign_driver(_driver("أحمد خان"), supervisor_vehicle)
	delivery = frappe.get_doc({
		"doctype": "Container Delivery",
		"order": o5.name,
		"container": containers[15],
		"driver": _driver("أحمد خان"),
		"vehicle": supervisor_vehicle,
		"supervisor": _driver("خالد المطيري"),
		"delivery_datetime": now_datetime(),
	})
	delivery.insert(ignore_permissions=True)
	delivery.submit()

	# 6) ملغي
	o6 = new_order(clients["سارة العنزي"], "دفع عند الاستلام", "20 ياردة")
	o6.cancel_order()


def seed_active_contract(clients, containers, employees, classifications):
	"""Active long-term contract with July deliveries → July monthly invoice."""
	last_month_start = get_first_day(add_months(today(), -1))
	contract = frappe.get_doc({
		"doctype": "Container Contract",
		"client": clients["مؤسسة البناء الحديث"],
		"contract_type": "أنقاض",
		"location": "حي العليا — شارع التحلية",
		"trip_duration_days": 7,
		"start_date": last_month_start,
		"end_date": add_months(last_month_start, 3),
		"items": [
			{"container_size": "10 ياردة", "trips_count": 30, "price": 120},
			{"container_size": "20 ياردة", "trips_count": 20, "price": 180},
		],
		"payments": [
			{"payment_date": add_days(last_month_start, 5), "amount": 2000, "tax_amount": 300,
			 "cash_box": get_cash_account()},
		],
	})
	contract.insert(ignore_permissions=True)
	contract.submit()

	driver = _driver("سالم القحطاني")
	supervisor = _driver("خالد المطيري")
	vehicle = frappe.db.get_value("Truck", {"vehicle_type": "قلاب"})

	# 4 early-July deliveries (unloaded mid-July, 2 with municipality fees)
	early = [containers[0], containers[1], containers[2], containers[12]]
	for i, container in enumerate(early):
		d = frappe.get_doc({
			"doctype": "Container Delivery",
			"contract": contract.name,
			"container": container,
			"driver": driver,
			"vehicle": vehicle,
			"supervisor": supervisor,
			"delivery_datetime": add_days(last_month_start, 2 + i),
		})
		d.insert(ignore_permissions=True)
		d.submit()
		unload = frappe.get_doc({
			"doctype": "Container Unload",
			"container": container,
			"driver": driver,
			"supervisor": supervisor,
			"unload_date": add_days(last_month_start, 9 + i),
			"unload_reason": "انتهاء المدة المحددة",
			"municipality_fee": 150 if i < 2 else 0,
			"send_whatsapp_confirmation": 0,
		})
		unload.insert(ignore_permissions=True)
		unload.submit()

	# 2 recent deliveries still with the client (due in the future)
	for i, container in enumerate([containers[3], containers[13]]):
		d = frappe.get_doc({
			"doctype": "Container Delivery",
			"contract": contract.name,
			"container": container,
			"driver": _driver("محمد عبدالرحمن"),
			"vehicle": vehicle,
			"supervisor": supervisor,
			"delivery_datetime": add_days(now_datetime(), -(2 + i)),
		})
		d.insert(ignore_permissions=True)
		d.submit()

	return contract


def seed_expired_contract(clients, classifications):
	"""Expired contract that still has remaining trips (S9 card)."""
	start = add_months(get_first_day(today()), -3)
	contract = frappe.get_doc({
		"doctype": "Container Contract",
		"client": clients["شركة الإعمار للمقاولات"],
		"contract_type": "مخلفات بناء",
		"location": "حي النرجس — مشروع الفلل",
		"trip_duration_days": 7,
		"start_date": start,
		"end_date": add_months(start, 2),
		"items": [{"container_size": "10 ياردة", "trips_count": 15, "price": 110}],
		"payments": [
			{"payment_date": add_days(start, 10), "amount": 800, "tax_amount": 120,
			 "cash_box": get_cash_account()},
		],
	})
	contract.insert(ignore_permissions=True)
	contract.submit()
	# Seed shortcut: historical consumption without generating old deliveries
	contract.db_set("consumed_trips", 9)
	contract.db_set("remaining_trips", 6)


def seed_walkin_rentals(clients, containers, classifications, employees):
	def rent(client, container, size, days_ago_from, days_until_due, driver, amount, payment="نقدي"):
		rental = frappe.get_doc({
			"doctype": "Container Rental",
			"rental_type": "نقدي" if payment == "نقدي" else "أجل قصير",
			"client": client,
			"period_from": add_days(now_datetime(), -days_ago_from),
			"period_to": add_days(now_datetime(), days_until_due),
			"classification": "أنقاض",
			"container_size": size,
			"container": container,
			"amount": amount,
			"payment_method": payment,
			"cash_box": get_cash_account() if payment == "نقدي" else None,
			"address": "الرياض",
			"driver": driver,
		})
		rental.insert(ignore_permissions=True)
		rental.submit()
		return rental

	d1 = _driver("سالم القحطاني")
	d2 = _driver("محمد عبدالرحمن")
	d3 = _driver("أحمد خان")

	# 3 current rentals (due in the future) → مؤجرة
	rent(clients["عبدالعزيز السبيعي"], containers[4], "10 ياردة", 2, 8, d1, 350)
	rent(clients["منصور الدوسري"], containers[5], "10 ياردة", 1, 9, d2, 350)
	rent(clients["سارة العنزي"], containers[16], "20 ياردة", 3, 7, d3, 500)

	# 3 backdated rentals → متأخرة (1 / 4 / 10 days → yellow / orange / red in S11)
	rent(clients["منصور الدوسري"], containers[7], "10 ياردة", 11, -1, d1, 350)
	rent(clients["عبدالعزيز السبيعي"], containers[8], "10 ياردة", 14, -4, d2, 350, payment="آجل")
	rent(clients["مصنع الخرسانة المتحدة"], containers[17], "20 ياردة", 20, -10, d3, 500, payment="آجل")

	# 1 rental then withdrawal → مسحوبة
	rent(clients["سارة العنزي"], containers[9], "10 ياردة", 5, 5, d1, 350)
	withdrawal = frappe.get_doc({
		"doctype": "Container Withdrawal",
		"container": containers[9],
		"driver": d1,
		"supervisor": _driver("خالد المطيري"),
		"withdrawal_date": today(),
		"notes": "سحب بناءً على طلب العميل دون تفريغ",
	})
	withdrawal.insert(ignore_permissions=True)
	withdrawal.submit()


def seed_manual_statuses(containers):
	# Maintenance + damaged (role-gated in the UI; direct set inside the seed)
	frappe.db.set_value("Container", containers[10], "status", "صيانة")
	frappe.db.set_value("Container", containers[11], "status", "تالفة")


def mark_one_commission_paid():
	entry = frappe.db.get_value("Driver Commission Entry", {"payout_status": "مستحقة"})
	if entry:
		frappe.db.set_value(
			"Driver Commission Entry", entry,
			{"payout_status": "مصروفة", "paid_on": today()},
		)
