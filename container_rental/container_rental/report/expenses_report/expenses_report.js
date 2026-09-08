frappe.query_reports["Expenses Report"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Rental Branch" },
		{
			fieldname: "expense_type",
			label: __("Expense Type"),
			fieldtype: "Select",
			options: ["", "رسوم بلدية", "صيانة"],
		},
	],
};
