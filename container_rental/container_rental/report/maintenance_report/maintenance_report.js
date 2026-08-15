frappe.query_reports["Maintenance Report"] = {
	filters: [
		{ fieldname: "vehicle", label: __("رقم السيارة"), fieldtype: "Link", options: "Truck" },
		{
			fieldname: "maintenance_type",
			label: __("نوع الصيانة"),
			fieldtype: "Select",
			options: ["", "تغيير زيت", "إطارات", "فرامل", "بطارية", "صيانة دورية", "إصلاح عطل", "أخرى"],
		},
		{ fieldname: "from_date", label: __("من تاريخ"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("إلى تاريخ"), fieldtype: "Date" },
	],
};
