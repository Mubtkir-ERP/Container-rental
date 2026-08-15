frappe.query_reports["Employee Alerts Report"] = {
	filters: [
		{
			fieldname: "employee",
			label: __("اختر الموظف"),
			fieldtype: "Link",
			options: "CR Employee",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		let html = default_formatter(value, row, column, data);
		const date_fields = ["iqama_expiry", "insurance_expiry", "driver_card_expiry"];
		if (data && date_fields.includes(column.fieldname) && value) {
			const days = frappe.datetime.get_day_diff(data[column.fieldname], frappe.datetime.get_today());
			if (days <= 30) {
				html = `<span style="color:#c0392b;font-weight:bold">${html}</span>`;
			}
		}
		if (column.fieldname === "actions" && data && data.employee) {
			const name = data.employee;
			return `
				<button class="btn btn-xs btn-default" onclick="frappe.set_route('Form','CR Employee','${name}')">${__("تعديل")}</button>
				<button class="btn btn-xs btn-default" onclick="cr_toggle_employee_status('${name}','${data.status}')">${__("تغيير الحالة")}</button>
				<button class="btn btn-xs btn-danger" onclick="cr_delete_employee('${name}')">${__("حذف")}</button>`;
		}
		return html;
	},
};

window.cr_toggle_employee_status = function (name, current) {
	const target = current === "نشط" ? "غير نشط" : "نشط";
	frappe.confirm(__("تغيير حالة الموظف إلى {0}؟", [target]), () => {
		frappe.call({
			method: "container_rental.container_rental.doctype.cr_employee.cr_employee.set_status",
			args: { employee: name, status: target },
			callback: () => frappe.query_report.refresh(),
		});
	});
};

window.cr_delete_employee = function (name) {
	frappe.confirm(__("هل أنت متأكد من حذف الموظف {0}؟", [name]), () => {
		frappe.call({
			method: "frappe.client.delete",
			args: { doctype: "CR Employee", name },
			callback: () => frappe.query_report.refresh(),
		});
	});
};
