frappe.query_reports["Truck Alerts Report"] = {
	filters: [
		{ fieldname: "vehicle", label: __("اختر شاحنة"), fieldtype: "Link", options: "Truck" },
	],

	formatter(value, row, column, data, default_formatter) {
		let html = default_formatter(value, row, column, data);
		const date_fields = [
			"next_oil_change_date",
			"registration_expiry",
			"insurance_expiry",
			"operating_card_expiry",
		];
		if (data && date_fields.includes(column.fieldname) && value) {
			const days = frappe.datetime.get_day_diff(data[column.fieldname], frappe.datetime.get_today());
			if (days <= 30) {
				html = `<span style="color:#c0392b;font-weight:bold">${html}</span>`;
			}
		}
		if (column.fieldname === "actions" && data && data.vehicle_no) {
			const name = data.vehicle_no;
			return `
				<button class="btn btn-xs btn-default" onclick="frappe.set_route('Form','Truck','${name}')">${__("تعديل")}</button>
				<button class="btn btn-xs btn-danger" onclick="cr_delete_truck('${name}')">${__("حذف")}</button>`;
		}
		return html;
	},
};

window.cr_delete_truck = function (name) {
	frappe.confirm(__("هل أنت متأكد من حذف الشاحنة {0}؟", [name]), () => {
		frappe.call({
			method: "frappe.client.delete",
			args: { doctype: "Truck", name },
			callback: () => frappe.query_report.refresh(),
		});
	});
};
