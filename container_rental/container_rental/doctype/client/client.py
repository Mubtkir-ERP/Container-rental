from frappe.model.document import Document


class Client(Document):
	def validate(self):
		self.ensure_single_default_address()

	def ensure_single_default_address(self):
		defaults = [r for r in (self.addresses or []) if r.is_default]
		if len(defaults) > 1:
			for row in defaults[1:]:
				row.is_default = 0
