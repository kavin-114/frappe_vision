# Copyright (c) 2025, Aerele Technologies Private Limited and contributors
# For license information, please see license.txt

import boto3.session
import frappe
import boto3
from frappe.model.document import Document


class VisionSettings(Document):
	def validate(self):
		if not self.is_enabled:
			return

		if self.ocr_provider == "AWS Textract":
			self.test_aws_connection()

	@frappe.whitelist()
	def test_aws_connection(self):
		try:
			if not (self.aws_access_key_id and self.aws_secret_access_key and self.aws_region):
				frappe.throw("AWS Access Key ID, Secret Access Key, and Region are required for Textract integration.")

			# Initialize Textract client to verify service connectivity
			textract_client = boto3.client(
				'textract',
				aws_access_key_id=self.aws_access_key_id,
				aws_secret_access_key=self.get_password("aws_secret_access_key"),
				region_name=self.aws_region
			)

			adapters = textract_client.list_adapters()

			frappe.msgprint("AWS Textract connection successful.", alert=True, indicator='green')

		except Exception as e:
			frappe.msgprint(title="AWS Textract connection failed", msg=f"Failed to connect to AWS: {str(e)}", indicator='red')

	def get_aws_textract_session(self):
		"""Get AWS Textract client"""
		self.validate()
		return boto3.session.Session(
			aws_access_key_id=self.aws_access_key_id,
			aws_secret_access_key=self.get_password("aws_secret_access_key"),
			region_name=self.aws_region,
		)