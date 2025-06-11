import frappe
import json
from botocore.exceptions import ClientError, NoCredentialsError, EndpointConnectionError
from frappe import _
from frappe_vision.frappe_vision.doctype.vision_log.vision_log import log_vision
from trp.t_pipeline import add_kv_ocr_confidence
from trp import Document as TextractDocument
import trp.trp2 as t2

class AWSTextractConnector:
	"""Connector class for AWS Textract OCR processing in Frappe Vision."""

	def __init__(self):
		"""Initialize Textract client with credentials from Vision Settings."""
		self.vision_settings = frappe.get_single("Vision Settings")
		if not self.vision_settings.is_enabled:
			frappe.throw(_("Vision Settings for OCR are not enabled. Please enable them to use AWS Textract."))

		self.client = self.vision_settings.get_aws_client()

	def analyze_document(self, file_url):
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

		try:
			# Read file as raw bytes (no base64 encoding needed with boto3)
			file_content = self.file_doc.get_content()

			#testingpurpose
			response = frappe.db.get_value("Vision Log", "f9ujfuink0", "response_data")
			response = json.loads(response)

			# Format request for analyze_document
			# response = self.client.analyze_document(
			# 	Document={
			# 		'Bytes': file_content
			# 	},
			# 	FeatureTypes=['FORMS', 'TABLES', 'QUERIES'],
			# 	QueriesConfig={
			# 		'Queries': [
			# 			{
			# 				'Text': 'What is type of document in following Invoice, Bill or Receipt?',
			# 			}
			# 		]
			# 	}
			# )
			print("Successfully analyzed document with AWS Textract", response)
			log_vision(provider="AWS Textract", method="POST", status="Success", url="analyze_document", status_code=200, request=None, response=json.dumps(response, indent=4))
			return response

		except Exception as e:
			print("Error during Textract document analysis:", str(e))
			frappe.msgprint(_("Unexpected error during Textract processing: {0}").format(str(e)))
			log_vision(provider="AWS Textract", method="POST", status="Failed", url="analyze_document", status_code=400, request=None, response=json.dumps(response, indent=4))


	def parse_textract_response(self, response):
		"""
		Parse Textract response using amazon-textract-response-parser and textractor.

		Args:
			response (Dict): Raw Textract API response.
			file_content (bytes): Raw bytes of the document.

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
			# Parse with amazon-textract-response-parser
			t_document: t2.TDocument = t2.TDocumentSchema().load(response)
			t_document = add_kv_ocr_confidence(t_document)
			doc = TextractDocument(t2.TDocumentSchema().dump(t_document))

			for page in doc.pages:
				# Add unique text
				for line in page.lines:
					if line.text not in structured_output["text"]:
						structured_output["text"].append(line.text)

				# Add unique tables
				for table in page.tables:
					table_data = [[cell.text.strip() for cell in row.cells] for row in table.rows]
					if table_data not in structured_output["tables"]:
						structured_output["tables"].append(table_data)

				# Add unique key-value pairs
				for field in page.form.fields:
					key = field.key.text.strip() if field.key else ""
					value = field.value.text.strip() if field.value else ""
					kv_pair = {"key": key, "value": value}
					if kv_pair not in structured_output["key_value_pairs"]:
						structured_output["key_value_pairs"].append(kv_pair)

			# Parse query results
			structured_output["query_results"] = self.parse_query_block(response.get("Blocks", []))
			print("Successfully parsed Textract response")
			log_vision(provider="AWS Textract", method="POST", status="Success", url="parse_textract_response", status_code=200, request=None, response=json.dumps(structured_output, indent=4))

			return structured_output

		except Exception as e:
			error_msg = f"Error parsing Textract response: {str(e)} {frappe.get_traceback()}"
			structured_output["errors"].append(error_msg)
			return structured_output

	def parse_query_block(self, blocks):
		"""
		Parse query blocks from Textract response.

		Args:
			blocks (list): List of Textract blocks containing queries.

		Returns:
			list: Parsed query results.
		"""
		query_results = {}

		for block in blocks:
			if block.get("BlockType") == "QUERY" and block.get("Relationships"):
				query_text = block.get("Query", "").get("Text", "")
				for answer in block.get("Relationships", []):
					if answer.get("Type") == "ANSWER":
						for answer_id in answer.get("Ids", []):
							if answer_id not in query_results:
								query_results[answer_id] = {
									"query_text": query_text,
									"query_answer": ""
								}
							else:
								# If already exists, just update the text
								query_results[answer_id]["query_text"] = query_text

			elif block.get("BlockType") == "QUERY_RESULT":
				if block.get("Id") in query_results:
					query_results[block.get("Id")]["query_answer"] = block.get("Text", "")
				else:
					query_results[block.get("Id")] = {
						"query_text": "",
						"query_answer": block.get("Text", "")
					}

		return query_results


def test_aws_analyze_document():
	"""Test function to analyze a document using AWS Textract."""
	connector = AWSTextractConnector()
	file_url = "/files/Grandmall casio Watch GST Invoice-10.02.2025-1.pdf"

	try:
		result = connector.analyze_document(file_url)
		structured_result = connector.parse_textract_response(result)

		print("Textract Analysis Result:", structured_result)
	except Exception as e:
		print("Error during Textract analysis:", str(e))