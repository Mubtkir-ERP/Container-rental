frappe.query_reports["Contract Report"] = {
	filters: [
		{
			fieldname: "client",
			label: __("Client Name"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "contract",
			label: __("Contract No"),
			fieldtype: "Link",
			options: "Container Contract",
		},
		{
			fieldname: "status",
			label: __("Contract Status"),
			fieldtype: "Select",
			options: ["", "Active", "Expire"],
			default: "الكل",
		},
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
	],

	formatter(value, row, column, data, default_formatter) {
		if (column.fieldname === "actions" && data && data.contract_no) {
			const name = data.contract_no;
			return `
				<button class="btn btn-xs btn-default" onclick="frappe.set_route('print', 'Container Contract', '${name}')">${__("Print")}</button>
				<button class="btn btn-xs btn-default" onclick="frappe.set_route('Form', 'Container Contract', '${name}')">${__("Edit")}</button>
				<button class="btn btn-xs btn-primary" onclick="container_rental_renew_contract('${name}')">${__("Renew")}</button>`;
		}
		if (column.fieldname === "contract_status" && data) {
			const color = value === "Active" ? "green" : "red";
			return `<span class="indicator-pill ${color}">${value}</span>`;
		}
		return default_formatter(value, row, column, data);
	},
};

window.container_rental_renew_contract = function (contract) {
	const d = new frappe.ui.Dialog({
		title: __("Renew Contract {0}", [contract]),
		fields: [
			{ fieldname: "new_end_date", fieldtype: "Date", label: __("New End Date"), reqd: 1 },
		],
		primary_action_label: __("Renew"),
		primary_action(values) {
			d.hide();
			frappe.call({
				method: "run_doc_method",
				args: {
					dt: "Container Contract",
					dn: contract,
					method: "renew_contract",
					args: { new_end_date: values.new_end_date },
				},
				callback: () => frappe.query_report.refresh(),
			});
		},
	});
	d.show();
};
