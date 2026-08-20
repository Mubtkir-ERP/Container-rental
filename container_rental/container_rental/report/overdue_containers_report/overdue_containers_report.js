frappe.query_reports["Overdue Containers Report"] = {
	filters: [
		{
			fieldname: "classification",
			label: __("التصنيف"),
			fieldtype: "Link",
			options: "Container Classification",
		},
		{
			fieldname: "container_size",
			label: __("حجم الحاوية"),
			fieldtype: "Link",
			options: "Container Size",
		},
		{ fieldname: "branch", label: __("الفرع"), fieldtype: "Link", options: "Rental Branch" },
		{
			fieldname: "driver",
			label: __("السائق"),
			fieldtype: "Link",
			options: "Employee",
			get_query: () => ({ filters: { designation: "سائق" } }),
		},
		{
			fieldname: "delay_range",
			label: __("نطاق مدة التأخير"),
			fieldtype: "Select",
			options: ["", "0-2", "3-7", "7+"],
		},
	],

	formatter(value, row, column, data, default_formatter) {
		let html = default_formatter(value, row, column, data);
		if (data && data.severity) {
			const colors = { yellow: "#b58a00", orange: "#d35400", red: "#c0392b" };
			if (column.fieldname === "overdue_text" || column.fieldname === "severity_label") {
				html = `<span style="color:${colors[data.severity]};font-weight:bold">${value || ""}</span>`;
			}
		}
		return html;
	},
};
