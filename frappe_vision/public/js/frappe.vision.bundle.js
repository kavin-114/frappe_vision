
console.log("adasdasdasdasdasd")
frappe.listview_settings['Purchase Invoice'] = {
    onload(listview) {
        console.log(listview);
    }
}
// frappe.listview_settings['Purchase Invoice'] = {
//     // add fields to fetch
//     add_fields: ['title', 'public'],
//     // set default filters
//     filters: [
//         ['public', '=', 1]
//     ],
//     hide_name_column: true, // hide the last column which shows the `name`
//     hide_name_filter: true, // hide the default filter field for the name column
//     onload(listview) {
//         // triggers once before the list is loaded
//     },
//     before_render() {
//         console.log("-----------------")
//     },

//     // set this to true to apply indicator function on draft documents too
//     has_indicator_for_draft: false,

//     get_indicator(doc) {
//         // customize indicator color
//         if (doc.public) {
//             return [__("Public"), "green", "public,=,Yes"];
//         } else {
//             return [__("Private"), "darkgrey", "public,=,No"];
//         }
//     },
//     primary_action() {
//         // triggers when the primary action is clicked
//     },
//     get_form_link(doc) {
//         // override the form route for this doc
//     },
//     // add a custom button for each row
//     button: {
//         show(doc) {
//             return doc.reference_name;
//         },
//         get_label() {
//             return 'View';
//         },
//         get_description(doc) {
//             return __('View {0}', [`${doc.reference_type} ${doc.reference_name}`])
//         },
//         action(doc) {
//             frappe.set_route('Form', doc.reference_type, doc.reference_name);
//         }
//     },
//     // format how a field value is shown
//     formatters: {
//         title(val) {
//             return val.bold();
//         },
//         public(val) {
//             return val ? 'Yes' : 'No';
//         }
//     }
// }

