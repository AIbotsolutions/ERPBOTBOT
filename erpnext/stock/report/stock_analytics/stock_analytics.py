# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from erpnext.selling.report.sales_analytics.sales_analytics import(get_period_date_ranges, get_period,get_depth_map)
from erpnext.stock.report.stock_balance.stock_balance import (get_items, get_stock_ledger_entries)

def execute(filters=None):
	columns = get_columns(filters)
	data = get_data(filters)
	chart = get_chart_data(filters,columns,data)
	
	return columns, data, None, chart

def get_columns(filters):

	columns =[
		{
			"label": _("Item"),
			"fieldname": "name",
			"fieldtype": "Data",
			"width": 140
		},
		{
			"label": _("Item Name"),
			"fieldname": "code",
			"fieldtype": "Data",
			"width": 140
		},
		{
			"label": _("Brand"),
			"fieldname": "brand",
			"fieldtype": "Data",
			"width": 120
		},
		{
			"label": _("UOM"),
			"fieldname": "uom",
			"fieldtype": "Data",
			"width": 120
		}]

	ranges = get_period_date_ranges(filters["range"],None, filters["from_date"],filters["to_date"])

	for dummy, end_date in ranges:

		label = field_name = get_period(end_date,filters["range"])

		columns.append(
			{
			"label": _(label),
			"field_name":field_name,
			"fieldtype": "Date",
			"width": 120
		},
		)

	return columns

def get_data_list(entry,filters):
	data_list = {}
	for d in entry:

		period = get_period(d.posting_date,filters["range"])
		bal_qty =0 

		if d.voucher_type == "Stock Reconciliation":
			if data_list.get(d.item_code):
 				bal_qty = data_list[d.item_code]["balance"] 

			qty_diff = d.qty_after_transaction - bal_qty
		else:
			qty_diff = d.actual_qty
		

		if filters["value_quantity"] == 'Quantity':
			value = qty_diff
		else:
			value = d.stock_value_difference 


		if data_list.get(d.item_code) :
			data_list[d.item_code]["balance"] += value
			data_list[d.item_code][period] = data_list[d.item_code]["balance"]
		else:
			data_list.setdefault(d.item_code,{}).setdefault(period,value)
			data_list[d.item_code]["balance"] = value

	return data_list


def get_data(filters):

	data = []

	items = get_items(filters)

	sle = get_stock_ledger_entries(filters, items)

	data_list = get_data_list(sle,filters)

	grp_dict ={"tree_type":"Item Group"}

	group = frappe.db.sql("""select name,lft,rgt from `tabItem Group` where lft = 1  """,as_dict=1)

	depth_map = get_depth_map(grp_dict,group,0,[])

	items_by_group = get_item_by_group(filters)
	for g in depth_map:
		has_items = 0
		group = {}
		g_total= 0
		out = []
		group["name"] = g.get("name")
		group["indent"] = g.get("depth")
		group["code"] = g.get("name")

		ranges = get_period_date_ranges(filters["range"],year_start_date=filters["from_date"], year_end_date=filters["to_date"])
		
		for d in items_by_group:
			if d.lft >= g.get("lft") and d.rgt <= g.get("rgt") :
				has_items = 1 
				item = {}
				total = 0
				item["name"] = d.name
				item["code"] = d.item_name
				item["uom"] = d.stock_uom
				item["brand"] = d.brand
				item["indent"] = g.get("depth")+1
				for dummy, end_date in ranges:
					period = get_period(end_date, filters["range"])
					if data_list.get(d.name) and data_list.get(d.name).get(period) :
						item[period] = data_list.get(d.name).get(period)
					else:
						item[period] = 0.0
					total += item[period]
					if group.get(period):
						group[period] += item[period]
					else:
						group[period] = item[period]
				item["total"] = total
				g_total += total 
				if d.item_group == g.get("name"):
					out.append(item)
		group["total"] = g_total
		if has_items:
			data.append(group)
		data += out

	return data

def get_item_by_group(filters):

	conditions = ["i.item_group = g.name"]
	
	if filters.get("brand"):
		conditions.append("i.brand=%(brand)s")
		
	items = frappe.db.sql("""select i.name,i.item_name,i.item_group,i.stock_uom,i.brand,g.lft,g.rgt 
							from `tabItem` i ,`tabItem Group` g  where {}"""
		.format(" and ".join(conditions)), filters,as_dict=1)

	return items

def get_chart_data(filters, columns, data):

	labels = [d.get("label") for d in columns[4:]]
	chart = {
		"data": {
			'labels': labels,
			'datasets':[
				{ "values": ['0' for d in columns[4:]] }
			]
		}
	}

	chart["type"] = "line"

	return chart


