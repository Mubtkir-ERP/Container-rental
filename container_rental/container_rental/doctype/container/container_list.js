frappe.listview_settings["Container"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colors = {
			"Available": "green",
			"Rented": "blue",
			"Overdue": "red",
			"Damaged": "gray",
			"Maintenance": "orange",
			"Withdrawn": "purple",
		};
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
};
