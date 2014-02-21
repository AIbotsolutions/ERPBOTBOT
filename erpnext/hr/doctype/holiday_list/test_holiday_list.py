# Copyright (c) 2013, Web Notes Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals

test_records = [
	[{
		"doctype": "Holiday List",
		"holiday_list_name": "_Test Holiday List",
		"period": "_Test Period",
		"is_default": 1
	}, {
		"doctype": "Holiday",
		"parent": "_Test Holiday List",
		"parenttype": "Holiday List",
		"parentfield": "holiday_list_details",
		"holiday_date": "2013-01-01",
		"description": "New Year"
	}]
]