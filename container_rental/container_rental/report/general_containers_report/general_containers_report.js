frappe.query_reports["General Containers Report"] = {
	filters: [
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "متاحة", "مؤجرة", "تالفة", "صيانة", "متأخرة", "مسحوبة"],
		},
		{
			fieldname: "size",
			label: __("Size"),
			fieldtype: "Link",
			options: "Container Size",
		},
		{
			fieldname: "classification",
			label: __("Classification"),
			fieldtype: "Link",
			options: "Container Classification",
		},
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Rental Branch" },
	],
};
