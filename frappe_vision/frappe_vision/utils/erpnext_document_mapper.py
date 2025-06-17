import json
import os
from rapidfuzz import process
import frappe


class ERPNextDocumentMapper:
	def __init__(self, doctype: str):
		"""
		:param doctype: Target ERPNext doctype (e.g., 'Purchase Invoice')
		"""
		self.doctype = doctype
		self.config_dir = "/home/kavin/bench-vision/apps/frappe_vision/frappe_vision/config/erpnext_mapper/"
		self.mapping = self._load_mapper_from_file()
		self.item_mapping = self.mapping.pop("items", {}) if "items" in self.mapping else {}
		self.link_fields = self.get_link_fields()
		self.table_link_fields = self.get_link_fields(True)
		print(self.table_link_fields)

	def _load_mapper_from_file(self) -> dict:
		filename = self.doctype.lower().replace(" ", "_") + ".json"
		filepath = os.path.join(self.config_dir, filename)

		if not os.path.exists(filepath):
			raise FileNotFoundError(f"Mapper file not found: {filepath}")

		with open(filepath, "r", encoding="utf-8") as f:
			return json.load(f)

	def get_link_fields(self, is_table=False) -> dict:
		"""
		Fetch all link fields for the doctype using Frappe metadata
		Returns a dictionary of {fieldname: target_doctype}
		"""
		res = {}
		meta = frappe.get_meta(self.doctype)
		if is_table:
			table_fields = meta.get_table_fields()
			for field in table_fields:
				fieldname = field.fieldname
				child_table_meta = frappe.get_meta(meta.get_field(fieldname).options)
				mapped_fields = {}
				for f in child_table_meta.get_link_fields():
					mapped_fields.update({
						f.fieldname: f.get_link_doctype()
					})

				res.update({
					field.fieldname: mapped_fields
				})

		else:
			link_fields = meta.get_link_fields()
			for field in link_fields:
				res.update({
					field.fieldname: field.get_link_doctype()
				})

		return res

	def resolve_link_field(self, value: str, target_doctype: str) -> str:
		"""
		Uses similarity matching to resolve a value to an existing link in target doctype
		"""

		docnames = frappe.db.get_all(target_doctype, pluck="name")
		mapped_candidates = {
			docname.capitalize(): docname
			for docname in docnames
		}

		if docnames:
			match, score = process.extractOne(value.strip().capitalize(), mapped_candidates.keys())
			if score > 70:
				return mapped_candidates.get(match)

		return None

	def map_document(self, normalized_doc: dict) -> dict:
		source_fields = normalized_doc.get("fields", {})
		mapped_doc = {}

		# Map top-level fields
		for target_field, source_key in self.mapping.items():
			value = source_fields.get(source_key, "")

			# Resolve link fields
			if target_field in self.link_fields and value:
				value = self.resolve_link_field(value, self.link_fields.get(target_field))

			mapped_doc[target_field] = value

		# Map child table
		if self.item_mapping and "items" in normalized_doc:
			mapped_doc["items"] = self.map_child_table(normalized_doc["items"], "items")

		return mapped_doc

	def map_child_table(self, item_list: list, fieldname: str) -> list:
		mapped_items = []

		for item in item_list:
			mapped_item = {}
			for target_field, source_key in self.item_mapping.items():
				value = item.get(source_key, "")

				# Resolve link fields
				if fieldname in self.table_link_fields and value:
					for table_fieldname, doctype in self.table_link_fields.get(fieldname).items():
						if target_field == table_fieldname:
							value = self.resolve_link_field(value, doctype)

				mapped_item.update({
					target_field: value
				})

			mapped_items.append(mapped_item)

		return mapped_items

	def validate(self, doc: dict, required_fields: list = None) -> list:
		missing = []
		for field in required_fields or []:
			if not doc.get(field):
				missing.append(field)
		return missing


import os
import json
from pprint import pprint

def test_purchase_invoice_mapper(normalized_invoice=None):
	# Sample normalized output from Frappe Vision
	if not normalized_invoice:
		normalized_invoice = {
			"document_type": "invoice",
			"fields": {
				"invoice_id": "1128B",
				"invoice_date": "09/06/2025",
				"tax_payer_id": "",
				"customer_number": "",
				"account_number": "",
				"vendor_name": "",
				"receiver_name": "UNIVERSAL BUS SERVICES",
				"vendor_address": "THIRUMURUGAN AUTO WINGS\nNO: 109, CENTRE STREET,\nKONDALAMPATTY ROUNDANA,\nSALEM-636 010",
				"receiver_address": "UNIVERSAL BUS SERVICES\n361-3, MGR NAGAR, JAGIR REDDIPATTY,\nMAMANGAM, SALEM, 636302.",
				"order_date": "",
				"due_date": "",
				"delivery_date": "",
				"po_number": "",
				"payment_terms": "Credit",
				"total": 0.0,
				"amount_due": "",
				"amount_paid": "",
				"subtotal": 38100.02,
				"tax": 0.0,
				"service_charge": "",
				"gratuity": "",
				"prior_balance": "",
				"discount": "",
				"shipping_charge": "",
				"vendor_abn_number": "",
				"vendor_gst_number": "33AAAFT7549M1ZR",
				"vendor_pan_number": "AAAFT7549M",
				"vendor_vat_number": "",
				"receiver_abn_number": "",
				"receiver_gst_number": "33AAFFU7373M1ZN",
				"receiver_pan_number": "",
				"receiver_vat_number": "",
				"vendor_phone": "",
				"receiver_phone": "",
				"vendor_url": ""
			},
			"items": [
				{
					"description": "DISC PAD SET VALVO MK3 BS6\nBUS MERITOR",
					"quantity": 3.0,
					"uom": "Set",
					"unit_price": 9921.88,
					"total_price": 38100.02,
					"hsn_code": "87083000"
				}
			]
		}

	# Import your class (assumed it's defined elsewhere)
	mapper = ERPNextDocumentMapper(
		doctype="Purchase Invoice"
	)

	# Run mapping
	mapped_doc = mapper.map_document(normalized_invoice)

	# Print output for inspection
	print("\n🧾 Mapped ERPNext Purchase Invoice Document:")
	pprint(mapped_doc)

	# Validate required fields
	missing = mapper.validate(mapped_doc, required_fields=["supplier", "company", "bill_no"])
	print("\n⚠️ Missing Required Fields:" if missing else "\n✅ All Required Fields Present")
	pprint(missing)
