frappe.ui.form.on("Truck", {
	setup(frm) {
		frm.set_query("driver", () => ({
			filters: { designation: "سائق", status: "Active" },
		}));
	},
});
