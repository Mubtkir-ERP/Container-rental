"""Sync the Container Rental workspace from the app's JSON definition.

Idempotent — re-applies the layout on every migrate.
"""

import json
import os

import frappe


def execute():
	path = frappe.get_app_path(
		"container_rental", "container_rental", "workspace", "تأجير_الحاويات", "تأجير_الحاويات.json"
	)
	if not os.path.exists(path):
		return
	with open(path, encoding="utf-8") as fh:
		data = json.load(fh)

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
