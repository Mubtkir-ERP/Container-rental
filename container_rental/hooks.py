app_name = "container_rental"
app_title = "Container Rental"
app_publisher = "Almubtkir"
app_description = "Container Rental Management System"
app_email = "almubtkir@gmail.com"
app_license = "mit"
app_version = "0.2.0"

required_apps = ["erpnext"]

doc_events = {}

fixtures = [
	{
		"doctype": "Custom Field",
		"filters": [["module", "=", "Container Rental"]],
	},
	{
		"doctype": "Role",
		"filters": [["name", "in", [
			"Customer Service",
			"Transfer Follow-up",
			"Driver Supervisor",
			"Container Manager",
		]]],
	},
]
