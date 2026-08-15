"""One-time migration: Client rows → ERPNext Customers, rewrite all references,
then drop the obsolete Client doctype. Idempotent — exits when Client is gone."""

import frappe

# (doctype, fieldname) pairs whose values point at the old Client names
CLIENT_REFERENCES = [
	("Container Order", "client"),
	("Container Contract", "client"),
	("Container Rental", "client"),
	("Rental Record", "client"),
	("Container Delivery", "client"),
	("Contract Monthly Invoice", "client"),
	("Driver Commission Entry", "client"),
]

TYPE_MAP = {"فرد": "Individual", "شركة": "Company"}


def execute():
	if not frappe.db.exists("DocType", "Client"):
		return

	from container_rental.patches.add_customer_fields import execute as add_customer_fields

	add_customer_fields()

	name_map = {}
	for client in frappe.get_all(
		"Client",
		fields=["name", "client_name", "client_type", "mobile_no", "account_type", "current_balance", "notes"],
	):
		customer = frappe.db.get_value("Customer", {"customer_name": client.client_name})
		if not customer:
			doc = frappe.get_doc({
				"doctype": "Customer",
				"customer_name": client.client_name,
				"customer_type": TYPE_MAP.get(client.client_type, "Individual"),
				"cr_mobile_no": client.mobile_no,
				"cr_account_type": client.account_type,
				"cr_rental_balance": client.current_balance,
				"cr_delivery_locations": [
					{
						"address_title": row.address_title,
						"address": row.address,
						"is_default": row.is_default,
					}
					for row in frappe.get_all(
						"Client Address",
						filters={"parent": client.name, "parenttype": "Client"},
						fields=["address_title", "address", "is_default"],
						order_by="idx",
					)
				],
			})
			doc.flags.ignore_permissions = True
			doc.flags.ignore_mandatory = True
			doc.insert()
			customer = doc.name
		name_map[client.name] = customer

	for old_name, new_name in name_map.items():
		if old_name == new_name:
			continue
		for doctype, fieldname in CLIENT_REFERENCES:
			if frappe.db.table_exists(doctype):
				frappe.db.sql(
					f"UPDATE `tab{doctype}` SET `{fieldname}` = %s WHERE `{fieldname}` = %s",
					(new_name, old_name),
				)

	frappe.delete_doc("DocType", "Client", force=True, ignore_permissions=True, delete_permanently=True)
	frappe.db.commit()
