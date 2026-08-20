frappe.query_reports["Truck Alerts Report"] = {
	filters: [
		{ fieldname: "vehicle", label: __("اختر شاحنة"), fieldtype: "Link", options: "Truck" },
	],

	formatter(value, row, column, data, default_formatter) {
		let html = default_formatter(value, row, column, data);
		const date_fields = ["expiry_date", "next_oil_date"];
		if (data && date_fields.includes(column.fieldname) && value) {
			const days = frappe.datetime.get_day_diff(data[column.fieldname], frappe.datetime.get_today());
			if (days <= 30) {
				html = `<span style="color:#c0392b;font-weight:bold">${html}</span>`;
			}
		}
		if (
			column.fieldname === "next_oil_km" &&
			data && data.next_oil_km && data.current_odometer_km >= data.next_oil_km
		) {
			html = `<span style="color:#c0392b;font-weight:bold">${value}</span>`;
		}
		if (column.fieldname === "actions" && data && data.vehicle_no) {
			return `<button class="btn btn-xs btn-default"
				onclick="frappe.set_route('Form','Truck','${data.vehicle_no}')">${__("تعديل")}</button>`;
		}
		return html;
	},
};
