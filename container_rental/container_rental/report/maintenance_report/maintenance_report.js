frappe.query_reports["Maintenance Report"] = {
	filters: [
		{ fieldname: "vehicle", label: __("Vehicle No"), fieldtype: "Link", options: "Truck" },
		{
			fieldname: "maintenance_type",
			label: __("Maintenance Type"),
			fieldtype: "Select",
			options: ["", "Oil Change", "Tyres", "Brakes", "Battery", "Periodic Service", "Repair", "أخرى"],
		},
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
	],
};
