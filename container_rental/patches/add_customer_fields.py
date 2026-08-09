"""Custom fields on ERPNext Customer for the container-rental domain
(document section 2.4). Tagged with module "Container Rental" so the fixture
filter in hooks.py exports them. Idempotent via create_custom_fields."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CUSTOM_FIELDS = {
	"Customer": [
		{
			"fieldname": "cr_rental_section",
			"fieldtype": "Section Break",
			"label": "بيانات تأجير الحاويات",
			"insert_after": "customer_type",
			"module": "Container Rental",
		},
		{
			"fieldname": "cr_mobile_no",
			"fieldtype": "Data",
			"label": "رقم الجوال (واتساب)",
			"options": "Phone",
			"insert_after": "cr_rental_section",
			"allow_in_quick_entry": 1,
			"in_list_view": 1,
			"in_standard_filter": 1,
			"module": "Container Rental",
			"description": "يُستخدم لإرسال رسائل واتساب",
		},
		{
			"fieldname": "cr_account_type",
			"fieldtype": "Select",
			"label": "نوع الحساب",
			"options": "نقدي\nآجل",
			"default": "نقدي",
			"insert_after": "cr_mobile_no",
			"allow_in_quick_entry": 1,
			"in_standard_filter": 1,
			"module": "Container Rental",
		},
		{
			"fieldname": "cr_rental_balance",
			"fieldtype": "Currency",
			"label": "الرصيد الحالي (تأجير الحاويات)",
			"read_only": 1,
			"insert_after": "cr_account_type",
			"module": "Container Rental",
			"description": "إجمالي المستحق على العميل من عمليات التأجير",
		},
		{
			"fieldname": "cr_locations_section",
			"fieldtype": "Section Break",
			"label": "مواقع التسليم",
			"insert_after": "cr_rental_balance",
			"collapsible": 1,
			"module": "Container Rental",
		},
		{
			"fieldname": "cr_delivery_locations",
			"fieldtype": "Table",
			"label": "العناوين / المواقع",
			"options": "Client Address",
			"insert_after": "cr_locations_section",
			"module": "Container Rental",
		},
	]
}


def execute():
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
