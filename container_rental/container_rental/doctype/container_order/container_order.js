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
		// The status changes server-side (driver confirm / delivery submit);
		// re-fetch when the cached form is behind so it never shows a stale state.
		if (!frm.is_new() && !frm.is_dirty()) {
			frappe.db.get_value("Container Order", frm.doc.name, "status").then((r) => {
				if (r.message && r.message.status !== frm.doc.status) frm.reload_doc();
			});
		}
		frm.trigger("render_status_buttons");
		frm.trigger("render_location_button");
		frm.trigger("render_driver_view");
	},

	render_location_button(frm) {
		if (frm.doc.google_maps_link) {
			frm.add_custom_button(__("فتح الموقع"), () => {
				window.open(frm.doc.google_maps_link, "_blank");
			});
		}
	},

	is_driver_only() {
		const office = ["System Manager", "Container Manager", "Customer Service",
			"Driver Supervisor", "Transfer Follow-up"];
		return frappe.user.has_role("Driver") && !office.some((r) => frappe.user.has_role(r));
	},

	render_driver_view(frm) {
		if (frm.is_new() || !frm.events.is_driver_only()) return;
		// Driver's screen = the "Delivery Info" section only, one action button
		const other_sections = [
			"client_section", "order_section", "additional_section", "rental_section",
			"delivery_schedule_section", "assignment_section", "transfer_section",
			"payment_track_section", "meta_section",
		];
		frm.toggle_display(other_sections, false);
		frm.disable_save();
		if (frm.doc.status === "مُسنَد لسائق") {
			frm.page.set_primary_action(__("تأكيد التوصيل"), () => {
				if (!frm.doc.container) {
					frappe.msgprint(__("أدخل رقم الحاوية أولًا"));
					return;
				}
				if (frm.doc.payment_method === "آجل" && !frm.doc.delivery_note_no) {
					frappe.msgprint(__("أدخل رقم دفتر التسليم للدفع الآجل"));
					return;
				}
				// One step: the server stores the container / note and records the delivery
				frappe.call({
					method: "run_doc_method",
					args: {
						dt: frm.doctype, dn: frm.docname, method: "driver_confirm_delivery",
						args: { container: frm.doc.container, delivery_note_no: frm.doc.delivery_note_no },
					},
					callback() {
						frappe.show_alert({ message: __("تم تأكيد التوصيل"), indicator: "green" });
						frm.doc.__unsaved = 0;
						frappe.set_route("List", "Container Order");
					},
				});
			});
		}
	},

	container_size(frm) {
		frm.set_value("container", null);
	},

	rental_days(frm) {
		// days → end date (only when it actually changes, so the two handlers converge)
		if (frm.doc.rental_start_date && frm.doc.rental_days) {
			const end = frappe.datetime.add_days(frm.doc.rental_start_date, frm.doc.rental_days);
			if (end !== frm.doc.rental_end_date) frm.set_value("rental_end_date", end);
		}
	},

	rental_end_date(frm) {
		// end date → days, recomputed on EVERY change of the date
		if (frm.doc.rental_start_date && frm.doc.rental_end_date) {
			const days = frappe.datetime.get_day_diff(frm.doc.rental_end_date, frm.doc.rental_start_date);
			if (days > 0 && days !== frm.doc.rental_days) frm.set_value("rental_days", days);
		}
	},

	rental_start_date(frm) {
		frm.trigger("rental_days");
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
			args: { size: frm.doc.container_size },
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
		if (frm.is_new() || frm.events.is_driver_only()) return;
		const call = (method, args = {}) =>
			frm.call(method, args).then(() => frm.reload_doc());

		if (frm.doc.status === "تم التوصيل") {
			frm.add_custom_button(__("إنشاء فاتورة مبيعات"), () => {
				frm.call("make_sales_invoice").then((r) => {
					if (r.message) frappe.set_route("Form", "Sales Invoice", r.message);
				});
			}).addClass("btn-primary");
		}

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
								options: "Employee",
								reqd: 1,
								get_query: () => ({ filters: { designation: "سائق", status: "Active" } }),
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
						{ fieldname: "cash_box", fieldtype: "Link", label: __("الصندوق النقدي"), options: "Account", get_query: () => ({ filters: { account_type: "Cash", is_group: 0 } }) },
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
