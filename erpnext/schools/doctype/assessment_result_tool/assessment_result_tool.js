// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

cur_frm.add_fetch("assessment_plan", "student_group", "student_group");

frappe.ui.form.on('Assessment Result Tool', {
	refresh: function(frm) {
		frm.trigger("assessment_plan");
		if (frappe.route_options) {
			frm.set_value("student_group", frappe.route_options.student_group);
			frm.set_value("assessment_plan", frappe.route_options.assessment_plan);
			frappe.route_options = null;
		}
		frm.disable_save();
		frm.page.set_primary_action(__("Submit"), function() {
			frm.events.make_result(frm)
		});
		frm.page.clear_indicator();
	},

	assessment_plan: function(frm) {
		if(!frm.doc.student_group) return;
		frappe.call({
			method: "erpnext.schools.api.get_assessment_students",
			args: {
				"assessment_plan": frm.doc.assessment_plan,
				"student_group": frm.doc.student_group
			},
			callback: function(r) {
				frm.doc.students = r.message;
				frm.events.render_table(frm);
			}
		});
	},

	render_table: function(frm) {
		$(frm.fields_dict.result_html.wrapper).empty();
		let assessment_plan = frm.doc.assessment_plan;
		frappe.call({
			method: "erpnext.schools.api.get_assessment_details",
			args: {
				assessment_plan: assessment_plan
			},
			callback: function(r) {
				frm.events.get_marks(frm, r.message);
			}
		});
	},

	get_marks: function(frm, criteria_list) {
		let max_total_score = 0;
		criteria_list.forEach(function(c) {
			max_total_score += c.maximum_score
		});
		var result_table = $(frappe.render_template('assessment_result_tool', {
			frm: frm,
			students: frm.doc.students,
			criteria: criteria_list,
			max_total_score: max_total_score
		}));
		result_table.appendTo(frm.fields_dict.result_html.wrapper);

		result_table.on('change', 'input', function(e) {
			let $input = $(e.target);
			let student = $input.data().student;
			let max_score = $input.data().maxScore;
			let value = $input.val();
			if(value < 0) {
				$input.val(0);
			} else if(value > max_score) {
				$input.val(max_score);
			}
			let total_score = 0;
			let student_scores = {};
			student_scores["assessment_details"] = {}
			result_table.find(`input[data-student=${student}].student-result-data`)
				.each(function(el, input) {
					let $input = $(input);
					let criteria = $input.data().criteria;
					let value = parseFloat($input.val());
					if (value) {
						student_scores["assessment_details"][criteria] = value;
					}
					total_score += value;
			});
			if(!Number.isNaN(total_score)) {
				result_table.find(`span[data-student=${student}].total-score`).html(total_score);
			}
			if (Object.keys(student_scores["assessment_details"]).length === criteria_list.length) {
				student_scores["student"] = student;
				student_scores["total_score"] = total_score;
				result_table.find(`[data-student=${student}].result-comment`)
					.each(function(el, input){
					student_scores["comment"] = $(input).val();
				});
				frappe.call({
					method: "erpnext.schools.api.mark_assessment_result",
					args: {
						"assessment_plan": frm.doc.assessment_plan,
						"scores": student_scores
					},
					callback: function(r) {
						let assessment_result = r.message;
						for (var criteria of Object.keys(assessment_result.details)) {
							result_table.find(`[data-criteria=${criteria}][data-student=${assessment_result
								.student}].student-result-grade`).each(function(e1, input) {
									$(input).html(assessment_result.details[criteria]);
							});
						}
						result_table.find(`span[data-student=${assessment_result.student}].total-score-grade`).html(assessment_result.grade);
					}
				});
			}
		});
	},

	make_result: function(frm) {
		frappe.call({
			method: "erpnext.schools.api.mark_assessment_result",
			args: {
				"assessment_plan": frm.doc.assessment_plan,
				"scores": student_scores
			},
			callback: function(r) {
				console.log(r);
			}
		});
	}

});
