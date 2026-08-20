"""One-time migration to ERPNext HR/Selling (user request 2026-08-10):

- CR Employee rows → ERPNext Employees (documents child rows from the old
  expiry-date fields); drivers also get Sales Person records carrying the
  per-delivery commission.
- All employee references across the app are rewritten to the new names.
- Truck flat expiry/oil fields → documents + oil-change child tables.
- Cash Box values are dropped (accounts live in the chart of accounts now).
- Settings.default_supervisor: old employee → their linked User.
- Obsolete doctypes (CR Employee, Cash Box, Truck License) are deleted.

Idempotent — exits when CR Employee no longer exists."""

import frappe
from frappe.utils import today

EMPLOYEE_REFERENCES = [
	("Container", "responsible_driver"),
	("Truck", "driver"),
	("Container Order", "assigned_driver"),
	("Container Rental", "driver"),
	("Container Delivery", "driver"),
	("Container Delivery", "supervisor"),
	("Container Unload", "driver"),
	("Container Unload", "supervisor"),
	("Container Withdrawal", "driver"),
	("Container Withdrawal", "supervisor"),
	("Rental Record", "driver"),
	("Driver Commission Entry", "driver"),
]

# Old CR Employee date field → document row label
EMPLOYEE_DOCUMENTS = [
	("iqama_expiry", "الإقامة"),
	("insurance_expiry", "التأمين"),
	("driver_card_expiry", "كارت السائق"),
]

TRUCK_DOCUMENTS = [
	("insurance_expiry", "تأمين الشاحنة"),
	("registration_expiry", "الاستمارة"),
	("operating_card_expiry", "كارت التشغيل"),
]


def execute():
	if not frappe.db.exists("DocType", "CR Employee"):
		return

	from container_rental.patches.add_hr_customizations import execute as add_hr_customizations

	add_hr_customizations()

	company = frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {})
	name_map = _migrate_employees(company)
	_rewrite_references(name_map)
	_migrate_truck_children()
	_migrate_settings(name_map)
	_drop_cash_boxes()

	for doctype in ("CR Employee", "Cash Box", "Truck License"):
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, force=True, ignore_permissions=True, delete_permanently=True)

	frappe.db.commit()


def _migrate_employees(company):
	name_map = {}
	rows = frappe.db.sql("SELECT * FROM `tabCR Employee`", as_dict=True)
	for old in rows:
		existing = frappe.db.get_value("Employee", {"employee_name": old.employee_name})
		if existing:
			name_map[old.name] = existing
			continue
		doc = frappe.get_doc({
			"doctype": "Employee",
			"first_name": old.employee_name,
			"employee_name": old.employee_name,
			"company": company,
			"status": "Active" if old.status == "نشط" else "Inactive",
			"gender": "Male",
			"date_of_birth": old.date_of_birth or "1990-01-01",
			"date_of_joining": today(),
			"designation": old.position,
			"cell_number": old.mobile_no,
			"user_id": old.user,
			"cr_documents": [
				{"document_name": label, "expiry_date": old.get(field)}
				for field, label in EMPLOYEE_DOCUMENTS
				if old.get(field)
			],
		})
		doc.flags.ignore_permissions = True
		doc.flags.ignore_mandatory = True
		doc.insert()
		name_map[old.name] = doc.name

		if old.position == "سائق":
			from container_rental.container_rental import hr_utils

			sales_person = hr_utils.ensure_sales_person(doc.name)
			frappe.db.set_value(
				"Sales Person", sales_person,
				"cr_commission_per_delivery", old.commission_per_delivery or 0,
				update_modified=False,
			)
	return name_map


def _rewrite_references(name_map):
	for old_name, new_name in name_map.items():
		if old_name == new_name:
			continue
		for doctype, fieldname in EMPLOYEE_REFERENCES:
			if frappe.db.table_exists(doctype):
				frappe.db.sql(
					f"UPDATE `tab{doctype}` SET `{fieldname}` = %s WHERE `{fieldname}` = %s",
					(new_name, old_name),
				)


def _migrate_truck_children():
	"""Old flat Truck columns (still in the DB) → documents + oil child rows."""
	columns = {c.Field for c in frappe.db.sql("SHOW COLUMNS FROM `tabTruck`", as_dict=True)}

	def has(col):
		return col in columns

	trucks = frappe.db.sql("SELECT * FROM `tabTruck`", as_dict=True)
	for truck in trucks:
		doc = frappe.get_doc("Truck", truck.name)
		if doc.documents or doc.oil_changes:
			continue  # already migrated
		for field, label in TRUCK_DOCUMENTS:
			if has(field) and truck.get(field):
				doc.append("documents", {"document_name": label, "expiry_date": truck.get(field)})
		# Old standalone licenses table → document rows
		if frappe.db.table_exists("Truck License"):
			for lic in frappe.db.sql(
				"SELECT license_type, expiry_date FROM `tabTruck License` WHERE parent = %s",
				truck.name, as_dict=True,
			):
				doc.append("documents", {"document_name": lic.license_type, "expiry_date": lic.expiry_date})
		# Latest oil-change info from the maintenance log rows of type تغيير زيت
		oil_rows = frappe.db.sql(
			"""
			SELECT maintenance_date, odometer_km, cost, next_maintenance_date, next_maintenance_km, notes
			FROM `tabTruck Maintenance Log`
			WHERE parent = %s AND maintenance_type = 'تغيير زيت'
			ORDER BY maintenance_date
			""",
			truck.name, as_dict=True,
		)
		for row in oil_rows:
			doc.append("oil_changes", {
				"change_date": row.maintenance_date,
				"odometer_km": row.odometer_km,
				"cost": row.cost,
				"next_change_date": row.next_maintenance_date,
				"next_change_km": row.next_maintenance_km,
				"notes": row.notes,
			})
		if doc.documents or doc.oil_changes:
			doc.flags.ignore_permissions = True
			doc.flags.ignore_mandatory = True
			doc.save()


def _migrate_settings(name_map):
	settings = frappe.get_doc("Container Rental Settings")
	old_supervisor = settings.default_supervisor
	if old_supervisor and not frappe.db.exists("User", old_supervisor):
		new_employee = name_map.get(old_supervisor)
		user = frappe.db.get_value("Employee", new_employee, "user_id") if new_employee else None
		frappe.db.set_value(
			"Container Rental Settings", None, "default_supervisor", user, update_modified=False
		)


def _drop_cash_boxes():
	"""cash_box values point at old Cash Box names — clear anything that is not
	a real Account so the Link fields stay valid."""
	for doctype, fieldname in [
		("Container Order", "cash_box"),
		("Container Rental", "cash_box"),
		("Contract Payment", "cash_box"),
	]:
		if frappe.db.table_exists(doctype):
			frappe.db.sql(
				f"""
				UPDATE `tab{doctype}` SET `{fieldname}` = NULL
				WHERE `{fieldname}` IS NOT NULL
				  AND `{fieldname}` NOT IN (SELECT name FROM `tabAccount`)
				"""
			)
