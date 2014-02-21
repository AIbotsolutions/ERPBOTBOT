# Copyright (c) 2013, Web Notes Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe
from frappe.utils import cint, flt, getdate
from frappe.model.code import get_obj
from frappe import msgprint, throw, _

class DocType:
	def __init__(self, doc, doclist):
		self.doc = doc
		self.doclist = doclist

	def get_emp_list(self):
		"""
			Returns list of active employees based on selected criteria 
			and for which salary structure exists
		"""

		cond = self.get_filter_condition()
		cond += self.get_joining_releiving_condition()

		emp_list = frappe.conn.sql("""
			select emp.name
			from `tabEmployee` emp, `tabSalary Structure` ss 
			where emp.docstatus!=2 and ss.docstatus!=2 
			and emp.name=ss.employee %s""", cond)

		return emp_list

	def get_filter_condition(self):
		self.check_mandatory()
		
		cond = ''
		for f in ['company', 'branch', 'department', 'designation', 'grade']:
			if self.doc.fields.get(f):
				cond += " and emp." + f + " = '" + self.doc.fields.get(f) + "'"

		return cond

	def get_joining_releiving_condition(self):
		m = self.get_month_details(self.doc.fiscal_year, self.doc.month)
		cond = """
			and ifnull(emp.date_of_joining, '0000-00-00') <= '%(month_end_date)s' 
			and ifnull(emp.relieving_date, '2199-12-31') >= '%(month_start_date)s' 
		""" % m
		return cond

	def check_mandatory(self):
		for f in ['company', 'from_date', 'to_date']:
			if not self.doc.fields[f]:
				throw("{select} {field} {proceed}".format(**{
					"select": _("Please select"),
					"field": f.replace("_", " ").title(),
					"proceed": _("to proceed")
				}))

	def create_sal_slip(self):
		"""Creates salary slip for selected employees if already not created"""

		emp_list = self.get_emp_list()
		ss_list = []
		for emp in emp_list:
			if not frappe.conn.sql("""select name from `tabSalary Slip` 
					where docstatus!=2 and employee=%s and company = %s 
					and 
					""", (emp[0], self.doc.company)):
				ss = frappe.bean({
					"doctype": "Salary Slip",
					"employee": emp[0],
					"month": self.doc.month,
					"from_date": self.doc.from_date,
					"to_date": self.doc.to_date,
					"email_check": self.doc.send_email,
					"company": self.doc.company,
				})
				ss.insert()
				ss_list.append(ss.doc.name)

		return self.create_log(ss_list)

	def create_log(self, ss_list):
		log = "<b>No employee for the above selected criteria OR salary slip already created</b>"
		if ss_list:
			log = "<b>Created Salary Slip has been created: </b>\
			<br><br>%s" % '<br>'.join(ss_list)
		return log

	def get_sal_slip_list(self):
		"""
			Returns list of salary slips based on selected criteria
			which are not submitted
		"""
		cond = self.get_filter_condition()
		ss_list = frappe.conn.sql("""select name from `tabSalary Slip` 
			where docstatus=0 and month=%s and fiscal_year=%s %s""", (self.doc.month, 
			self.doc.fiscal_year, cond))

		return ss_list

	def submit_salary_slip(self):
		"""
			Submit all salary slips based on selected criteria
		"""
		ss_list = self.get_sal_slip_list()
		not_submitted_ss = []
		for ss in ss_list:
			ss_obj = get_obj("Salary Slip", ss[0], with_children=1)
			try:
				frappe.conn.set(ss_obj.doc, 'email_check', cint(self.doc.send_mail))
				if cint(self.doc.send_email) == 1:
					ss_obj.send_mail_funct()

				frappe.conn.set(ss_obj.doc, 'docstatus', 1)
			except Exception,e:
				not_submitted_ss.append(ss[0])
				msgprint(e)
				continue

		return self.create_submit_log(ss_list, not_submitted_ss)

	def create_submit_log(self, all_ss, not_submitted_ss):
		log = ''
		if not all_ss:
			log = "No salary slip found to submit for the above selected criteria"
		else:
			all_ss = [d[0] for d in all_ss]

		submitted_ss = list(set(all_ss) - set(not_submitted_ss))		
		if submitted_ss:
			mail_sent_msg = self.doc.send_email and " (Mail has been sent to the employee)" or ""
			log = """
			<b>Submitted Salary Slips%s:</b>\
			<br><br> %s <br><br>
			""" % (mail_sent_msg, '<br>'.join(submitted_ss))

		if not_submitted_ss:
			log += """
				<b>Not Submitted Salary Slips: </b>\
				<br><br> %s <br><br> \
				Reason: <br>\
				May be company email id specified in employee master is not valid. <br> \
				Please mention correct email id in employee master or if you don't want to \
				send mail, uncheck 'Send Email' checkbox. <br>\
				Then try to submit Salary Slip again.
			"""% ('<br>'.join(not_submitted_ss))
		return log

	def get_total_salary(self):
		"""
			Get total salary amount from submitted salary slip based on selected criteria
		"""
		cond = self.get_filter_condition()
		tot = frappe.conn.sql("""select sum(rounded_total) from `tabSalary Slip` 
			where docstatus=1 and month=%s and fiscal_year=%s %s""", (self.doc.month, 
			self.doc.fiscal_year, cond))

		return flt(tot[0][0])

	def get_acc_details(self):
		"""
			get default bank account,default salary acount from company
		"""
		amt = self.get_total_salary()
		default_bank_account = frappe.conn.get_value("Company", self.doc.company, 
			"default_bank_account")
		if not default_bank_account:
			msgprint("You can set Default Bank Account in Company master.")

		return {
			'default_bank_account': default_bank_account,
			'amount': amt
		}