frappe.query_reports["Expenses Report"] = {
	filters: [
		{ fieldname: "from_date", label: __("من تاريخ"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("إلى تاريخ"), fieldtype: "Date" },
		{ fieldname: "branch", label: __("الفرع"), fieldtype: "Link", options: "Rental Branch" },
		{
			fieldname: "expense_type",
			label: __("نوع المصروف"),
			fieldtype: "Select",
			options: ["", "رسوم بلدية", "صيانة"],
		},
	],
};
