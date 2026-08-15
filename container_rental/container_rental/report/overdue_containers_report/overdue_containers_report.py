# S11 export twin — shares the exact query of the overdue-containers page.
from frappe import _

from container_rental.api import get_overdue_data


def execute(filters=None):
	return get_columns(), get_overdue_data(filters or {})


def get_columns():
	return [
		{"fieldname": "container", "label": _("رقم الحاوية"), "fieldtype": "Link", "options": "Container", "width": 110},
		{"fieldname": "client_name", "label": _("العميل"), "fieldtype": "Data", "width": 150},
		{"fieldname": "mobile_no", "label": _("رقم الجوال"), "fieldtype": "Data", "width": 110},
		{"fieldname": "container_size", "label": _("الحجم"), "fieldtype": "Data", "width": 90},
		{"fieldname": "classification", "label": _("التصنيف"), "fieldtype": "Data", "width": 100},
		{"fieldname": "branch", "label": _("الفرع"), "fieldtype": "Data", "width": 110},
		{"fieldname": "address", "label": _("العنوان / الموقع"), "fieldtype": "Data", "width": 180},
		{"fieldname": "driver_name", "label": _("السائق"), "fieldtype": "Data", "width": 130},
		{"fieldname": "delivered_on", "label": _("تاريخ التوصيل"), "fieldtype": "Datetime", "width": 140},
		{"fieldname": "due_on", "label": _("تاريخ الاستحقاق"), "fieldtype": "Datetime", "width": 140},
		{"fieldname": "overdue_text", "label": _("مدة التأخير"), "fieldtype": "Data", "width": 140},
		{"fieldname": "severity_label", "label": _("درجة الخطورة"), "fieldtype": "Data", "width": 110},
		{"fieldname": "last_whatsapp_message", "label": _("آخر رسالة واتساب"), "fieldtype": "Data", "width": 130},
		{"fieldname": "last_whatsapp_on", "label": _("تاريخ آخر رسالة"), "fieldtype": "Datetime", "width": 140},
	]
