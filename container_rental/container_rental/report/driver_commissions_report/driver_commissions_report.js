frappe.query_reports["Driver Commissions Report"] = {
	filters: [
		{
			fieldname: "driver",
			label: __("السائق"),
			fieldtype: "Link",
			options: "Employee",
			get_query: () => ({ filters: { designation: "سائق" } }),
		},
		{
			fieldname: "from_date",
			label: __("من تاريخ"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
		},
		{ fieldname: "to_date", label: __("إلى تاريخ"), fieldtype: "Date" },
		{
			fieldname: "payout_status",
			label: __("حالة الصرف"),
			fieldtype: "Select",
			options: ["", "مستحقة", "مصروفة"],
		},
	],

	onload(report) {
		report.page.add_inner_button(__("تحديد المعروض كمصروف"), () => {
			const names = (frappe.query_report.data || [])
				.filter((r) => r.entry && r.payout_status === "مستحقة")
				.map((r) => r.entry);
			if (!names.length) {
				frappe.msgprint(__("لا توجد عمولات مستحقة في النتائج الحالية"));
				return;
			}
			frappe.confirm(__("صرف {0} عمولة مستحقة؟", [names.length]), () => {
				frappe.call({
					method:
						"container_rental.container_rental.doctype.driver_commission_entry.driver_commission_entry.mark_paid",
					args: { names },
					callback(r) {
						frappe.msgprint(__("تم صرف {0} عمولة", [r.message]));
						frappe.query_report.refresh();
					},
				});
			});
		});
	},
};
