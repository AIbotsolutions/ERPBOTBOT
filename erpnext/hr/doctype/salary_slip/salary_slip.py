# Copyright (c) 2013, Web Notes Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe
from frappe.utils import add_days, cint, cstr, flt, getdate, nowdate, _round
from frappe.model.doc import make_autoname
from frappe.model.bean import getlist
from frappe.model.code import get_obj
from frappe import msgprint, throw, _
from erpnext.setup.utils import get_company_currency
from erpnext.hr.utils import get_period

from erpnext.utilities.transaction_base import TransactionBase

class DocType(TransactionBase):
	def __init__(self,doc,doclist=[]):
		self.doc = doc
		self.doclist = doclist

	def autoname(self):
		self.doc.name = make_autoname('Sal Slip/' + self.doc.employee + '/.#####')

	def get_emp_and_leave_details(self):
		if self.doc.employee:
			self.get_leave_details()
			struct = self.check_sal_struct()
			if struct:
				self.pull_sal_struct(struct)

	def check_sal_struct(self):
		struct = frappe.conn.sql("""select name from `tabSalary Structure` 
			where employee=%s and is_active = 'Yes'""", self.doc.employee)
		if not struct:
			msgprint("Please create Salary Structure for employee '%s'" % self.doc.employee)
			self.doc.employee = None
		return struct and struct[0][0] or ''

	def pull_sal_struct(self, struct):
		from erpnext.hr.doctype.salary_structure.salary_structure import get_mapped_doclist
		self.doclist = get_mapped_doclist(struct, self.doclist)

	def pull_emp_details(self):
		emp = frappe.conn.get_value("Employee", self.doc.employee, 
			["bank_name", "bank_ac_no", "esic_card_no", "pf_number"], as_dict=1)
		if emp:
			self.doc.bank_name = emp.bank_name
			self.doc.bank_account_no = emp.bank_ac_no
			self.doc.esic_no = emp.esic_card_no
			self.doc.pf_no = emp.pf_number

	def get_leave_details(self, lwp=None):
		if not self.doc.from_date and not self.doc.to_date:
			throw(_("Please enter From Date and To Date"))

		period_days = (getdate(self.doc.to_date) - getdate(self.doc.from_date)).days + 1
		holidays = self.get_holidays_for_employee(self.doc.from_date, self.doc.to_date)

		if not cint(frappe.conn.get_value("HR Settings", "HR Settings",
			"include_holidays_in_total_working_days")):
				period_days -= len(holidays)
				if period_days < 0:
					throw(_("Bummer! There are more holidays than working days this period."))

		if not lwp:
			lwp = self.calculate_lwp(holidays, period_days)
		self.doc.total_days_in_month = period_days
		self.doc.leave_without_pay = lwp
		payment_days = flt(self.get_payment_days(period_days)) - flt(lwp)
		self.doc.payment_days = payment_days > 0 and payment_days or 0

	def get_payment_days(self, payment_days):
		emp = frappe.conn.sql("""select date_of_joining, relieving_date from `tabEmployee` 
			where name=%s""", self.doc.employee, as_dict=1)[0]

		if emp['relieving_date']:
			if getdate(emp['relieving_date']) > self.doc.from_date and \
				getdate(emp['relieving_date']) < self.doc.to_date:
					payment_days = getdate(emp['relieving_date']).day
			elif getdate(emp['relieving_date']) < self.doc.from_date:
				throw("{emp} {rel_date}. {status}".format(**{
					"emp": _("Relieving Date of employee is"),
					"rel_date": cstr(emp['relieving_date']),
					"status": _("Please set status of the employee as 'Left'")
				}))

		if emp['date_of_joining']:
			if getdate(emp['date_of_joining']) > self.doc.from_date and \
				getdate(emp['date_of_joining']) < self.doc.to_date:
					payment_days = payment_days - getdate(emp['date_of_joining']).day + 1
			elif getdate(emp['date_of_joining']) > self.doc.from_date:
				payment_days = 0

		return payment_days

	def get_holidays_for_employee(self, from_date, to_date):
		holidays = frappe.conn.sql("""select h.holiday_date 
			from `tabHoliday` h, `tabEmployee` emp 
			where h.parent=emp.holiday_list and emp.name=%s 
			and h.holiday_date between %s and %s""", 
			(self.doc.employee, from_date, to_date))

		period = get_period(self.doc.from_date, self.doc.to_date)[0]
		if not holidays:
			holidays = frappe.conn.sql("""select h.holiday_date 
				from `tabHoliday` h, `tabHoliday List` hl 
				where h.parent=hl.name and ifnull(hl.is_default, 0)=1 
				and hl.period=%s
				and h.holiday_date between %s and %s""", (period, from_date, to_date))

		holidays = [cstr(i[0]) for i in holidays]
		return holidays

	def calculate_lwp(self, holidays, period_days):
		lwp = 0
		for d in range(period_days):
			dt = add_days(cstr(self.doc.from_date), d)
			if dt not in holidays:
				leave = frappe.conn.sql("""select la.name, la.half_day 
					from `tabLeave Application` la, `tabLeave Type` lt 
					where lt.name=la.leave_type and ifnull(lt.is_lwp, 0)=1 
					and la.docstatus=1 and la.employee=%s 
					and %s between from_date and to_date""", (self.doc.employee, dt))
				if leave:
					lwp = cint(leave[0][1]) and (lwp + 0.5) or (lwp + 1)
		return lwp

	def check_existing(self):
		ret_exist = frappe.conn.sql("""select name, from_date, to_date from `tabSalary Slip` 
			where and docstatus!=2 and employee=%s and name!=%s and 
			(from_date not between %s and %s) and 
			(to_date not between %s and %s)""", 
			(self.doc.from_date, self.doc.to_date, self.doc.from_date, self.doc.to_date, 
			self.doc.employee, self.doc.name), as_dict=1)

		if ret_exist:
			self.doc.employee = ''
			throw("{slip}: {emp} {already}: {from_date} to {to_date}".format(**{
				"slip": _("Salary Slip for Employee"),
				"emp": self.doc.employee,
				"already": _("already created for date range"),
				"from_date": ret_exist.from_date,
				"to_date": ret_exist.to_date
			}))

	def validate(self):
		from frappe.utils import money_in_words
		self.check_existing()

		if not (len(self.doclist.get({"parentfield": "earning_details"})) or 
			len(self.doclist.get({"parentfield": "deduction_details"}))):
				self.get_emp_and_leave_details()
		else:
			self.get_leave_details(self.doc.leave_without_pay)

		if not self.doc.net_pay:
			self.calculate_net_pay()

		company_currency = get_company_currency(self.doc.company)
		self.doc.total_in_words = money_in_words(self.doc.rounded_total, company_currency)

	def calculate_earning_total(self):
		self.doc.gross_pay = flt(self.doc.arrear_amount) + flt(self.doc.leave_encashment_amount)
		for d in self.doclist.get({"parentfield": "earning_details"}):
			if cint(d.e_depends_on_lwp) == 1:
				d.e_modified_amount = _round(flt(d.e_amount) * flt(self.doc.payment_days)
					/ cint(self.doc.total_days_in_month), 2)
			elif not self.doc.payment_days:
				d.e_modified_amount = 0
			else:
				d.e_modified_amount = d.e_amount
			self.doc.gross_pay += flt(d.e_modified_amount)

	def calculate_ded_total(self):
		self.doc.total_deduction = 0
		for d in getlist(self.doclist, 'deduction_details'):
			if cint(d.d_depends_on_lwp) == 1:
				d.d_modified_amount = _round(flt(d.d_amount) * flt(self.doc.payment_days) 
					/ cint(self.doc.total_days_in_month), 2)
			elif not self.doc.payment_days:
				d.d_modified_amount = 0
			else:
				d.d_modified_amount = d.d_amount

			self.doc.total_deduction += flt(d.d_modified_amount)

	def calculate_net_pay(self):
		self.calculate_earning_total()
		self.calculate_ded_total()
		self.doc.net_pay = flt(self.doc.gross_pay) - flt(self.doc.total_deduction)
		self.doc.rounded_total = _round(self.doc.net_pay)

	def on_submit(self):
		if(self.doc.email_check == 1):
			self.send_mail_funct()

	def send_mail_funct(self):
		from frappe.utils.email_lib import sendmail

		receiver = frappe.conn.get_value("Employee", self.doc.employee, "company_email")
		if receiver:
			subj = 'Salary Slip: ' + cstr(self.doc.from_date) + ' - ' + cstr(self.doc.to_date)
			earn_ret = frappe.conn.sql("""select e_type, e_modified_amount from 
				`tabSalary Slip Earning` where parent = %s""", self.doc.name)
			ded_ret = frappe.conn.sql("""select d_type, d_modified_amount from 
				`tabSalary Slip Deduction` where parent = %s""", self.doc.name)

			earn_table = ''
			ded_table = ''
			if earn_ret:
				earn_table += "<table cellspacing=5px cellpadding=5px width='100%%'>"

				for e in earn_ret:
					if not e[1]:
						earn_table += '<tr><td>%s</td><td align="right">0.00</td></tr>' % cstr(e[0])
					else:
						earn_table += '<tr><td>%s</td><td align="right">%s</td></tr>' \
							% (cstr(e[0]), cstr(e[1]))
				earn_table += '</table>'

			if ded_ret:
				ded_table += "<table cellspacing=5px cellpadding=5px width='100%%'>"

				for d in ded_ret:
					if not d[1]:
						ded_table +='<tr><td">%s</td><td align="right">0.00</td></tr>' % cstr(d[0])
					else:
						ded_table +='<tr><td>%s</td><td align="right">%s</td></tr>' \
							% (cstr(d[0]), cstr(d[1]))
				ded_table += '</table>'

			letter_head = frappe.conn.get_value("Letter Head", {"is_default": 1, "disabled": 0}, 
				"content")

			msg = '''<div> %s <br>
			<table cellspacing= "5" cellpadding="5"  width = "100%%">
				<tr>
					<td width = "100%%" colspan = "2"><h4>Salary Slip</h4></td>
				</tr>
				<tr>
					<td width = "50%%"><b>Employee Code : %s</b></td>
					<td width = "50%%"><b>Employee Name : %s</b></td>
				</tr>
				<tr>
					<td width = "50%%">From Date: %s</td>
					<td width = "50%%">To Date: %s</td>
				</tr>
				<tr>
					<td width = "50%%">Department : %s</td>
					<td width = "50%%">Branch : %s</td>
				</tr>
				<tr>
					<td width = "50%%">Designation : %s</td>
					<td width = "50%%">Grade : %s</td>
				</tr>
				<tr>
					<td width = "50%%">Bank Account No. : %s</td>
					<td  width = "50%%">Bank Name : %s</td>
				</tr>
				<tr>
					<td  width = "50%%">Arrear Amount : <b>%s</b></td>
					<td  width = "50%%">Payment days : %s</td>
				</tr>
			</table>
			<table border="1px solid #CCC" width="100%%" cellpadding="0px" cellspacing="0px">
				<tr>
					<td colspan = 2 width = "50%%" bgcolor="#CCC" align="center">
						<b>Earnings</b></td>
					<td colspan = 2 width = "50%%" bgcolor="#CCC" align="center">
						<b>Deductions</b></td>
				</tr>
				<tr>
					<td colspan = 2 width = "50%%" valign= "top">%s</td>
					<td colspan = 2 width = "50%%" valign= "top">%s</td>
				</tr>
			</table>
			<table cellspacing= "5" cellpadding="5" width = '100%%'>
				<tr>
					<td width = '25%%'><b>Gross Pay :</b> </td>
					<td width = '25%%' align='right'>%s</td>
					<td width = '25%%'><b>Total Deduction :</b></td>
					<td width = '25%%' align='right'> %s</td>
				</tr>
				<tr>
					<tdwidth='25%%'><b>Net Pay : </b></td>
					<td width = '25%%' align='right'><b>%s</b></td>
					<td colspan = '2' width = '50%%'></td>
				</tr>
				<tr>
					<td width='25%%'><b>Net Pay(in words) : </td>
					<td colspan = '3' width = '50%%'>%s</b></td>
				</tr>
			</table></div>''' % (cstr(letter_head), cstr(self.doc.employee), 
				cstr(self.doc.employee_name), cstr(self.doc.from_date), cstr(self.doc.to_date), 
				cstr(self.doc.department), cstr(self.doc.branch), cstr(self.doc.designation), 
				cstr(self.doc.grade), cstr(self.doc.bank_account_no), cstr(self.doc.bank_name), 
				cstr(self.doc.arrear_amount), cstr(self.doc.payment_days), earn_table, ded_table, 
				cstr(flt(self.doc.gross_pay)), cstr(flt(self.doc.total_deduction)), 
				cstr(flt(self.doc.net_pay)), cstr(self.doc.total_in_words))

			sendmail([receiver], subject=subj, msg = msg)
		else:
			msgprint(_("Company Email ID not found, hence mail not sent"))