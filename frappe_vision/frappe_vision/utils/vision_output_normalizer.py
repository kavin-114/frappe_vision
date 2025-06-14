import frappe
import json
from fuzzywuzzy import process
from typing import Dict, List, Any
from datetime import datetime
import logging

class VisionOutputNormalizer:
	"""Class to normalize extracted OCR data into standard format using Vision Template."""

	def __init__(self):
		"""Initialize logger and allowed document types."""
		self.logger = logging.getLogger(__name__)
		self.allowed_types = [
			"Sales Invoice", "Purchase Invoice", "Receipt", "Bill",
			"Delivery Note", "Payment Receipt", "Credit Note", "Debit Note"
		]

	def normalize(self, structured_output: Dict[str, Any], document_type: str = None) -> Dict[str, Any]:
		"""
		Normalize extracted data into standard format based on Vision Template.

		Args:
			structured_output (Dict): Output from OCR connector (e.g., AWSTextractConnector).
			document_type (str, optional): Document type. If None, use query_results.

		Returns:
			Dict: Standardized data format.
		"""
		standard_output = {
			"document_type": document_type or "",
			"data": {},
			"items": [],
			"confidence_scores": {},
			"errors": []
		}

		# Determine document type from query results if not provided
		if not document_type:
			for result in structured_output.get("query_results", {}).values():
				if "document type" in result["query_text"].lower():
					standard_output["document_type"] = result["query_answer"]
					break

		# Validate document type
		if standard_output["document_type"] not in self.allowed_types:
			standard_output["errors"].append(f"Invalid document type: {standard_output['document_type']}")
			return standard_output

		# Load Vision Template
		try:
			template = frappe.get_doc("Vision Template", {
				"document_type": standard_output["document_type"],
				"is_enabled": 1
			})
		except frappe.DoesNotExistError:
			standard_output["errors"].append(f"No enabled Vision Template found for {standard_output['document_type']}")
			return standard_output

		# Prepare field mappings
		field_mappings = {row.standard_field: {
			"aliases": json.loads(row.aliases),
			"required": row.required,
			"data_type": row.data_type,
			"default_value": row.default_value
		} for row in template.field_mappings}

		# Normalize key-value pairs
		for pair in structured_output.get("key_value_pairs", []):
			key = pair["key"]
			value = pair["value"]
			confidence = pair.get("confidence", 0.0)
			best_match, score = process.extractOne(
				key.lower(),
				[alias.lower() for mappings in field_mappings.values() for alias in mappings["aliases"]]
			)
			if score >= 80:  # Fuzzy matching threshold
				for standard_field, mapping in field_mappings.items():
					if best_match.lower() in [a.lower() for a in mapping["aliases"]]:
						try:
							value = self._validate_and_convert(value, mapping["data_type"])
							standard_output["data"][standard_field] = value
							standard_output["confidence_scores"][standard_field] = confidence
						except ValueError as e:
							standard_output["errors"].append(f"Invalid {standard_field}: {value} ({str(e)})")

		# Extract items from tables
		item_mappings = {row.item_field: {
			"aliases": json.loads(row.item_aliases),
			"required": row.required,
			"data_type": row.item_data_type,
			"default_value": row.default_value
		} for row in template.child_template}
		for table in structured_output.get("tables", []):
			if len(table) > 1:  # Assume first row is header
				headers = [h.lower() for h in table[0]]
				for row in table[1:]:
					item = {}
					for i, value in enumerate(row):
						header = headers[i] if i < len(headers) else ""
						for standard_field, mapping in item_mappings.items():
							if header in [a.lower() for a in mapping["aliases"]]:
								try:
									value = self._validate_and_convert(value, mapping["data_type"])
									item[standard_field] = value
								except ValueError as e:
									standard_output["errors"].append(f"Invalid item {standard_field}: {value} ({str(e)})")
					if item.get("item_description") or item.get("item_code"):
						standard_output["items"].append(item)

		# Apply default values for missing fields
		for standard_field, mapping in field_mappings.items():
			if standard_field not in standard_output["data"]:
				standard_output["data"][standard_field] = mapping["default_value"]

		# Validate required fields
		for standard_field, mapping in field_mappings.items():
			if mapping["required"] and not standard_output["data"].get(standard_field):
				standard_output["errors"].append(f"Missing required field: {standard_field}")

		self.logger.info(f"Normalized output for {standard_output['document_type']}")
		return standard_output

	def _validate_and_convert(self, value: str, data_type: str) -> Any:
		"""
		Validate and convert value to the specified data type.

		Args:
			value (str): Raw value from OCR.
			data_type (str): Target data type (String, Date, Float, Integer, JSON).

		Returns:
			Any: Converted value.

		Raises:
			ValueError: If conversion fails.
		"""
		if not value:
			return value

		if data_type == "Date":
			try:
				# Support common date formats
				for fmt in ["%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]:
					try:
						return datetime.strptime(value, fmt).date().isoformat()
					except ValueError:
						continue
				raise ValueError("Invalid date format")
			except ValueError as e:
				raise ValueError(f"Cannot parse date: {value}")
		elif data_type == "Float":
			return float(value.replace(",", "").replace("₹", "").strip())
		elif data_type == "Integer":
			return int(value.replace(",", "").strip())
		elif data_type == "JSON":
			return json.loads(value)
		return value  # String or other types