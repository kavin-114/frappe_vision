import frappe
import json
import re
import pandas as pd
from frappe import _
from frappe_vision.frappe_vision.doctype.vision_log.vision_log import log_vision
from textractor import Textractor
from textractor.data.constants import TextractFeatures
from textractcaller import Query, QueriesConfig
from textractor.entities.document import Document as TextractDocument
from textractor.exceptions import IncorrectMethodException
from textractor.parsers import response_parser

class AWSTextractConnector:
	"""Connector class for AWS Textract OCR processing in Frappe Vision."""

	def __init__(self):
		"""Initialize Textract client with credentials from Vision Settings."""
		self.vision_settings = frappe.get_single("Vision Settings")
		if not self.vision_settings.is_enabled:
			frappe.throw(_("Vision Settings for OCR are not enabled. Please enable them to use AWS Textract."))

		self.session = self.vision_settings.get_aws_textract_session()
		self.client = self.session.client("textract")

		self.extractor = Textractor(
			region_name=self.vision_settings.aws_region,
			textract_client=self.client
		)

		self.queries = [
			"What type of document in following Invoice, Bill, Receipt or Other?",
			"What type of document?",
			"What is the document title?"
		]
		self.document_types = ["Invoice", "Receipt", "Bill"]

	def analyze_document(self, file_url, queries=None):
		"""
		Process a document (image or PDF) using AWS Textract's analyze_document API.

		Args:
			file_url (str): Path to the document (JPEG, PNG, PDF, or TIFF) on the server.

		Returns:
			dict: Extracted data including key-value pairs and tables.

		Throws:
			frappe.exceptions.ValidationError: If processing fails or file is invalid.
		"""
		file = frappe.db.get_value("File", {"file_url": file_url})
		if file:
			self.file_doc = frappe.get_doc("File", file)

		if not self.file_doc.file_type in ['JPG', 'JPEG', 'PNG', 'PDF']:
			frappe.throw(_("Unsupported file format. Allowed: .jpg, .jpeg, .png, .pdf"))

		if queries is not None:
			self.queries.append(queries)

		self.queries_config = QueriesConfig([Query(query) for query in self.queries])
		document: TextractDocument = None
		try:
			file_path = self.file_doc.get_full_path()
			try:
				existing_response = frappe.db.get_value("Vision Log", "mpcvc27527", "response_data")
				document = response_parser.parse(json.loads(existing_response))
				# document = self.extractor.analyze_document(
				# 	file_source=file_path,
				# 	features=[TextractFeatures.QUERIES],
				# 	queries=self.queries_config,
				# 	save_image=True
				# )
			except IncorrectMethodException:
				document = self.extractor.start_document_analysis(
					file_source=file_path,
					features=[TextractFeatures.QUERIES],
					queries=self.queries_config,
					save_image=True
				)
			except Exception:
				raise

			result = self.normalize_textract_document(document, file_path)
			log_vision(
				provider="AWS Textract",
				method="POST",
				status="Success",
				url="analyze_document",
				status_code=200,
				request=None,
				response=json.dumps(document.response if document else "", indent=4)
			)
			return result

		except Exception as e:
			print(frappe.get_traceback())
			frappe.msgprint(_("Unexpected error during Textract processing: {0}").format(str(e)))
			log_vision(
				provider="AWS Textract",
				method="POST",
				status="Failed",
				url="analyze_document",
				status_code=400,
				request=None,
				response=json.dumps(document.response if document else "", indent=4)
			)

	def analyze_expense(self, file_url):
		"""
		Process a document (image or PDF) using AWS Textract's analyze_document API.

		Args:
			file_url (str): Path to the document (JPEG, PNG, PDF, or TIFF) on the server.

		Returns:
			dict: Extracted data including key-value pairs and tables.

		Throws:
			frappe.exceptions.ValidationError: If processing fails or file is invalid.
		"""
		document = None
		file = frappe.db.get_value("File", {"file_url": file_url})
		if file:
			self.file_doc = frappe.get_doc("File", file)

		if not self.file_doc.file_type in ['JPG', 'JPEG', 'PNG', 'PDF']:
			frappe.throw(_("Unsupported file format. Allowed: .jpg, .jpeg, .png, .pdf"))

		try:
			file_path = self.file_doc.get_full_path()
			# for development
			existing_response = frappe.db.get_value("Vision Log", "1q3cmbp39h", "response_data")
			document = response_parser.parse(json.loads(existing_response))

			# document = self.extractor.analyze_expense(
			# 	file_source=file_path,
			# 	save_image=True
			# )
			log_vision(
				provider="AWS Textract",
				method="POST",
				status="Success",
				url="analyze_expense",
				status_code=200,
				request=None,
				response=json.dumps(document.response if document else "", indent=4)
			)
			return document

		except Exception as e:
			frappe.msgprint(_("Unexpected error during Textract processing: {0}").format(str(e)))
			log_vision(
				provider="AWS Textract",
				method="POST",
				status="Failed",
				url="analyze_expense",
				status_code=400,
				request=None,
				response=json.dumps(document.response if document else "", indent=4)
			)

	def get_structured_output_from_document(self, document: TextractDocument):
		"""
		Parse Textract response using amazon-textract-response-parser and textractor.

		Args:
			document (Dict): Raw Textract API response.

		Returns:
			Dict[str, Any]: Structured output with text, tables, and key-value pairs.

		Raises:
			Exception: For parsing errors, logged and returned in output.
		"""
		structured_output = {
			"text": [],
			"tables": [],
			"key_value_pairs": [],
			"query_results": {},
			"errors": []
		}

		try:
			for page in document.pages:
				for line in page.lines:
					if line.text not in structured_output["text"]:
						structured_output["text"].append(line.text)

				for table in page.tables:
					table_data = [[cell.text.strip() for cell in row.cells] for row in table.rows]
					if table_data not in structured_output["tables"]:
						structured_output["tables"].append(table_data)

				for field in page.form.fields:
					key = field.key.text.strip() if field.key else ""
					value = field.value.text.strip() if field.value else ""
					kv_pair = {"key": key, "value": value}
					if kv_pair not in structured_output["key_value_pairs"]:
						structured_output["key_value_pairs"].append(kv_pair)

			structured_output["query_results"] = self.parse_queryies_from_doc(document.queries)
			log_vision(
				provider="AWS Textract",
				method="POST",
				status="Success",
				url="parse_textract_response",
				status_code=200,
				request=None,
				response=json.dumps(structured_output, indent=4)
			)
			return structured_output

		except Exception as e:
			error_msg = f"Error parsing Textract response: {str(e)} {frappe.get_traceback()}"
			structured_output["errors"].append(error_msg)
			return structured_output

	def get_standard_output_from_expense(self, document: TextractDocument):
		"""
		Parse document object and structure a standard key value pairs from expense document

		Args:
			document (Textract Document): Textract Expense Document

		Returns:
			Dict[str, any]: Structured output with primary fields and line item lists.
		"""
		res = {}
		primary_field_groups = {}
		line_items = []

		expense_doc = document.expense_documents[0]
		line_item_group = expense_doc.line_items_groups[0].to_pandas()
		df = pd.DataFrame(line_item_group)
		df_records = df.to_dict('records')

		normalized_fields = self.get_normalized_primary_fields(expense_doc.summary_fields_list)
		primary_fields = normalized_fields.get("primary_fields")

		# # tax normalization
		# if "tax" in primary_fields and isinstance(primary_fields["tax"], list):
		# 	tax = self.normalize_tax_fields(primary_fields["tax"])
		# 	primary_fields["total_tax_rate"] = tax.get("total_percent")
		# 	primary_fields["total_tax_amount"] = tax.get("total_amount")

		for row in df_records:
			item_row = {}
			for key, value in row.items():
				field = key.lower()

				item_row.update({
					field: value
				})

				if field == 'quantity':
					qty_and_uom = self.get_qty_and_uom(value)
					if not qty_and_uom:
						continue
					item_row.update({
						field: qty_and_uom.get(field),
						"uom": qty_and_uom.get('uom')
					})

			line_items.append(item_row)

		res = {
			"field_groups": primary_field_groups,
			"fields": primary_fields,
			"items": line_items,
			"under_confidence_values": normalized_fields.get("under_confidence_values"),
			"document": document
		}

		return res

	def normalize_tax_fields(self, tax_entries: list) -> dict:
		tax = {
			"cgst_percent": 0.0,
			"sgst_percent": 0.0,
			"igst_percent": 0.0,
			"total_percent": 0.0,
			"cgst_amount": 0.0,
			"sgst_amount": 0.0,
			"igst_amount": 0.0,
			"total_amount": 0.0
		}
		for entry in tax_entries:
			for raw_label, raw_value in entry.items():
				label = raw_label.lower()
				value = self._try_parse_value(raw_value)
				if re.search(r"sgst.*%", label):
					tax["sgst_percent"] = value
				elif re.search(r"cgst.*%", label):
					tax["cgst_percent"] = value
				elif re.search(r"igst.*%", label):
					tax["igst_percent"] = value
				elif re.search(r"net.*%|total.*%", label):
					tax["total_percent"] = value
				elif re.search(r"sgst.*amt|sgst.*amount", label):
					tax["sgst_amount"] = value
				elif re.search(r"cgst.*amt|cgst.*amount", label):
					tax["cgst_amount"] = value
				elif re.search(r"igst.*amt|igst.*amount", label):
					tax["igst_amount"] = value
				elif re.search(r"net.*amt|total.*amt|tax.*amt", label):
					tax["total_amount"] = max(tax["total_amount"], value)
		return tax

	def _try_parse_value(self, val):
		try:
			return float(re.sub(r"[^\d.]+", "", val))
		except:
			return val.strip()

	def get_normalized_primary_fields(self, summary_fields_list:list):
		primary_fields = {}
		under_confidence_fields = {}

		for row in summary_fields_list:
			key = row.type.text.lower()
			value = row._value.text
			confidence = row._value.confidence

			if row._currency and not "currency" in primary_fields:
				primary_fields.update({
					"currency": row._currency
				})

			if key == 'other' and row._key:
				label_name = self._sanitize_the_text(row._key)

				if not 'other' in primary_fields:
					primary_fields['other'] = []

				primary_fields['other'].append({
					label_name: value
				})

				continue

			if key == 'tax' and row._key:
				label_name = self._sanitize_the_text(row._key)

				if not 'tax' in primary_fields:
					primary_fields['tax'] = []

				primary_fields['tax'].append({
					label_name: value
				})

				continue

			if key in primary_fields:
				if label_name:= row._key:

					key = (key + '_' + self._sanitize_the_text(label_name))


			key = key.replace(":", "").strip()

			if key in primary_fields and primary_fields.get(key) == value:
				print(primary_fields.get(key))
				continue

			if confidence > 75:
				primary_fields.update({
					key: value
				})
			else:
				under_confidence_fields.update({
					key: {
						'value': value,
						'confidence': confidence
					}
				})

		return {"primary_fields": primary_fields, "under_confidence_fields": under_confidence_fields}

	def _sanitize_the_text(self, value):
		return (value.text.lower()
				.replace(":", "").strip().replace(" ", "_")
				.replace("/", "").replace(".", ""))

	# def _group_common_values(self, )

	def _get_key_value_from_list_values(self, parent_key, values):
		res = {}
		existing_keys = {}

		for field in values:
			key = field.key.text if field.key else parent_key
			value = field.value.text
			if (key in existing_keys) and (value == existing_keys.get(key)):
				res.update({parent_key: value})
			else:
				res.update({key: value})
				existing_keys[key] = value

		return res

	def get_qty_and_uom(self, value):
		res = {}
		match = re.match(r'(\d+\.?\d*)\s*(\w+)', value)
		if match:
			quantity = float(match.group(1))
			uom = match.group(2).capitalize()
			res.update({"quantity": quantity, "uom": uom})

		return res

	def parse_queryies_from_doc(self, queries):
		"""
		Parse query blocks from Textract Document Object.

		Args:
			queries (list): List of Queries containing query results and query.

		Returns:
			list: Parsed query results.
		"""
		query_results = {}
		for query in queries:
			if query.result:
				query_results[query.query] = {
					"answer": query.result.answer,
					"confidence": query.result.confidence
				}
			else:
				query_results[query.query] = {}
		return query_results

	def normalize_textract_document(self, document: TextractDocument, file_path: str):
		"""
		Normalize Textract document to a standard format.

		Args:
			document (Document Object): Parsed Textract document.

		Returns:
			Document Object: Normalized Textract document.
		"""
		document_type = self.get_document_type(document)
		if document_type in self.document_types:
			expense_doc = self.analyze_expense(
				file_url=file_path
			)
			return self.get_standard_output_from_expense(expense_doc)
		else:
			return self.get_structured_output_from_document(document)

	def get_document_type(self, document: TextractDocument):
		"""
		Determine the type of document based on its content.

		Args:
			document (Document Object): Parsed Textract document.

		Returns:
			str: Document type (e.g., "Invoice", "Receipt", etc.).
		"""
		type = None
		for query in document.queries:
			if query.result:
				if str(query.result.answer).capitalize() in self.document_types:
					type = str(query.result.answer).capitalize()
			else:
				type = "Other"
		return type

def test_aws_analyze_document():
	"""Test function to analyze a document using AWS Textract."""
	connector = AWSTextractConnector()
	file_url = "/files/auto wings bill.pdf"
	try:
		result = connector.analyze_document(file_url)
		frappe.log_error(title="Textract Analysis Result:", message=result)
		return result
	except Exception as e:
		print("Textract Analysis Error", frappe.get_traceback())
		frappe.log_error(title="Textract Analysis Error:", message=frappe.get_traceback())