import frappe
from frappe.model.document import Document


class RentalRecord(Document):
	pass


def create_rental_record(
	container,
	client,
	delivered_on,
	due_on,
	source_doctype,
	source_name,
	driver=None,
	contract=None,
	address=None,
	rental_value=0,
	payment_method=None,
):
	"""Create the internal per-container rental ledger row (controllers only)."""
	container_doc = frappe.db.get_value(
		"Container", container, ["size", "classification", "branch"], as_dict=True
	)
	mobile_no = frappe.db.get_value("Customer", client, "cr_mobile_no")

	record = frappe.get_doc({
		"doctype": "Rental Record",
		"container": container,
		"container_size": container_doc.size,
		"classification": container_doc.classification,
		"branch": container_doc.branch,
		"client": client,
		"mobile_no": mobile_no,
		"address": address,
		"driver": driver,
		"source_doctype": source_doctype,
		"source_name": source_name,
		"contract": contract,
		"delivered_on": delivered_on,
		"due_on": due_on,
		"rental_value": rental_value,
		"payment_method": payment_method,
		"status": "مؤجرة",
	})
	record.flags.ignore_permissions = True
	record.insert()
	return record


def get_open_record(container):
	"""Return the name of the open (rented/overdue) rental record for a container."""
	return frappe.db.get_value(
		"Rental Record",
		{"container": container, "status": ("in", ["مؤجرة", "متأخرة"])},
		order_by="delivered_on desc",
	)


def get_maps_link(record):
	"""Google Maps link of the delivery location (lives on the source order)."""
	if record.source_doctype == "Container Order" and record.source_name:
		return frappe.db.get_value("Container Order", record.source_name, "google_maps_link") or ""
	return ""
