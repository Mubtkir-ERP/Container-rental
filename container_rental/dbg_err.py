import frappe


def run():
	rows = frappe.get_all("Error Log", fields=["method", "error"], order_by="creation desc", limit=2)
	for r in rows:
		print("=== ", r.method)
		print(r.error[:1200])
