frappe.pages["containers-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("لوحة التحكم الرئيسية"),
		single_column: true,
	});

	page.set_secondary_action(__("تحديث"), () => render_cards(page), "refresh");
	page.add_inner_button(__("التقرير العام للحاويات"), () => {
		frappe.set_route("query-report", "General Containers Report");
	});

	$(`<style>
		.cr-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; margin-top: 15px; }
		.cr-card { border: 1px solid var(--border-color); border-radius: 10px; padding: 16px; background: var(--card-bg); }
		.cr-card .cr-count { font-size: 30px; font-weight: 700; margin: 4px 0; }
		.cr-card .cr-label { color: var(--text-muted); font-size: 13px; }
		.cr-card.cr-danger .cr-count { color: #c0392b; }
		.cr-card.cr-warning .cr-count { color: #d35400; }
		.cr-card.cr-ok .cr-count { color: #1e7e34; }
		.cr-card .btn { margin-top: 8px; }
	</style>`).appendTo(page.main);

	page.body = $('<div class="cr-cards"></div>').appendTo(page.main);
	render_cards(page);
};

function render_cards(page) {
	frappe.call({
		method: "container_rental.api.get_dashboard_counts",
		callback(r) {
			const c = r.message || {};
			const cards = [
				{
					label: __("إجمالي عدد الحاويات"), value: c.total_containers,
					route: () => frappe.set_route("List", "Container"),
				},
				{
					label: __("الحاويات الخالية"), value: c.available_containers, cls: "cr-ok",
					route: () => frappe.set_route("List", "Container", { status: "متاحة" }),
				},
				{
					label: __("الحاويات المؤجرة"), value: c.rented_containers,
					route: () => frappe.set_route("List", "Container", { status: "مؤجرة" }),
				},
				{
					label: __("الحاويات المتأخرة"), value: c.overdue_containers, cls: "cr-danger",
					route: () => frappe.set_route("overdue-containers"),
				},
				{
					label: __("الحاويات المسحوبة"), value: c.withdrawn_containers,
					route: () => frappe.set_route("List", "Container", { status: "مسحوبة" }),
				},
				{
					label: __("تأخيرات الدفع"), value: c.payment_delays, cls: "cr-danger",
					route: () =>
						frappe.set_route("List", "Container Order", {
							payment_method: "آجل",
							payment_received: 0,
							status: "تم التوصيل",
						}),
				},
				{
					label: __("تأخيرات غيار الزيت"), value: c.oil_change_delays, cls: "cr-warning",
					route: () => frappe.set_route("query-report", "Truck Alerts Report"),
				},
				{
					label: __("التصاريح المنتهية"), value: c.expired_permits, cls: "cr-danger",
					route: () => frappe.set_route("query-report", "Employee Alerts Report"),
				},
				{
					label: __("تنبيهات الشاحنات"), value: c.truck_alerts, cls: "cr-warning",
					route: () => frappe.set_route("query-report", "Truck Alerts Report"),
				},
				{
					label: __("تنبيهات الموظفين"), value: c.employee_alerts, cls: "cr-warning",
					route: () => frappe.set_route("query-report", "Employee Alerts Report"),
				},
				{
					label: __("العقود المنتهية"), value: c.expired_contracts,
					route: () => {
						frappe.route_options = { status: "منتهٍ" };
						frappe.set_route("query-report", "Contract Report");
					},
				},
				{
					label: __("العقود المنتهية ولها رحلات"), value: c.expired_contracts_with_trips, cls: "cr-warning",
					route: () => {
						frappe.route_options = { status: "منتهٍ" };
						frappe.set_route("query-report", "Contract Report");
					},
				},
				{
					label: __("الإيجارات الآجلة"), value: c.credit_rentals,
					route: () => frappe.set_route("List", "Container Order", { payment_method: "آجل" }),
				},
			];

			page.body.empty();
			cards.forEach((card) => {
				const $card = $(`
					<div class="cr-card ${card.cls || ""}">
						<div class="cr-label">${card.label}</div>
						<div class="cr-count">${card.value ?? 0}</div>
						<button class="btn btn-xs btn-default">${__("عرض")}</button>
					</div>`);
				$card.find("button").on("click", card.route);
				page.body.append($card);
			});
		},
	});
}
