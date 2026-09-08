// Shared extension dialog: any days count, billed as a NEW closed order
window.container_rental_extend_dialog = window.container_rental_extend_dialog || function (rental_record, on_done) {
	const d = new frappe.ui.Dialog({
		title: __("Extend Container Rental"),
		fields: [
			{
				fieldname: "days", fieldtype: "Int", label: __("Extension Days"),
				reqd: 1, default: 10,
				description: __("The extension is billed as a new order"),
			},
			{ fieldname: "rental_value", fieldtype: "Currency", label: __("Extension Value"), reqd: 1 },
			{
				fieldname: "payment_method", fieldtype: "Link", label: __("Payment Method"),
				options: "Mode of Payment",
			},
		],
		primary_action_label: __("Extend"),
		primary_action(values) {
			d.hide();
			frappe.call({
				method: "container_rental.api.extend_rental",
				args: {
					rental_record: rental_record,
					days: values.days,
					rental_value: values.rental_value,
					payment_method: values.payment_method,
				},
				callback(r) {
					const m = r.message || {};
					frappe.show_alert({
						message: __("Extended — order {0} created", [m.order]),
						indicator: "green",
					});
					if (on_done) on_done(m);
				},
			});
		},
	});
	d.show();
};

frappe.ui.form.on("Container Unload", {
	refresh(frm) {
		frm.trigger("render_extend_button");
	},

	render_extend_button(frm) {
		frm.remove_custom_button(__("Extend"));
		if (frm.doc.docstatus === 0 && frm.doc.rental_record) {
			frm.add_custom_button(__("Extend"), () => {
				window.container_rental_extend_dialog(frm.doc.rental_record, () => {
					frappe.msgprint(__("Extended — no unload needed now, you can close this screen"));
				});
			});
		}
	},

	setup(frm) {
		frm.set_query("container", () => ({
			filters: { status: ["in", ["مؤجرة", "متأخرة"]] },
		}));
		frm.set_query("driver", () => ({ filters: { designation: "سائق", status: "Active" } }));
		frm.set_query("supervisor", () => ({ filters: { designation: "مشرف سواقين", status: "Active" } }));
	},

	container(frm) {
		if (!frm.doc.container) return;
		// Show the open rental's client/contract context to the operator
		frappe.db
			.get_list("Rental Record", {
				filters: { container: frm.doc.container, status: ["in", ["مؤجرة", "متأخرة"]] },
				fields: ["name", "client", "delivered_on", "due_on", "contract"],
				limit: 1,
			})
			.then((rows) => {
				if (!rows.length) {
					frappe.msgprint(__("No open rental record for this container"));
					return;
				}
				const r = rows[0];
				frm.set_value("rental_record", r.name);
				frm.trigger("render_extend_button");
				frappe.db.get_value("Customer", r.client, "customer_name").then((res) => {
					frm.dashboard.set_headline(
						__("Client: {0} — Delivered: {1} — Due: {2}", [
							res.message.customer_name,
							frappe.datetime.str_to_user(r.delivered_on),
							r.due_on ? frappe.datetime.str_to_user(r.due_on) : "-",
						])
					);
				});
			});
	},

	barcode_scan(frm) {
		if (!frm.doc.barcode_scan) return;
		frappe.call({
			method: "container_rental.container_rental.doctype.container.container.resolve_barcode",
			args: { code: frm.doc.barcode_scan },
			callback(r) {
				if (r.message) {
					frm.set_value("container", r.message);
					frm.set_value("barcode_scan", "");
				}
			},
			error() {
				frm.set_value("barcode_scan", "");
			},
		});
	},
});
