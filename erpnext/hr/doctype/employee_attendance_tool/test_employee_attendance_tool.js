QUnit.module('hr');

//not added path in tests.txt yet

QUnit.test("Test: Employee attendance tool [HR]", function (assert) {
	assert.expect(0);
	let done = assert.async();
	let attendance_date = farppe.datetime.add_days(frappe.datetime.nowdate(), -1);	// previous day

	frappe.run_serially([
		() => frappe.set_route("Form", "Employee Attendance Tool"),
		() => frappe.timeout(0.5),
		() => assert.equal("Employee Attendance Tool", cur_frm.doctype,
			"Form for Employee Attendance Tool opened successfully."),
 		// set values in form
		() => cur_frm.set_value("date", attendance_date),
		() => cur_frm.set_value("branch", "Branch test"),
		() => cur_frm.set_value("department", "Department test"),
		() => cur_frm.set_value("company", "Company test"),
		() => frappe.click_check('Employee test'),
		() => frappe.tests.click_button('Mark Present'),
		// check if attendance is marked
		() => frappe.set_route("List", "Attendance", "List"),
		() => frappe.timeout(1),
		() => {
			assert.equal("Present", cur_list.data[0].status,
				"attendance status correctly saved");
			assert.equal(attendance_date, cur_list.data[0].attendance_date,
				"attendance date is set correctly");
		}
		() => done()
	]);
});