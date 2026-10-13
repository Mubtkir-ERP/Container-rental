// Shared voucher dialog for one maintenance / oil-change row
function cr_expense_voucher_dialog(frm, table, row, label) {
	const d = new frappe.ui.Dialog({
		title: __("Create Expense Voucher"),
		fields: [
			{
				fieldname: "info", fieldtype: "HTML",
				options: `<div class="text-muted">${__("Item")}: <b>${frappe.utils.escape_html(label || "")}</b> — ${__("Cost")}: <b>${format_currency(row.cost)}</b></div>`,
			},
			{
				fieldname: "expense_account", fieldtype: "Link", label: __("Expense Account"),
				options: "Account", default: row.expense_account,
				get_query: () => ({ filters: { is_group: 0, root_type: "Expense" } }),
				description: __("Leave empty to use the vehicle expense account from settings"),
			},
			{
				fieldname: "payout_account", fieldtype: "Link", label: __("Paid From Account"),
				options: "Account", reqd: 1,
				get_query: () => ({ filters: { is_group: 0, account_type: ["in", ["Cash", "Bank"]] } }),
			},
			{ fieldname: "posting_date", fieldtype: "Date", label: __("Posting Date"), default: frappe.datetime.get_today() },
		],
		primary_action_label: __("Create Voucher"),
		primary_action(values) {
			d.hide();
			frappe.call({
				method: "container_rental.container_rental.doctype.truck.truck.make_expense_voucher",
				args: {
					truck: frm.doc.name,
					table: table,
					row_name: row.name,
					payout_account: values.payout_account,
					expense_account: values.expense_account,
					posting_date: values.posting_date,
				},
				freeze: true,
				callback(r) {
					if (!r.message) return;
					frappe.show_alert({ message: __("Expense voucher {0} created", [r.message]), indicator: "green" });
					frm.reload_doc();
				},
			});
		},
	});
	d.show();
}

function cr_row_voucher(frm, cdt, cdn, table, label_field) {
	const row = locals[cdt][cdn];
	if (frm.is_dirty() || frm.is_new()) {
		frappe.msgprint(__("Save the truck first, then create the voucher"));
		return;
	}
	if (row.journal_entry) {
		frappe.set_route("Form", "Journal Entry", row.journal_entry);
		return;
	}
	if (!row.cost) {
		frappe.msgprint(__("Enter the item cost first"));
		return;
	}
	cr_expense_voucher_dialog(frm, table, row, label_field ? row[label_field] : __("Oil Change"));
}

frappe.ui.form.on("Truck", {
	setup(frm) {
		frm.set_query("driver", () => ({
			query: "container_rental.container_rental.hr_utils.driver_query",
		}));
	},

	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Pay Unpaid Expenses"), () => {
			frappe.call({
				method: "container_rental.container_rental.doctype.truck.truck.get_unpaid_expense_rows",
				args: { truck: frm.doc.name },
				callback(r) {
					const rows = r.message || [];
					if (!rows.length) {
						frappe.msgprint(__("No unpaid expenses on this truck"));
						return;
					}
					cr_bulk_voucher_dialog(frm, rows);
				},
			});
		});
	},
});

function cr_bulk_voucher_dialog(frm, rows) {
	const total = rows.reduce((s, r) => s + (r.cost || 0), 0);
	const d = new frappe.ui.Dialog({
		title: __("Pay Unpaid Expenses"),
		size: "large",
		fields: [
			{
				fieldname: "items", fieldtype: "Table", label: __("Unpaid Items"),
				cannot_add_rows: 1, cannot_delete_rows: 1, in_place_edit: false,
				data: rows.map((r) => ({ ...r, pay: 1 })),
				get_data: () => rows.map((r) => ({ ...r, pay: 1 })),
				fields: [
					{ fieldname: "pay", fieldtype: "Check", label: __("Pay"), in_list_view: 1, columns: 1, default: 1 },
					{ fieldname: "date", fieldtype: "Date", label: __("Date"), in_list_view: 1, columns: 2, read_only: 1 },
					{ fieldname: "label", fieldtype: "Data", label: __("Item"), in_list_view: 1, columns: 4, read_only: 1 },
					{ fieldname: "cost", fieldtype: "Currency", label: __("Cost"), in_list_view: 1, columns: 2, read_only: 1 },
					{ fieldname: "table", fieldtype: "Data", hidden: 1 },
					{ fieldname: "row_name", fieldtype: "Data", hidden: 1 },
				],
			},
			{
				fieldname: "expense_account", fieldtype: "Link", label: __("Expense Account"), options: "Account",
				get_query: () => ({ filters: { is_group: 0, root_type: "Expense" } }),
				description: __("Leave empty to use the vehicle expense account from settings"),
			},
			{
				fieldname: "payout_account", fieldtype: "Link", label: __("Paid From Account"), options: "Account", reqd: 1,
				get_query: () => ({ filters: { is_group: 0, account_type: ["in", ["Cash", "Bank"]] } }),
			},
			{ fieldname: "posting_date", fieldtype: "Date", label: __("Posting Date"), default: frappe.datetime.get_today() },
			{
				fieldname: "total_html", fieldtype: "HTML",
				options: `<div class="text-muted">${__("Total unpaid")}: <b>${format_currency(total)}</b></div>`,
			},
		],
		primary_action_label: __("Create Vouchers"),
		primary_action(values) {
			const picked = (values.items || []).filter((r) => r.pay);
			if (!picked.length) {
				frappe.msgprint(__("Select at least one item"));
				return;
			}
			d.hide();
			// One voucher per item keeps each expense traceable to its row
			const calls = picked.map((row) =>
				frappe.call({
					method: "container_rental.container_rental.doctype.truck.truck.make_expense_voucher",
					args: {
						truck: frm.doc.name,
						table: row.table,
						row_name: row.row_name,
						payout_account: values.payout_account,
						expense_account: values.expense_account,
						posting_date: values.posting_date,
					},
				})
			);
			frappe.dom.freeze(__("Creating vouchers..."));
			Promise.all(calls)
				.then(() => {
					frappe.dom.unfreeze();
					frappe.show_alert({ message: __("{0} expense vouchers created", [picked.length]), indicator: "green" });
					frm.reload_doc();
				})
				.catch(() => frappe.dom.unfreeze());
		},
	});
	d.show();
}

frappe.ui.form.on("Truck Maintenance Log", {
	make_payment(frm, cdt, cdn) {
		cr_row_voucher(frm, cdt, cdn, "maintenance_log", "maintenance_type");
	},
});

frappe.ui.form.on("Truck Oil Change", {
	make_payment(frm, cdt, cdn) {
		cr_row_voucher(frm, cdt, cdn, "oil_changes", null);
	},
});
