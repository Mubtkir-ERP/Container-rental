# S11 export twin — shares the exact query of the overdue-containers page.
from frappe import _

from container_rental.api import get_overdue_data


def execute(filters=None):
	return get_columns(), get_overdue_data(filters or {})


def get_columns():
	return [
		{"fieldname": "container", "label": _("Container No"), "fieldtype": "Link", "options": "Container", "width": 110},
		{"fieldname": "client_name", "label": _("Client"), "fieldtype": "Data", "width": 150},
		{"fieldname": "mobile_no", "label": _("Mobile No"), "fieldtype": "Data", "width": 110},
		{"fieldname": "container_size", "label": _("Size"), "fieldtype": "Data", "width": 90},
		{"fieldname": "classification", "label": _("Classification"), "fieldtype": "Data", "width": 100},
		{"fieldname": "branch", "label": _("Branch"), "fieldtype": "Data", "width": 110},
		{"fieldname": "address", "label": _("Address / Location"), "fieldtype": "Data", "width": 180},
		{"fieldname": "driver_name", "label": _("Driver"), "fieldtype": "Data", "width": 130},
		{"fieldname": "delivered_on", "label": _("Delivery Date"), "fieldtype": "Datetime", "width": 140},
		{"fieldname": "due_on", "label": _("Due Date"), "fieldtype": "Datetime", "width": 140},
		{"fieldname": "overdue_text", "label": _("Overdue Duration"), "fieldtype": "Data", "width": 140},
		{"fieldname": "severity_label", "label": _("Severity"), "fieldtype": "Data", "width": 110},
		{"fieldname": "last_whatsapp_message", "label": _("Last WhatsApp Message"), "fieldtype": "Data", "width": 130},
		{"fieldname": "last_whatsapp_on", "label": _("Last Message Date"), "fieldtype": "Datetime", "width": 140},
	]
