frappe.ui.form.on("Container Withdrawal", {
	setup(frm) {
		frm.set_query("container", () => ({
			filters: { status: ["in", ["Rented", "Overdue"]] },
		}));
		frm.set_query("driver", () => ({ query: "container_rental.container_rental.hr_utils.driver_query" }));
		frm.set_query("supervisor", () => ({ filters: { designation: "مشرف سواقين", status: "Active" } }));
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
