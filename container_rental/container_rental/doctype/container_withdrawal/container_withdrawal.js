frappe.ui.form.on("Container Withdrawal", {
	setup(frm) {
		frm.set_query("container", () => ({
			filters: { status: ["in", ["مؤجرة", "متأخرة"]] },
		}));
		frm.set_query("driver", () => ({ filters: { position: "سائق", status: "نشط" } }));
		frm.set_query("supervisor", () => ({ filters: { position: "مشرف سواقين", status: "نشط" } }));
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
