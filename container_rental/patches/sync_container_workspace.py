"""Sync the Container Rental workspace from the app's JSON definition and drop
the older Arabic-named workspace. Idempotent — re-applies on every migrate."""

import json
import os

import frappe

OLD_WORKSPACE_NAMES = ["تأجير الحاويات", "Container Rental"]


def execute():
	path = frappe.get_app_path(
		"container_rental", "container_rental", "workspace", "container_rental_system", "container_rental_system.json"
	)
	if not os.path.exists(path):
		return
	with open(path, encoding="utf-8") as fh:
		data = json.load(fh)

	for old in OLD_WORKSPACE_NAMES:
		if frappe.db.exists("Workspace", old):
			frappe.delete_doc("Workspace", old, force=True, ignore_permissions=True)

	name = data["name"]
	if frappe.db.exists("Workspace", name):
		ws = frappe.get_doc("Workspace", name)
	else:
		ws = frappe.new_doc("Workspace")
		ws.name = name

	ws.title = data.get("title")
	ws.label = data.get("label")
	ws.icon = data.get("icon")
	ws.indicator_color = data.get("indicator_color")
	ws.module = data.get("module")
	ws.public = 1
	ws.content = data.get("content")

	ws.set("links", [])
	for row in data.get("links", []):
		ws.append("links", row)
	ws.set("shortcuts", [])
	for row in data.get("shortcuts", []):
		ws.append("shortcuts", row)
	ws.set("custom_blocks", [])
	ws.set("charts", [])
	ws.set("number_cards", [])

	ws.flags.ignore_permissions = True
	ws.flags.ignore_links = True
	ws.flags.ignore_mandatory = True
	ws.save()
	frappe.db.commit()
