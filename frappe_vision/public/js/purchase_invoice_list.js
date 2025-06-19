frappe.listview_settings["Purchase Invoice"] = {
	onload: (listview) => {
		const vision_menu = listview.page.add_custom_button_group(__("Vision OCR"));

		listview.page.add_custom_menu_item(vision_menu, __("Upload File"), () => {
			var dialog = new frappe.ui.Dialog({
			title: __("Process Vision OCR"),
			fields: [
				{
					fieldtype: "Attach",
					fieldname: "file",
					label: __("Upload File"),
					reqd: 1
				},

			],
			primary_action: (d) => {
				console.log(d.file);

				var file_path = d.file;
				frappe.call({
					method: "frappe_vision.api.create_purchase_invoice",
					args: {
						file_path: file_path
					},
					freeze: true,
					freeze_msg: __("Processing Vision OCR.."),
					callback: (r) => {
						if (!r.exec) {
							console.log(r.message);

							frappe.set_route("Form", r.message.doctype, r.message.name)
						}
					}
				})
			},
			primary_action_label: __("Create Purchase Invoice")
		});
		dialog.show()
		}
		);
	},
}