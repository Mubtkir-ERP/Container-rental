frappe.query_reports["General Containers Report"] = {
	filters: [
		{
			fieldname: "status",
			label: __("الحالة"),
			fieldtype: "Select",
			options: ["", "متاحة", "مؤجرة", "تالفة", "صيانة", "متأخرة", "مسحوبة"],
		},
		{
			fieldname: "size",
			label: __("الحجم"),
			fieldtype: "Select",
			options: ["", "10 ياردة", "20 ياردة"],
		},
		{
			fieldname: "classification",
			label: __("التصنيف"),
			fieldtype: "Link",
			options: "Container Classification",
		},
		{ fieldname: "branch", label: __("الفرع"), fieldtype: "Link", options: "Rental Branch" },
	],
};
