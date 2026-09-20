"""Seed the driver-first unload-request WhatsApp templates
(unload_driver_request / unload_reassign_request / unload_done).
Delegates to the original seeding patch, which only inserts missing keys."""

from container_rental.patches.seed_whatsapp_templates import execute as seed


def execute():
	seed()
