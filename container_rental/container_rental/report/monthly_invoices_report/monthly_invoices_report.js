frappe.query_reports["Monthly Invoices Report"] = {
	filters: [
		{ fieldname: "contract", label: __("Contract"), fieldtype: "Link", options: "Container Contract" },
		{ fieldname: "client", label: __("Client"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "month_key", label: __("Month (YYYY-MM)"), fieldtype: "Data" },
		{
			fieldname: "payment_status",
			label: __("Payment Status"),
			fieldtype: "Select",
			options: ["", "غير مسددة", "مسددة جزئيًا", "مسددة"],
		},
	],

	onload(report) {
		report.page.add_inner_button(__("Generate Last Month Invoices"), () => {
			frappe.confirm(__("Generate last month's contract invoices?"), () => {
				frappe.call({
					method: "container_rental.container_rental.tasks.generate_monthly_invoices",
					callback(r) {
						const created = r.message || [];
						frappe.msgprint(
							created.length
								? __("Generated {0} invoices: {1}", [created.length, created.join("، ")])
								: __("No new invoices to generate")
						);
						frappe.query_report.refresh();
					},
				});
			});
		});
	},
};
