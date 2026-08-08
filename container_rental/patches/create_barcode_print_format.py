"""Create the container barcode label print format (idempotent re-sync)."""

import frappe

FORMAT_NAME = "ملصق باركود الحاوية"

HTML = """
<div style="width: 72mm; padding: 4mm; text-align: center; font-family: Tahoma, Arial;">
	<div style="font-size: 12px; font-weight: bold;">{{ doc.branch }}</div>
	<div style="font-size: 26px; font-weight: bold; letter-spacing: 1px; margin: 2mm 0;">
		{{ doc.container_no }}
	</div>
	<div style="width: 62mm; margin: auto;">
		{% if doc.barcode %}{{ doc.barcode | safe }}{% endif %}
	</div>
	<div style="font-size: 12px; margin-top: 2mm;">
		{{ doc.size }}{% if doc.classification %} — {{ doc.classification }}{% endif %}
	</div>
</div>
"""


def execute():
	values = {
		"doc_type": "Container",
		"module": "Container Rental",
		"print_format_type": "Jinja",
		"standard": "No",
		"custom_format": 1,
		"html": HTML,
		"font_size": 12,
		"margin_top": 0,
		"margin_bottom": 0,
		"margin_left": 0,
		"margin_right": 0,
		"disabled": 0,
	}
	if frappe.db.exists("Print Format", FORMAT_NAME):
		doc = frappe.get_doc("Print Format", FORMAT_NAME)
		doc.update(values)
		doc.flags.ignore_permissions = True
		doc.save()
	else:
		frappe.get_doc({"doctype": "Print Format", "name": FORMAT_NAME, **values}).insert(
			ignore_permissions=True
		)
	frappe.db.commit()
