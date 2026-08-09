frappe.listview_settings["Container Order"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colors = {
			"جديد": "blue",
			"بانتظار تأكيد الحوالة": "yellow",
			"بانتظار تحديد سائق": "orange",
			"مُسنَد لسائق": "purple",
			"تم التوصيل": "green",
			"ملغي": "gray",
		};
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
};
