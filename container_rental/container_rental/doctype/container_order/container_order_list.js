frappe.listview_settings["Container Order"] = {
	onload(listview) {
		// Drivers land on "my assigned orders" — nothing else is relevant to them
		const office = ["System Manager", "Container Manager", "Customer Service", "Driver Supervisor", "Transfer Follow-up"];
		const driver_only = frappe.user.has_role("Driver") && !office.some((r) => frappe.user.has_role(r));
		if (!driver_only) return;
		frappe.xcall("container_rental.api.get_current_employee").then((employee) => {
			listview.filter_area.clear();
			listview.filter_area.add([["Container Order", "status", "=", "مُسنَد لسائق"]]);
			if (employee) listview.filter_area.add([["Container Order", "assigned_driver", "=", employee]]);
			listview.page.set_title(__("طلباتي المُسندة"));
		});
	},
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
