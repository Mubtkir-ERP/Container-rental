app_name = "container_rental"
app_title = "Container Rental"
app_publisher = "Almubtkir"
app_description = "Container Rental Management System"
app_email = "almubtkir@gmail.com"
app_license = "mit"
app_version = "1.0.0"

required_apps = ["erpnext", "frappe_whatsapp"]

# NOTE: All submittable doctypes in this app implement `on_submit` / `on_cancel`
# as controller methods, which Frappe invokes automatically. We deliberately do
# NOT register them again via `doc_events` — doing so would run every side
# effect (container status changes, commission entries, trip decrements) twice.
doc_events = {}

scheduler_events = {
	"cron": {
		# Flag rentals past their due datetime (and their containers) as overdue
		"0 * * * *": [
			"container_rental.container_rental.tasks.mark_overdue_rentals",
		],
		# WhatsApp reminders + employee/truck document expiry alerts
		"0 7 * * *": [
			"container_rental.container_rental.tasks.daily_alerts",
		],
		# Monthly contract invoices from actual deliveries of the previous month
		"0 2 1 * *": [
			"container_rental.container_rental.tasks.generate_monthly_invoices",
		],
	}
}

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
			"Driver",
			"Container Manager",
		]]],
	},
]
