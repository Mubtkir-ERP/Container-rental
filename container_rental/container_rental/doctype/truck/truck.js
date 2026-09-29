frappe.ui.form.on("Truck", {
	setup(frm) {
		frm.set_query("driver", () => ({
			query: "container_rental.container_rental.hr_utils.driver_query",
		}));
	},
});
