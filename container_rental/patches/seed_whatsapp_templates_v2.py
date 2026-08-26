"""Re-run the template seed so newly added event templates
(e.g. supervisor_new_order) get their editable WhatsApp Templates row."""

from container_rental.patches.seed_whatsapp_templates import execute as seed


def execute():
	seed()
