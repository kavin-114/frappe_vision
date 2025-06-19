import frappe
from frappe_vision.frappe_vision.services.aws_textract_connector import AWSTextractConnector
from frappe_vision.frappe_vision.utils.vision_output_normalizer import VisionOutputNormalizer
from frappe_vision.frappe_vision.utils.erpnext_document_mapper import ERPNextDocumentMapper


@frappe.whitelist()
def create_purchase_invoice(file_path: str):
	connector = AWSTextractConnector()
	aws_output = connector.analyze_document(file_url=file_path)

	# pass aws output to normalizer
	normalizer = VisionOutputNormalizer(aws_output, 'aws')
	normalized_output = normalizer.normalize()

	# print("Normalized Output", normalized_output)

	mapper = ERPNextDocumentMapper('Purchase Invoice')
	mapped_doc = mapper.map_document(normalized_output)
	mapped_items = []

	if 'items' in mapped_doc:
		mapped_items = mapped_doc.pop('items')


	pi_doc = frappe.new_doc('Purchase Invoice')

	pi_doc.update(mapped_doc)

	for item in mapped_items:
		pi_doc.append('items', item)

	# print(pi_doc.as_dict())

	pi_doc.insert()

	return pi_doc