import frappe
from frappe import _
from frappe.model.document import Document

# Statuses whose manual assignment requires an authorized role (open question 5)
RESTRICTED_STATUSES = ("تالفة", "صيانة")
STATUS_AUTHORIZED_ROLES = ("Container Manager", "Driver Supervisor", "System Manager")


class Container(Document):
	def before_save(self):
		# Barcode always mirrors the container number so labels stay consistent.
		# Stored as SVG so both the form control and print formats render it.
		self.barcode = generate_barcode_svg(self.container_no)

	def validate(self):
		if self.responsible_driver:
			from container_rental.container_rental import hr_utils
			hr_utils.ensure_driver(self.responsible_driver)


@frappe.whitelist()
def change_status(container, new_status):
	"""S4 list action 'تغيير الحالة'. Damaged/maintenance transitions are role-gated."""
	doc = frappe.get_doc("Container", container)
	valid = [s for s in (doc.meta.get_field("status").options or "").split("\n") if s]
	if new_status not in valid:
		frappe.throw(_("حالة غير صحيحة: {0}").format(new_status))

	if new_status in RESTRICTED_STATUSES or doc.status in RESTRICTED_STATUSES:
		if not set(frappe.get_roles()) & set(STATUS_AUTHORIZED_ROLES):
			frappe.throw(_("تغيير الحالة إلى/من تالفة أو صيانة يتطلب صلاحية مشرف السواقين أو مدير الحاويات"))

	if new_status == "مؤجرة":
		frappe.throw(_("حالة مؤجرة تُضبط تلقائيًا عبر عمليات التوصيل فقط"))

	old_status = doc.status
	doc.db_set("status", new_status)
	doc.add_comment("Info", _("تغيير الحالة من {0} إلى {1}").format(old_status, new_status))
	return new_status


@frappe.whitelist()
def release_to_available(container):
	"""Move a withdrawn (مسحوبة) container back to متاحة after inspection."""
	frappe.only_for(("Container Manager", "Driver Supervisor", "System Manager"))
	doc = frappe.get_doc("Container", container)
	if doc.status != "مسحوبة":
		frappe.throw(_("هذا الإجراء متاح فقط للحاويات المسحوبة"))
	doc.db_set("status", "متاحة")
	doc.add_comment("Info", _("إعادة الحاوية للمتاح بعد الفحص"))
	return "متاحة"


@frappe.whitelist()
def suggest_container(size, branch=None):
	"""Return the first available container of the given size (open question 1)."""
	filters = {"status": "متاحة", "size": size}
	if branch:
		filters["branch"] = branch
	containers = frappe.get_all("Container", filters=filters, order_by="container_no asc", limit=1, pluck="name")
	return containers[0] if containers else None


@frappe.whitelist()
def resolve_barcode(code):
	"""Resolve a scanned barcode / container number to a Container name."""
	name = frappe.db.get_value("Container", {"container_no": code})
	if not name:
		frappe.throw(_("لا توجد حاوية بهذا الباركود: {0}").format(code))
	return name


def generate_barcode_svg(value):
	"""Code128 SVG for the container number (scanner-readable label)."""
	import io

	from barcode import Code128
	from barcode.writer import SVGWriter

	buf = io.BytesIO()
	Code128(str(value), writer=SVGWriter()).write(
		buf, options={"module_height": 10, "font_size": 8, "text_distance": 3}
	)
	svg = buf.getvalue().decode("utf-8")
	# Strip the XML prolog so the value embeds cleanly in HTML contexts
	return svg[svg.find("<svg"):]
