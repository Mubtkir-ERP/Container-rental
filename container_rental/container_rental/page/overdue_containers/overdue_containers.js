// S11 — the owner's most important screen: interactive table + card toggle,
// live-updating delay durations, severity colors, filters, stats bar,
// quick actions (supervisor unload request / WhatsApp / call) and export.

frappe.pages["overdue-containers"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("متابعة الحاويات المتأخرة"),
		single_column: true,
	});

	const state = { rows: [], stats: {}, view: "table", timer: null, poll: null };

	$(`<style>
		.odc-stats { display: flex; gap: 14px; margin: 12px 0; flex-wrap: wrap; }
		.odc-stat { border: 1px solid var(--border-color); border-radius: 10px; padding: 10px 18px; background: var(--card-bg); }
		.odc-stat b { font-size: 22px; display: block; }
		.odc-table { width: 100%; border-collapse: collapse; }
		.odc-table th, .odc-table td { border: 1px solid var(--border-color); padding: 6px 8px; font-size: 12.5px; text-align: right; }
		.odc-table th { background: var(--control-bg); position: sticky; top: 0; }
		.odc-sev-yellow { background: rgba(255, 221, 87, 0.18); }
		.odc-sev-orange { background: rgba(255, 152, 0, 0.18); }
		.odc-sev-red { background: rgba(244, 67, 54, 0.18); }
		.odc-badge { padding: 2px 8px; border-radius: 10px; font-weight: 700; font-size: 11px; color: #fff; }
		.odc-badge.yellow { background: #b58a00; }
		.odc-badge.orange { background: #d35400; }
		.odc-badge.red { background: #c0392b; }
		.odc-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(270px, 1fr)); gap: 14px; }
		.odc-card { border: 1px solid var(--border-color); border-right-width: 5px; border-radius: 10px; padding: 12px 14px; background: var(--card-bg); }
		.odc-card.yellow { border-right-color: #b58a00; }
		.odc-card.orange { border-right-color: #d35400; }
		.odc-card.red { border-right-color: #c0392b; }
		.odc-card .odc-title { font-weight: 700; font-size: 15px; }
		.odc-card .odc-line { color: var(--text-muted); font-size: 12.5px; margin-top: 3px; }
		.odc-actions .btn { margin-inline-end: 4px; margin-top: 6px; }
		.odc-wrap { overflow-x: auto; }
	</style>`).appendTo(page.main);

	// ── Filters ──────────────────────────────────────────────────────────
	const filters = {};
	filters.classification = page.add_field({
		fieldname: "classification", label: __("التصنيف"), fieldtype: "Link",
		options: "Container Classification", change: () => load(),
	});
	filters.container_size = page.add_field({
		fieldname: "container_size", label: __("حجم الحاوية"), fieldtype: "Link",
		options: "Container Size", change: () => load(),
	});
	filters.branch = page.add_field({
		fieldname: "branch", label: __("الفرع"), fieldtype: "Link",
		options: "Rental Branch", change: () => load(),
	});
	filters.driver = page.add_field({
		fieldname: "driver", label: __("السائق"), fieldtype: "Link", options: "Employee",
		get_query: () => ({ filters: { designation: "سائق" } }), change: () => load(),
	});
	filters.delay_range = page.add_field({
		fieldname: "delay_range", label: __("نطاق التأخير"), fieldtype: "Select",
		options: ["", "0-2", "3-7", "7+"], change: () => load(),
	});

	function get_filters() {
		const out = {};
		Object.keys(filters).forEach((k) => {
			const v = filters[k].get_value();
			if (v) out[k] = v;
		});
		return out;
	}

	// ── Actions ──────────────────────────────────────────────────────────
	page.set_primary_action(__("تحديث"), () => load(), "refresh");
	page.add_inner_button(__("عرض جدول / بطاقات"), () => {
		state.view = state.view === "table" ? "cards" : "table";
		render();
	});
	page.add_inner_button(__("تصدير Excel"), () => open_report());
	page.add_inner_button(__("تصدير PDF"), () => open_report());

	function open_report() {
		// Same dataset + filters in the query report, where native Excel/PDF export applies
		frappe.route_options = get_filters();
		frappe.set_route("query-report", "Overdue Containers Report");
	}

	const $stats = $('<div class="odc-stats"></div>').appendTo(page.main);
	const $body = $('<div class="odc-wrap"></div>').appendTo(page.main);

	// ── Data ─────────────────────────────────────────────────────────────
	function load() {
		frappe.call({
			method: "container_rental.api.get_overdue_rentals",
			args: { filters: get_filters() },
			callback(r) {
				state.rows = (r.message && r.message.rows) || [];
				state.stats = (r.message && r.message.stats) || {};
				render();
			},
		});
	}

	function delay_parts(row) {
		// Live recomputation: now − due_on (updates without page reload)
		const due = frappe.datetime.str_to_obj(row.due_on);
		const hours = Math.max(0, Math.floor((new Date() - due) / 36e5));
		return { days: Math.floor(hours / 24), hours: hours % 24, total: hours };
	}

	function delay_text(row) {
		const d = delay_parts(row);
		return __("متأخرة {0} يوم {1} ساعة", [d.days, d.hours]);
	}

	// ── Render ───────────────────────────────────────────────────────────
	function render() {
		const s = state.stats;
		$stats.html(`
			<div class="odc-stat"><b>${s.total ?? 0}</b>${__("إجمالي الحاويات المتأخرة")}</div>
			<div class="odc-stat"><b>${s.avg_days ?? 0}</b>${__("متوسط مدة التأخير (يوم)")}</div>
			<div class="odc-stat"><b style="color:#c0392b">${s.over_week ?? 0}</b>${__("متأخرة أكثر من أسبوع")}</div>
		`);

		if (!state.rows.length) {
			$body.html(`<div class="text-muted" style="padding:30px;text-align:center">${__("لا توجد حاويات متأخرة 🎉")}</div>`);
			return;
		}
		state.view === "table" ? render_table() : render_cards();
	}

	function action_buttons(row) {
		return `
			<button class="btn btn-xs btn-primary odc-unload" data-rec="${row.rental_record}">${__("طلب تفريغ")}</button>
			<button class="btn btn-xs btn-warning odc-extend" data-rec="${row.rental_record}">${__("تمديد")}</button>
			<button class="btn btn-xs btn-success odc-wa" data-rec="${row.rental_record}">${__("واتساب")}</button>
			<a class="btn btn-xs btn-default" href="tel:${row.mobile_no || ""}">${__("اتصال")}</a>`;
	}

	function open_extend_dialog(rec) {
		frappe.db.get_single_value("Container Rental Settings", "min_extension_days").then((min_days) => {
			min_days = min_days || 10;
			const d = new frappe.ui.Dialog({
				title: __("تمديد مدة الحاوية"),
				fields: [
					{
						fieldname: "days", fieldtype: "Int", label: __("عدد أيام التمديد"),
						reqd: 1, default: min_days,
						description: __("أقل مدة تمديد: {0} يوم — يُحاسب التمديد بطلب جديد", [min_days]),
					},
					{ fieldname: "rental_value", fieldtype: "Currency", label: __("قيمة التمديد"), reqd: 1 },
					{
						fieldname: "payment_method", fieldtype: "Link", label: __("طريقة الدفع"),
						options: "Mode of Payment",
					},
				],
				primary_action_label: __("تمديد"),
				primary_action(values) {
					if (values.days < min_days) {
						frappe.msgprint(__("أقل مدة تمديد هي {0} يوم", [min_days]));
						return;
					}
					d.hide();
					frappe.call({
						method: "container_rental.api.extend_rental",
						args: {
							rental_record: rec,
							days: values.days,
							rental_value: values.rental_value,
							payment_method: values.payment_method,
						},
						callback(r) {
							const m = r.message || {};
							frappe.show_alert({
								message: __("تم التمديد — أُنشئ الطلب {0}", [m.order]),
								indicator: "green",
							});
							load();
						},
					});
				},
			});
			d.show();
		});
	}

	function last_wa(row) {
		if (!row.last_whatsapp_on) return __("لم يتم التذكير");
		return `${row.last_whatsapp_message || ""}<br><span class="text-muted">${frappe.datetime.str_to_user(row.last_whatsapp_on)}</span>`;
	}

	function render_table() {
		const headers = [
			__("رقم الحاوية"), __("العميل"), __("رقم الجوال"), __("الحجم"), __("الفرع"),
			__("العنوان / الموقع"), __("السائق"), __("تاريخ التوصيل"), __("تاريخ الاستحقاق"),
			__("مدة التأخير"), __("درجة الخطورة"), __("آخر رسالة واتساب"), __("إجراء سريع"),
		];
		const rows_html = state.rows
			.map(
				(row) => `
			<tr class="odc-sev-${row.severity}">
				<td><a href="/app/container/${encodeURIComponent(row.container)}">${row.container}</a></td>
				<td>${row.client_name || row.client || ""}</td>
				<td dir="ltr">${row.mobile_no || ""}</td>
				<td>${row.container_size || ""}</td>
				<td>${row.branch || ""}</td>
				<td>${row.address || ""}</td>
				<td>${row.driver_name || ""}</td>
				<td>${frappe.datetime.str_to_user(row.delivered_on) || ""}</td>
				<td>${frappe.datetime.str_to_user(row.due_on) || ""}</td>
				<td class="odc-delay" data-rec="${row.rental_record}"><b>${delay_text(row)}</b></td>
				<td><span class="odc-badge ${row.severity}">${row.severity_label}</span></td>
				<td>${last_wa(row)}</td>
				<td class="odc-actions">${action_buttons(row)}</td>
			</tr>`
			)
			.join("");
		$body.html(`
			<table class="odc-table">
				<thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead>
				<tbody>${rows_html}</tbody>
			</table>`);
		bind_actions();
	}

	function render_cards() {
		const cards = state.rows
			.map(
				(row) => `
			<div class="odc-card ${row.severity}">
				<div class="odc-title">${row.container} — ${row.container_size || ""}</div>
				<div class="odc-line">${__("العميل")}: ${row.client_name || ""} — <span dir="ltr">${row.mobile_no || ""}</span></div>
				<div class="odc-line">${__("فترة التأجير")}: ${frappe.datetime.str_to_user(row.delivered_on) || ""} ← ${frappe.datetime.str_to_user(row.due_on) || ""}</div>
				<div class="odc-line">${__("السائق")}: ${row.driver_name || "-"}</div>
				<div class="odc-line">${__("العنوان")}: ${row.address || "-"}</div>
				<div class="odc-line">${__("آخر واتساب")}: ${last_wa(row)}</div>
				<div class="odc-line odc-delay" data-rec="${row.rental_record}"><b>${delay_text(row)}</b></div>
				<div class="odc-actions">${action_buttons(row)}</div>
			</div>`
			)
			.join("");
		$body.html(`<div class="odc-cards">${cards}</div>`);
		bind_actions();
	}

	function bind_actions() {
		$body.find(".odc-extend").on("click", function () {
			open_extend_dialog($(this).data("rec"));
		});
		$body.find(".odc-unload").on("click", function () {
			const rec = $(this).data("rec");
			frappe.call({
				method: "container_rental.api.send_unload_request",
				args: { rental_record: rec },
				callback() {
					frappe.show_alert({ message: __("أُرسل طلب التفريغ لمشرف السواقين"), indicator: "green" });
					load();
				},
			});
		});
		$body.find(".odc-wa").on("click", function () {
			const rec = $(this).data("rec");
			frappe.call({
				method: "container_rental.api.send_client_whatsapp",
				args: { rental_record: rec },
				callback(r) {
					const m = r.message || {};
					if (m.sent) {
						frappe.show_alert({ message: __("أُرسلت رسالة واتساب للعميل"), indicator: "green" });
					} else if (m.wa_link) {
						window.open(m.wa_link, "_blank");
					}
					load();
				},
			});
		});
	}

	// Live ticking delay text (every minute) without reloading the page,
	// plus a 5-minute data refresh.
	state.timer = setInterval(() => {
		state.rows.forEach((row) => {
			$body.find(`.odc-delay[data-rec="${row.rental_record}"] b`).text(delay_text(row));
		});
	}, 60 * 1000);
	state.poll = setInterval(() => load(), 5 * 60 * 1000);

	$(wrapper).on("remove", () => {
		clearInterval(state.timer);
		clearInterval(state.poll);
	});

	load();
};
