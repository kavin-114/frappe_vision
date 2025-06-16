# Copyright (c) 2025, Aerele Technologies Private Limited and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class VisionLog(Document):
	pass

def log_vision(provider, url, status_code, status, method, request, response, defer_insert=False):
	"""Log Vision API calls and responses."""
	doc = frappe.get_doc(
		doctype="Vision Log",
		ocr_provider=provider,
		url=url,
		http_status_code=status_code,
		status=status,
		method=method,
		request_data=request,
		response_data=response
	)
	if defer_insert:
		doc.deferred_insert()
	else:
		doc.insert(ignore_permissions=True)