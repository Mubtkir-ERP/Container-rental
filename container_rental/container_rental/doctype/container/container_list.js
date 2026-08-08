frappe.listview_settings["Container"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colors = {
			"متاحة": "green",
			"مؤجرة": "blue",
			"متأخرة": "red",
			"تالفة": "gray",
			"صيانة": "orange",
			"مسحوبة": "purple",
		};
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
};
