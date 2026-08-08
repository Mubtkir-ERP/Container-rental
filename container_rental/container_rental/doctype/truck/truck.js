frappe.ui.form.on("Truck", {
	setup(frm) {
		frm.set_query("driver", () => ({
			filters: { position: "سائق", status: "نشط" },
		}));
	},
});
