frappe.query_reports["Driver Commissions Report"] = {
	filters: [
		{
			fieldname: "driver",
			label: __("Driver"),
			fieldtype: "Link",
			options: "Employee",
			get_query: () => ({ filters: { designation: "سائق" } }),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
		},
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
		{
			fieldname: "payout_status",
			label: __("Payout Status"),
			fieldtype: "Select",
			options: ["", "مستحقة", "مصروفة"],
		},
	],

	onload(report) {
		report.page.add_inner_button(__("Pay Listed (Journal Entry)"), () => {
			const names = (frappe.query_report.data || [])
				.filter((r) => r.entry && r.payout_status === "مستحقة")
				.map((r) => r.entry);
			if (!names.length) {
				frappe.msgprint(__("No due commissions in the current results"));
				return;
			}
			const d = new frappe.ui.Dialog({
				title: __("Pay {0} Commissions", [names.length]),
				fields: [
					{
						fieldname: "payout_account", fieldtype: "Link", label: __("Payout Account"),
						options: "Account", reqd: 1,
						description: __("Driver's cash box or bank — credited against the commission expense account"),
						get_query: () => ({ filters: { is_group: 0, account_type: ["in", ["Cash", "Bank"]] } }),
					},
					{ fieldname: "posting_date", fieldtype: "Date", label: __("Posting Date"), default: frappe.datetime.get_today() },
				],
				primary_action_label: __("Pay and Create Entry"),
				primary_action(values) {
					d.hide();
					frappe.call({
						method: "container_rental.container_rental.doctype.driver_commission_entry.driver_commission_entry.mark_paid",
						args: { names, payout_account: values.payout_account, posting_date: values.posting_date },
						callback(r) {
							frappe.msgprint(__("Paid {0} commissions and created the journal entries", [r.message]));
							frappe.query_report.refresh();
						},
					});
				},
			});
			d.show();
		});
	},
};
