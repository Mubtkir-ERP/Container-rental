frappe.query_reports["Monthly Invoices Report"] = {
	filters: [
		{ fieldname: "contract", label: __("العقد"), fieldtype: "Link", options: "Container Contract" },
		{ fieldname: "client", label: __("العميل"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "month_key", label: __("الشهر (YYYY-MM)"), fieldtype: "Data" },
		{
			fieldname: "payment_status",
			label: __("حالة السداد"),
			fieldtype: "Select",
			options: ["", "غير مسددة", "مسددة جزئيًا", "مسددة"],
		},
	],

	onload(report) {
		report.page.add_inner_button(__("توليد فواتير الشهر السابق"), () => {
			frappe.confirm(__("توليد الفواتير الشهرية للعقود عن الشهر السابق؟"), () => {
				frappe.call({
					method: "container_rental.container_rental.tasks.generate_monthly_invoices",
					callback(r) {
						const created = r.message || [];
						frappe.msgprint(
							created.length
								? __("تم توليد {0} فاتورة: {1}", [created.length, created.join("، ")])
								: __("لا توجد فواتير جديدة للتوليد")
						);
						frappe.query_report.refresh();
					},
				});
			});
		});
	},
};
