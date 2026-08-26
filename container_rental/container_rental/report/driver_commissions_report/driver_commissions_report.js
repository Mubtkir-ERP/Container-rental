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
		report.page.add_inner_button(__("صرف المعروض (قيد محاسبي)"), () => {
			const names = (frappe.query_report.data || [])
				.filter((r) => r.entry && r.payout_status === "مستحقة")
				.map((r) => r.entry);
			if (!names.length) {
				frappe.msgprint(__("لا توجد عمولات مستحقة في النتائج الحالية"));
				return;
			}
			const d = new frappe.ui.Dialog({
				title: __("صرف {0} عمولة", [names.length]),
				fields: [
					{
						fieldname: "payout_account", fieldtype: "Link", label: __("حساب الصرف"),
						options: "Account", reqd: 1,
						description: __("صندوق السائق أو البنك — يُقيَّد عليه المبلغ مقابل حساب مصروف العمولات"),
						get_query: () => ({ filters: { is_group: 0, account_type: ["in", ["Cash", "Bank"]] } }),
					},
					{ fieldname: "posting_date", fieldtype: "Date", label: __("تاريخ القيد"), default: frappe.datetime.get_today() },
				],
				primary_action_label: __("صرف وإنشاء القيد"),
				primary_action(values) {
					d.hide();
					frappe.call({
						method: "container_rental.container_rental.doctype.driver_commission_entry.driver_commission_entry.mark_paid",
						args: { names, payout_account: values.payout_account, posting_date: values.posting_date },
						callback(r) {
							frappe.msgprint(__("تم صرف {0} عمولة وإنشاء القيود المحاسبية", [r.message]));
							frappe.query_report.refresh();
						},
					});
				},
			});
			d.show();
		});
	},
};
