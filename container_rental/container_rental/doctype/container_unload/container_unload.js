frappe.ui.form.on("Container Unload", {
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
					frappe.msgprint(__("لا يوجد سجل تأجير مفتوح لهذه الحاوية"));
					return;
				}
				const r = rows[0];
				frm.set_value("rental_record", r.name);
				frappe.db.get_value("Customer", r.client, "customer_name").then((res) => {
					frm.dashboard.set_headline(
						__("العميل: {0} — تاريخ التوصيل: {1} — الاستحقاق: {2}", [
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
