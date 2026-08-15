frappe.query_reports["Contract Report"] = {
	filters: [
		{
			fieldname: "client",
			label: __("اسم العميل"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "contract",
			label: __("رقم العقد"),
			fieldtype: "Link",
			options: "Container Contract",
		},
		{
			fieldname: "status",
			label: __("حالة العقد"),
			fieldtype: "Select",
			options: ["الكل", "ساري", "منتهٍ"],
			default: "الكل",
		},
		{ fieldname: "from_date", label: __("من تاريخ"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("إلى تاريخ"), fieldtype: "Date" },
	],

	formatter(value, row, column, data, default_formatter) {
		if (column.fieldname === "actions" && data && data.contract_no) {
			const name = data.contract_no;
			return `
				<button class="btn btn-xs btn-default" onclick="frappe.set_route('print', 'Container Contract', '${name}')">${__("طباعة")}</button>
				<button class="btn btn-xs btn-default" onclick="frappe.set_route('Form', 'Container Contract', '${name}')">${__("تعديل")}</button>
				<button class="btn btn-xs btn-primary" onclick="container_rental_renew_contract('${name}')">${__("تجديد")}</button>`;
		}
		if (column.fieldname === "contract_status" && data) {
			const color = value === "ساري" ? "green" : "red";
			return `<span class="indicator-pill ${color}">${value}</span>`;
		}
		return default_formatter(value, row, column, data);
	},
};

window.container_rental_renew_contract = function (contract) {
	const d = new frappe.ui.Dialog({
		title: __("تجديد التعاقد {0}", [contract]),
		fields: [
			{ fieldname: "new_end_date", fieldtype: "Date", label: __("تاريخ الانتهاء الجديد"), reqd: 1 },
		],
		primary_action_label: __("تجديد"),
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
