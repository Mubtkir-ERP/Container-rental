frappe.ui.form.on("Container Contract", {
	start_date(frm) {
		compute_end_date(frm);
	},
	contract_duration(frm) {
		compute_end_date(frm);
	},
	duration_unit(frm) {
		compute_end_date(frm);
	},
	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Renew Contract"), () => {
				const d = new frappe.ui.Dialog({
					title: __("Renew Contract"),
					fields: [
						{
							fieldname: "new_end_date",
							fieldtype: "Date",
							label: __("New End Date"),
							reqd: 1,
						},
					],
					primary_action_label: __("Renew"),
					primary_action(values) {
						d.hide();
						// dt/dn form — see the note in container_order.js about frm.call
						frappe
							.call({
								method: "run_doc_method",
								args: {
									dt: frm.doctype,
									dn: frm.docname,
									method: "renew_contract",
									args: { new_end_date: values.new_end_date },
								},
							})
							.then(() => frm.reload_doc());
					},
				});
				d.show();
			}).addClass("btn-primary");

			frm.add_custom_button(__("Record Delivery From Contract"), () => {
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

function compute_end_date(frm) {
	if (!frm.doc.start_date || !frm.doc.contract_duration) {
		return;
	}
	const duration = cint(frm.doc.contract_duration);
	if (duration <= 0) {
		return;
	}
	const unit = frm.doc.duration_unit || "Months";
	let end_date;
	if (unit === "Days") {
		end_date = frappe.datetime.add_days(frm.doc.start_date, duration);
	} else if (unit === "Years") {
		end_date = frappe.datetime.add_months(frm.doc.start_date, duration * 12);
	} else {
		end_date = frappe.datetime.add_months(frm.doc.start_date, duration);
	}
	frm.set_value("end_date", end_date);
}
