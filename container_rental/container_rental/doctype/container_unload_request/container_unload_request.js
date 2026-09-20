frappe.ui.form.on("Container Unload Request", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.trigger("render_maps_button");
		if (frm.events.is_driver_only()) {
			frm.trigger("render_driver_view");
		} else {
			frm.trigger("render_office_buttons");
		}
	},

	is_driver_only() {
		const office = ["System Manager", "Container Manager", "Customer Service",
			"Driver Supervisor", "Transfer Follow-up"];
		return frappe.user.has_role("Driver") && !office.some((r) => frappe.user.has_role(r));
	},

	render_maps_button(frm) {
		if (frm.doc.google_maps_link) {
			frm.add_custom_button(__("Open Location"), () => {
				window.open(frm.doc.google_maps_link, "_blank");
			});
		}
	},

	// dt/dn form — see the note in container_order.js about frm.call
	run(frm, method, args = {}) {
		return frappe.call({
			method: "run_doc_method",
			args: { dt: frm.doctype, dn: frm.docname, method: method, args: args },
		});
	},

	render_driver_view(frm) {
		// The driver opens the WhatsApp link and only confirms (or declines)
		frm.disable_save();
		if (frm.doc.status !== "بانتظار تأكيد السائق") return;
		frm.page.set_primary_action(__("Confirm Unload"), () => {
			frm.events.run(frm, "driver_confirm").then(() => {
				frappe.show_alert({ message: __("Unload confirmed, thank you"), indicator: "green" });
				frappe.set_route("List", "Container Unload Request");
			});
		});
		frm.add_custom_button(__("Decline"), () => {
			frappe.confirm(__("Decline this unload request? The supervisor will assign another driver."), () => {
				frm.events.run(frm, "driver_decline").then(() => {
					frappe.show_alert({ message: __("The supervisor was notified"), indicator: "orange" });
					frappe.set_route("List", "Container Unload Request");
				});
			});
		});
	},

	render_office_buttons(frm) {
		const active = ["بانتظار تأكيد السائق", "بانتظار إسناد سائق"].includes(frm.doc.status);
		if (!active) return;
		frm.add_custom_button(__("Assign Driver"), () => {
			const d = new frappe.ui.Dialog({
				title: __("Assign Driver to Unload Request"),
				fields: [
					{
						fieldname: "driver",
						fieldtype: "Link",
						label: __("Driver"),
						options: "Employee",
						reqd: 1,
						get_query: () => ({ filters: { designation: "سائق", status: "Active" } }),
					},
				],
				primary_action_label: __("Assign"),
				primary_action(values) {
					d.hide();
					frm.events.run(frm, "assign_driver", { driver: values.driver }).then(() => frm.reload_doc());
				},
			});
			d.show();
		}).addClass("btn-primary");
		frm.add_custom_button(__("Confirm Unload"), () => {
			frm.events.run(frm, "driver_confirm").then(() => frm.reload_doc());
		});
		frm.add_custom_button(__("Cancel Request"), () => {
			frappe.confirm(__("Cancel this unload request?"), () => {
				frm.events.run(frm, "cancel_request").then(() => frm.reload_doc());
			});
		});
	},
});
