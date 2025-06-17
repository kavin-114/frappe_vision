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
		primary_fields = {}
		primary_field_groups = {}
		line_items = []
		under_confidence_fields = {}

		expense_doc = document.expense_documents[0]
		line_item_group = expense_doc.line_items_groups[0].to_pandas()
		df = pd.DataFrame(line_item_group)
		df_records = df.to_dict('records')

		for key, value in expense_doc.summary_fields.items():
			field = key.lower()

			if len(value) == 1:
				answer = value[0].value.text
				confidence = value[0].value.confidence

				if confidence > float(75):
					primary_fields.update({
						field : answer
					})
				else:
					under_confidence_fields.update({
						field: {
							"value": answer,
							"confidence": confidence
						}
					})
			elif len(value) == 2:
				primary_fields.update(self._get_key_value_from_list_values(field, value))
			else:
				primary_field_groups.update({
					field : self._structure_field_groups(field, value)
				})


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
			"under_confidence_values": under_confidence_fields,
			"document": document
		}

		return res

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

	# def _structure_field_groups(self, input_list):
	# 	structured_dict = {}
	# 	key_counts = {}

	# 	for item in input_list:
	# 		if ':' in str(item):
	# 			item_key, item_value = str(item).split(':', 1)
	# 			# Clean up the item_key by removing unwanted characters and spaces
	# 			item_key = item_key.strip().replace('(', '').replace(')', '').replace(':', '').replace('/', '_').replace(' ', '_').lower()
	# 			item_value = item_value.strip()

	# 			# Check if the key already exists in the dictionary
	# 			if item_key in key_counts:
	# 				# Increment the count and append it to the key
	# 				key_counts[item_key] += 1
	# 				item_key = f"{item_key}_{key_counts[item_key]}"
	# 			else:
	# 				# Initialize the count for the key
	# 				key_counts[item_key] = 1

	# 			# Use the cleaned item_key as the key in the dictionary
	# 			structured_dict[item_key] = item_value

	# 	return structured_dict

	def _structure_field_groups(self, parent_key, values):
		res = {}
		key_counts = {}
		for field in values:
		# item_key, item_value = str(item).split(':', 1)
		# Clean up the item_key by removing unwanted characters and spaces
			item_key = field.key.text if field.key else parent_key
			item_key = item_key.strip().replace('(', '').replace(')', '').replace(':', '').replace('/', '_').replace(' ', '_').lower()
			item_value = field.value.text.strip()
			confidence = field.value.confidence

			# Check if the key already exists in the dictionary
			if item_key in key_counts:
				# Increment the count and append it to the key
				key_counts[item_key] += 1
				item_key = f"{item_key}_{key_counts[item_key]}"
			else:
				# Initialize the count for the key
				key_counts[item_key] = 1

			# Use the cleaned item_key as the key in the dictionary
			if confidence > float(75):
				res[item_key] = item_value
			else:
				res[item_key] = {
					"value": item_value,
					"confidence": confidence
				}

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




def _structure_field_groups(input_list):
		structured_dict = {}
		key_counts = {}

		for item in input_list:
			if ':' in item:
				item_key, item_value = item.split(':', 1)
				# Clean up the item_key by removing unwanted characters and spaces
				item_key = item_key.strip().replace('(', '').replace(')', '').replace(':', '').replace('/', '_').replace(' ', '_').lower()
				item_value = item_value.strip()

				# Check if the key already exists in the dictionary
				if item_key in key_counts:
					# Increment the count and append it to the key
					key_counts[item_key] += 1
					item_key = f"{item_key}_{key_counts[item_key]}"
				else:
					# Initialize the count for the key
					key_counts[item_key] = 1

				# Use the cleaned item_key as the key in the dictionary
				structured_dict[item_key] = item_value

		return structured_dict