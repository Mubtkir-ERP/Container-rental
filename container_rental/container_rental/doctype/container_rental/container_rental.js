frappe.ui.form.on("Container Rental", {
	setup(frm) {
		frm.set_query("container", () => ({
			filters: { size: frm.doc.container_size, status: "متاحة" },
		}));
		frm.set_query("driver", () => ({
			filters: { position: "سائق", status: "نشط" },
		}));
	},

	period_from(frm) {
		frm.trigger("compute_period_to");
	},

	compute_period_to(frm) {
		if (!frm.doc.period_from) return;
		frappe.db.get_single_value("Container Rental Settings", "default_rental_days").then((days) => {
			frm.set_value(
				"period_to",
				frappe.datetime.add_days(frm.doc.period_from, days || 10)
			);
		});
	},

	container_size(frm) {
		frm.set_value("container", null);
		if (!frm.doc.container_size) return;
		// Match the reference screen: warn when no empty container of this size exists
		frappe.db
			.count("Container", { filters: { size: frm.doc.container_size, status: "متاحة" } })
			.then((count) => {
				if (!count) frappe.msgprint(__("لا يوجد حاوية فارغة بهذا الحجم"));
			});
	},

	barcode_scan(frm) {
		if (!frm.doc.barcode_scan) return;
		frappe.call({
			method: "container_rental.container_rental.doctype.container.container.resolve_barcode",
			args: { code: frm.doc.barcode_scan },
			callback(r) {
				if (r.message) {
					frappe.db.get_value("Container", r.message, ["size", "status"]).then((res) => {
						frm.set_value("container_size", res.message.size);
						frm.set_value("container", r.message);
						frm.set_value("barcode_scan", "");
					});
				}
			},
			error() {
				frm.set_value("barcode_scan", "");
			},
		});
	},
});
