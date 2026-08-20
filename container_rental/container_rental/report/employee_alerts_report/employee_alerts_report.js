frappe.query_reports["Employee Alerts Report"] = {
	filters: [
		{
			fieldname: "employee",
			label: __("اختر الموظف"),
			fieldtype: "Link",
			options: "Employee",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		let html = default_formatter(value, row, column, data);
		if (data && column.fieldname === "expiry_date" && value) {
			const days = frappe.datetime.get_day_diff(data.expiry_date, frappe.datetime.get_today());
			if (days <= 30) {
				html = `<span style="color:#c0392b;font-weight:bold">${html}</span>`;
			}
		}
		if (column.fieldname === "attachment" && data && data.attachment) {
			return `<a href="${data.attachment}" target="_blank">${__("عرض الملف")}</a>`;
		}
		if (column.fieldname === "actions" && data && data.employee) {
			return `<button class="btn btn-xs btn-default"
				onclick="frappe.set_route('Form','Employee','${data.employee}')">${__("تعديل")}</button>`;
		}
		return html;
	},
};
