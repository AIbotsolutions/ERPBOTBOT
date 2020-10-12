# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import json
from six import iteritems
from frappe import _, scrub
from frappe.utils import getdate, flt
from erpnext.accounts.utils import get_fiscal_year
from erpnext.stock.report.stock_analytics.stock_analytics import get_period_date_ranges

def execute(filters=None):
	return IssueSummary(filters).run()

class IssueSummary(object):
	def __init__(self, filters=None):
		"""Issue Summary Report"""
		self.filters = frappe._dict(filters or {})

	def run(self):
		self.get_columns()
		self.get_data()
		self.get_chart_data()

		return self.columns, self.data, None, self.chart

	def get_columns(self):
		self.columns = []

		if self.filters.based_on == 'Customer':
			self.columns.append({
				'label': _('Customer'),
				'options': 'Customer',
				'fieldname': 'customer',
				'fieldtype': 'Link',
				'width': 200
			})

		elif self.filters.based_on == 'Assigned To':
			self.columns.append({
				'label': _('User'),
				'fieldname': 'user',
				'fieldtype': 'Link',
				'options': 'User',
				'width': 200
			})

		elif self.filters.based_on == 'Issue Type':
			self.columns.append({
				'label': _('Issue Type'),
				'fieldname': 'issue_type',
				'fieldtype': 'Link',
				'options': 'Issue Type',
				'width': 200
			})

		elif self.filters.based_on == 'Issue Priority':
			self.columns.append({
				'label': _('Issue Priority'),
				'fieldname': 'priority',
				'fieldtype': 'Link',
				'options': 'Issue Priority',
				'width': 200
			})

		self.statuses = ['Open', 'Replied', 'Resolved', 'Closed']
		for status in self.statuses:
			self.columns.append({
				'label': _(status),
				'fieldname': scrub(status),
				'fieldtype': 'Int',
				'width': 80
			})

		self.columns.append({
			'label': _('Total Issues'),
			'fieldname': 'total_issues',
			'fieldtype': 'Int',
			'width': 100
		})

		self.metrics = ['Average First Response Time', 'Average Response Time', 'Average Hold Time',
			'Average Resolution Time', 'Average User Resolution Time']

		for metric in self.metrics:
			self.columns.append({
				'label': _(metric),
				'fieldname': scrub(metric),
				'fieldtype': 'Duration',
				'width': 200
			})

	def get_data(self):
		self.get_issues()
		self.get_rows()

	def get_issues(self):
		filters = self.get_common_filters()
		self.field_map = {
			'Customer': 'customer',
			'Issue Type': 'issue_type',
			'Issue Priority': 'priority',
			'Assigned To': '_assign'
		}

		self.entries = frappe.db.get_all('Issue',
			fields=[self.field_map.get(self.filters.based_on), 'name', 'opening_date', 'status', 'avg_response_time',
				'first_response_time', 'total_hold_time', 'user_resolution_time', 'resolution_time'],
			filters=filters
		)

	def get_common_filters(self):
		filters = {}
		filters['opening_date'] = ('between', [self.filters.from_date, self.filters.to_date])

		if self.filters.get('assigned_to'):
			filters['_assign'] = ('like', '%' + self.filters.get('assigned_to') + '%')

		for entry in ['company', 'status', 'priority', 'customer', 'project']:
			if self.filters.get(entry):
				filters[entry] = self.filters.get(entry)

		return filters

	def get_rows(self):
		self.data = []
		self.get_summary_data()

		for entity, data in iteritems(self.issue_summary_data):
			if self.filters.based_on == 'Customer':
				row = {'customer': entity}
			elif self.filters.based_on == 'Assigned To':
				row = {'user': entity}
			elif self.filters.based_on == 'Issue Type':
				row = {'issue_type': entity}
			elif self.filters.based_on == 'Issue Priority':
				row = {'priority': entity}

			total = 0
			for status in self.statuses:
				count = flt(data.get(status, 0.0))
				row[scrub(status)] = count

			row['total_issues'] = data.get('total_issues', 0.0)

			for metric in self.metrics:
				value = flt(data.get(scrub(metric)), 0.0)
				row[scrub(metric)] = value

			self.data.append(row)

	def get_summary_data(self):
		self.issue_summary_data = frappe._dict()

		for d in self.entries:
			status = d.status

			if self.filters.based_on == 'Assigned To':
				if d._assign:
					for entry in json.loads(d._assign):
						self.issue_summary_data.setdefault(entry, frappe._dict()).setdefault(status, 0.0)
						self.issue_summary_data.setdefault(entry, frappe._dict()).setdefault('total_issues', 0.0)
						self.issue_summary_data[entry][status] += 1
						self.issue_summary_data[entry]['total_issues'] += 1

			else:
				field = self.field_map.get(self.filters.based_on)
				value = d.get(field)
				if not value:
					value = _('Not Specified')

				self.issue_summary_data.setdefault(value, frappe._dict()).setdefault(status, 0.0)
				self.issue_summary_data.setdefault(value, frappe._dict()).setdefault('total_issues', 0.0)
				self.issue_summary_data[value][status] += 1
				self.issue_summary_data[value]['total_issues'] += 1

		self.get_metrics_data()

	def get_metrics_data(self):
		issues = []

		metrics_list = ['average_response_time', 'average_first_response_time', 'average_hold_time',
			'average_resolution_time', 'average_user_resolution_time']

		for entry in self.entries:
			issues.append(entry.name)

		field = self.field_map.get(self.filters.based_on)

		if issues:
			if self.filters.based_on == 'Assigned To':
				assignment_map = frappe._dict()
				for d in self.entries:
					if d._assign:
						for entry in json.loads(d._assign):
							for metric in metrics_list:
								self.issue_summary_data.setdefault(entry, frappe._dict()).setdefault(metric, 0.0)

							self.issue_summary_data[entry]['average_response_time'] += d.get('avg_response_time') or 0.0
							self.issue_summary_data[entry]['average_first_response_time'] += d.get('first_response_time') or 0.0
							self.issue_summary_data[entry]['average_hold_time'] += d.get('total_hold_time') or 0.0
							self.issue_summary_data[entry]['average_resolution_time'] += d.get('resolution_time') or 0.0
							self.issue_summary_data[entry]['average_user_resolution_time'] += d.get('user_resolution_time') or 0.0

							if not assignment_map.get(entry):
								assignment_map[entry] = 0
							assignment_map[entry] += 1

				for entry in assignment_map:
					for metric in metrics_list:
						self.issue_summary_data[entry][metric] /= flt(assignment_map.get(entry))

			else:
				data = frappe.db.sql("""
					SELECT
						{0}, AVG(first_response_time) as avg_frt,
						AVG(avg_response_time) as avg_resp_time,
						AVG(total_hold_time) as avg_hold_time,
						AVG(resolution_time) as avg_resolution_time,
						AVG(user_resolution_time) as avg_user_resolution_time
					FROM `tabIssue`
					WHERE
						name IN %(issues)s
					GROUP BY {0}
				""".format(field), {'issues': issues}, as_dict=1)

				for entry in data:
					value = entry.get(field)
					if not value:
						value = _('Not Specified')

					for metric in metrics_list:
						self.issue_summary_data.setdefault(value, frappe._dict()).setdefault(metric, 0.0)

					self.issue_summary_data[value]['average_response_time'] = entry.get('avg_resp_time') or 0.0
					self.issue_summary_data[value]['average_first_response_time'] = entry.get('avg_frt') or 0.0
					self.issue_summary_data[value]['average_hold_time'] = entry.get('avg_hold_time') or 0.0
					self.issue_summary_data[value]['average_resolution_time'] = entry.get('avg_resolution_time') or 0.0
					self.issue_summary_data[value]['average_user_resolution_time'] = entry.get('avg_user_resolution_time') or 0.0

	def get_chart_data(self):
		length = len(self.columns)
		labels = [d.get('label') for d in self.columns[1:length]]
		self.chart = {
			'data': {
				'labels': labels,
				'datasets': []
			},
			'type': 'line'
		}

	def get_chart_data(self):
		labels = []
		open_issues = []
		replied_issues = []
		resolved_issues = []
		closed_issues = []

		entity = self.filters.based_on
		entity_field = self.field_map.get(entity)
		if entity == 'Assigned To':
			entity_field = 'user'

		for entry in self.data:
			labels.append(entry.get(entity_field))
			open_issues.append(entry.get('open'))
			replied_issues.append(entry.get('replied'))
			resolved_issues.append(entry.get('resolved'))
			closed_issues.append(entry.get('closed'))

		self.chart = {
			'data': {
				'labels': labels[:30],
				'datasets': [
					{
						'name': 'Open',
						'values': open_issues[:30]
					},
					{
						'name': 'Replied',
						'values': replied_issues[:30]
					},
					{
						'name': 'Resolved',
						'values': resolved_issues[:30]
					},
					{
						'name': 'Closed',
						'values': closed_issues[:30]
					}
				]
			},
			'type': 'bar',
			'barOptions': {
				'stacked': True
			}
		}

