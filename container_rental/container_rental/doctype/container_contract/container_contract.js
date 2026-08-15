frappe.ui.form.on("Container Contract", {
	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("تجديد التعاقد"), () => {
				const d = new frappe.ui.Dialog({
					title: __("تجديد التعاقد"),
					fields: [
						{
							fieldname: "new_end_date",
							fieldtype: "Date",
							label: __("تاريخ الانتهاء الجديد"),
							reqd: 1,
						},
					],
					primary_action_label: __("تجديد"),
					primary_action(values) {
						d.hide();
						frm.call("renew_contract", { new_end_date: values.new_end_date }).then(() =>
							frm.reload_doc()
						);
					},
				});
				d.show();
			}).addClass("btn-primary");

			frm.add_custom_button(__("تسجيل توصيل من العقد"), () => {
				frappe.new_doc("Container Delivery", {
					contract: frm.doc.name,
					client: frm.doc.client,
				});
			});
		}
	},
});

frappe.ui.form.on("Contract Item", {
	trips_count(frm, cdt, cdn) {
		compute_item(frm, cdt, cdn);
	},
	price(frm, cdt, cdn) {
		compute_item(frm, cdt, cdn);
	},
	items_remove(frm) {
		compute_contract_value(frm);
	},
});

function compute_item(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "total", (row.trips_count || 0) * (row.price || 0));
	compute_contract_value(frm);
}

function compute_contract_value(frm) {
	const total = (frm.doc.items || []).reduce((s, r) => s + (r.total || 0), 0);
	frm.set_value("contract_value", total);
}
