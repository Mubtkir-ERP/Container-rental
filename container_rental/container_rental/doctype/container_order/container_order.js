frappe.ui.form.on("Container Order", {
	setup(frm) {
		frm.set_query("container", () => ({
			filters: { size: frm.doc.container_size, status: "متاحة" },
		}));
		frm.set_query("contract", () => ({
			filters: { client: frm.doc.client, docstatus: 1, contract_status: "ساري" },
		}));
		frm.set_query("container", "additional_containers", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return { filters: { size: row.container_size, status: "متاحة" } };
		});
	},

	refresh(frm) {
		frm.trigger("render_status_buttons");
	},

	container_size(frm) {
		frm.set_value("container", null);
	},

	rental_days(frm) {
		frm.trigger("compute_end_date");
	},

	rental_start_date(frm) {
		frm.trigger("compute_end_date");
	},

	compute_end_date(frm) {
		if (frm.doc.rental_start_date && frm.doc.rental_days) {
			frm.set_value(
				"rental_end_date",
				frappe.datetime.add_days(frm.doc.rental_start_date, frm.doc.rental_days)
			);
		}
	},

	client(frm) {
		if (!frm.doc.client) return;
		// Offer the customer's saved delivery locations as the delivery address
		frappe.db.get_doc("Customer", frm.doc.client).then((customer) => {
			const locations = customer.cr_delivery_locations || [];
			if (!locations.length) return;
			const def = locations.find((a) => a.is_default) || locations[0];
			if (!frm.doc.delivery_address) frm.set_value("delivery_address", def.address);
		});
	},

	suggest_container(frm) {
		if (!frm.doc.container_size) {
			frappe.msgprint(__("اختر حجم الحاوية أولًا"));
			return;
		}
		frappe.call({
			method: "container_rental.container_rental.doctype.container.container.suggest_container",
			args: { size: frm.doc.container_size, branch: frm.doc.branch },
			callback(r) {
				if (r.message) {
					frm.set_value("container", r.message);
				} else {
					frappe.msgprint(__("لا يوجد حاوية فارغة بهذا الحجم"));
				}
			},
		});
	},

	render_status_buttons(frm) {
		if (frm.is_new()) return;
		const call = (method, args = {}) =>
			frm.call(method, args).then(() => frm.reload_doc());

		if (frm.doc.docstatus === 0 && !frm.is_dirty()) {
			if (frm.doc.status === "جديد") {
				frm.add_custom_button(__("تأكيد الطلب"), () => call("confirm_order")).addClass("btn-primary");
			}
			if (frm.doc.status === "بانتظار تأكيد الحوالة") {
				frm.add_custom_button(__("تأكيد وصول الحوالة"), () => call("confirm_transfer")).addClass("btn-primary");
			}
			if (frm.doc.status === "بانتظار تحديد سائق") {
				frm.add_custom_button(__("إسناد سائق"), () => {
					const d = new frappe.ui.Dialog({
						title: __("إسناد سائق للطلب"),
						fields: [
							{
								fieldname: "driver",
								fieldtype: "Link",
								label: __("السائق"),
								options: "CR Employee",
								reqd: 1,
								get_query: () => ({ filters: { position: "سائق", status: "نشط" } }),
							},
							{
								fieldname: "vehicle",
								fieldtype: "Link",
								label: __("الشاحنة"),
								options: "Truck",
							},
						],
						primary_action_label: __("إسناد"),
						primary_action(values) {
							d.hide();
							call("assign_driver", { driver: values.driver, vehicle: values.vehicle });
						},
					});
					d.show();
				}).addClass("btn-primary");
			}
			if (frm.doc.status === "مُسنَد لسائق") {
				frm.add_custom_button(__("تسجيل توصيل"), () => {
					frappe.new_doc("Container Delivery", {
						order: frm.doc.name,
						container: frm.doc.container,
						driver: frm.doc.assigned_driver,
						vehicle: frm.doc.assigned_vehicle,
					});
				}).addClass("btn-primary");
			}
			if (["جديد", "بانتظار تأكيد الحوالة", "بانتظار تحديد سائق", "مُسنَد لسائق"].includes(frm.doc.status)) {
				frm.add_custom_button(__("إلغاء الطلب"), () => {
					frappe.confirm(__("هل أنت متأكد من إلغاء الطلب؟"), () => call("cancel_order"));
				});
			}
			if (frm.doc.status === "جديد" || frm.doc.status === "بانتظار تحديد سائق") {
				frm.add_custom_button(__("اقتراح حاوية"), () => frm.trigger("suggest_container"));
			}
		}
		if (
			frm.doc.status === "تم التوصيل" &&
			frm.doc.payment_method === "آجل" &&
			!frm.doc.payment_received
		) {
			frm.add_custom_button(__("تسجيل استلام المبلغ"), () => {
				const d = new frappe.ui.Dialog({
					title: __("استلام المبلغ"),
					fields: [
						{ fieldname: "cash_box", fieldtype: "Link", label: __("الخزينة"), options: "Cash Box" },
					],
					primary_action_label: __("تسجيل"),
					primary_action(values) {
						d.hide();
						call("mark_payment_received", { cash_box: values.cash_box });
					},
				});
				d.show();
			}).addClass("btn-primary");
		}
	},
});
