frappe.ui.form.on("Container", {
	setup(frm) {
		frm.set_query("responsible_driver", () => ({
			filters: { designation: "سائق", status: "Active" },
		}));
	},

	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("تغيير الحالة"), () => {
			const d = new frappe.ui.Dialog({
				title: __("تغيير حالة الحاوية"),
				fields: [
					{
						fieldname: "new_status",
						fieldtype: "Select",
						label: __("الحالة الجديدة"),
						options: ["متاحة", "تالفة", "صيانة", "مسحوبة"],
						reqd: 1,
					},
				],
				primary_action_label: __("تغيير"),
				primary_action(values) {
					frappe.call({
						method: "container_rental.container_rental.doctype.container.container.change_status",
						args: { container: frm.doc.name, new_status: values.new_status },
						callback: () => {
							d.hide();
							frm.reload_doc();
						},
					});
				},
			});
			d.show();
		});

		if (frm.doc.status === "مسحوبة") {
			frm.add_custom_button(__("إعادة للمتاح بعد الفحص"), () => {
				frappe.call({
					method: "container_rental.container_rental.doctype.container.container.release_to_available",
					args: { container: frm.doc.name },
					callback: () => frm.reload_doc(),
				});
			});
		}

		frm.add_custom_button(__("طباعة ملصق الباركود"), () => {
			frappe.set_route("print", "Container", frm.doc.name);
		});
	},
});
