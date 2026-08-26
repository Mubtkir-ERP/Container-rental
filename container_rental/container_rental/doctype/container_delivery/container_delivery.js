frappe.ui.form.on("Container Delivery", {
	setup(frm) {
		frm.set_query("container", () => ({ filters: { status: "متاحة" } }));
		frm.set_query("driver", () => ({ filters: { designation: "سائق", status: "Active" } }));
		frm.set_query("supervisor", () => ({ filters: { designation: "مشرف سواقين", status: "Active" } }));
		frm.set_query("order", () => ({ filters: { status: "مُسنَد لسائق" } }));
		frm.set_query("contract", () => ({ filters: { docstatus: 1, contract_status: "ساري" } }));
	},

	refresh(frm) {
		// One step: saving a draft delivery submits it right away (no separate Submit click)
		if (frm.doc.docstatus === 0) {
			frm.disable_save();
			frm.page.set_primary_action(__("تسجيل التوصيل"), () => frm.save("Submit"));
		}
	},

	order(frm) {
		if (!frm.doc.order) return;
		frappe.db.get_doc("Container Order", frm.doc.order).then((order) => {
			frm.set_value("client", order.client);
			frm.set_value("address", order.delivery_address);
			frm.set_value("agreed_days", order.rental_days);
			if (order.container && !frm.doc.container) frm.set_value("container", order.container);
			if (order.assigned_driver) frm.set_value("driver", order.assigned_driver);
			if (order.assigned_vehicle) frm.set_value("vehicle", order.assigned_vehicle);
			if (order.contract) frm.set_value("contract", order.contract);
		});
	},

	contract(frm) {
		if (!frm.doc.contract || frm.doc.order) return;
		frappe.db.get_doc("Container Contract", frm.doc.contract).then((contract) => {
			frm.set_value("client", contract.client);
			frm.set_value("address", frm.doc.address || contract.location);
			frm.set_value("agreed_days", contract.trip_duration_days);
		});
	},

	delivery_datetime(frm) {
		frm.trigger("compute_due");
	},

	agreed_days(frm) {
		frm.trigger("compute_due");
	},

	compute_due(frm) {
		if (frm.doc.delivery_datetime && frm.doc.agreed_days) {
			frm.set_value(
				"due_datetime",
				frappe.datetime.add_days(frm.doc.delivery_datetime, frm.doc.agreed_days)
			);
		}
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
