import re
import os
import json
from typing import Dict, Any, List

class VisionOutputNormalizer:
	def __init__(self, raw_output: Dict[str, Any], service: str):
		self.raw_output = raw_output
		self.service = service
		self.mapper = self._load_mapper(service)

	def _load_mapper(self, service):
		file_name = ''
		if service == 'aws':
			file_name = 'aws_invoice_mapper.json'

		path = os.path.join(f"/home/kavin/bench-vision/apps/frappe_vision/frappe_vision/config/ocr_mapper/{file_name}")

		with open(path, 'r') as f:
			return json.load(f)

	def normalize(self) -> Dict[str, Any]:
		if self.service == "aws":
			return self._normalize_generic()
		else:
			raise ValueError(f"Unsupported service: {self.service}")

	def _get_value_from_path(self, data: dict, path: str):
		keys = path.split('.')
		value = data
		try:
			for key in keys:
				if isinstance(value, list):
					value = value[int(key)] if key.isdigit() and int(key) < len(value) else {}
				elif isinstance(value, dict):
					lower_keys = {k.lower(): v for k, v in value.items()}
					value = lower_keys.get(key.lower(), {})
				else:
					return ""
			if isinstance(value, dict):
				return ""
			return value
		except (KeyError, IndexError, TypeError, ValueError):
			return ""

	def _get_with_fallback(self, field_key: str) -> Any:
		value = self._get_value_from_path(self.raw_output, f"fields.{field_key}")
		if value:
			return value
		value = self._get_value_from_path(self.raw_output, f"field_groups.{field_key}.0")
		return value

	def _normalize_generic(self):
		normalized = {"document_type": "invoice", "fields": {}, "items": []}
		mapping = self.mapper.get("fields", {})

		for target_field, source_path in mapping.items():
			source_key = source_path.split('.')[-1]
			value = self._get_with_fallback(source_key)
			normalized["fields"][target_field] = self._parse_amount(value) if target_field in ['subtotal', 'tax', 'total'] else value

		items_conf = self.mapper.get("items", {})
		item_path = items_conf.get("path", "items")
		item_mapping = items_conf.get("mapping", {})
		raw_items = self._get_value_from_path(self.raw_output, item_path) or []

		for item in raw_items:
			new_item = {}
			item_lower = {k.lower(): v for k, v in item.items()}
			for target_field, source_field in item_mapping.items():
				value = item_lower.get(source_field.lower(), "")
				if not value:
					value = self._get_with_fallback(source_field.lower())
				new_item[target_field] = self._parse_amount(value) if target_field in ['unit_price', 'total_price'] else value

			# Auto calculate missing total_price if possible
			if not new_item.get("total_price") and new_item.get("unit_price") and new_item.get("quantity"):
				try:
					new_item["total_price"] = round(float(new_item["unit_price"]) * float(new_item["quantity"]), 2)
				except Exception:
					new_item["total_price"] = 0.0
			normalized["items"].append(new_item)

		# Auto calculate subtotal if missing
		if not normalized["fields"].get("subtotal") or normalized["fields"]["subtotal"] == 0.0:
			subtotal = sum(item.get("total_price", 0.0) for item in normalized["items"])
			normalized["fields"]["subtotal"] = round(subtotal, 2)

		return normalized

	def _parse_amount(self, value: Any) -> float:
		if not value or not isinstance(value, str):
			return 0.0
		cleaned_value = re.sub(r'[^\d.,]', '', value)
		cleaned_value = cleaned_value.replace(',', '')
		try:
			return float(cleaned_value)
		except ValueError:
			return 0.0

# if __name__ == "__main__":
# 	raw_output = {
# 		'field_groups': {
# 			'vendor_name': ["VENDOR_NAME: THIRUMURUGAN AUTO WINGS"],
# 			'name': ["NAME: UNIVERSAL BUS SERVICES"]
# 		},
# 		'fields': {
# 			'invoice_receipt_id': '1128b',
# 			'invoice_receipt_date': '09/06/2025',
# 			'vendor_gst_number': '33aaaft7549m1zr',
# 			'receiver_name': 'universal bus services',
# 			'receiver_address': 'universal bus services\n361-3, mgr nagar, jagir reddipatty,\nmamangam, salem, 636302.',
# 			'subtotal': '38100.02 [inr]'
# 		},
# 		'items': [
# 			{
# 				'item': 'DISC PAD SET VALVO MK3 BS6\nBUS MERITOR',
# 				'quantity': 3.0,
# 				'product_code': '87083000',
# 				'uom': 'Set',
# 				'unit_price': '9921.88'
# 				# 'price' is intentionally missing to test auto-calculation
# 			}
# 		]
# 	}

# 	normalizer = VisionOutputNormalizer(raw_output, service="aws")
# 	normalized_output = normalizer.normalize()
# 	print(json.dumps(normalized_output, indent=2))

def test_vision_output_normalizer(raw_output=None):
	if raw_output is None:
		raw_output = {
			'field_groups': {
				'vendor_name': ["VENDOR_NAME: THIRUMURUGAN AUTO WINGS"],
				'name': ["NAME: UNIVERSAL BUS SERVICES"]},
				'fields': {
					'invoice_receipt_id': '1128b',
					'invoice_receipt_date': '09/06/2025',
					'vendor_gst_number': '33aaaft7549m1zr',
					'receiver_name': 'universal bus services',
					'receiver_address': 'universal bus services\n361-3, mgr nagar, jagir reddipatty,\nmamangam, salem, 636302.', 'subtotal': '38100.02 [inr]',
					'vendor_address': 'thirumurugan auto wings\\nno'
				}, 'items': [
					{
						'item': 'DISC PAD SET VALVO MK3 BS6\nBUS MERITOR',
						'quantity': 3.0,
						'product_code': '87083000',
						'uom': 'Set',
						'unit_price':
						'9921.88'
					}
				]}

	normalizer = VisionOutputNormalizer(raw_output, service="aws")
	normalized_output = normalizer.normalize()
	print(json.dumps(normalized_output, indent=2))
	return normalized_output