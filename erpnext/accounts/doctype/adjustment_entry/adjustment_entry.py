# -*- coding: utf-8 -*-
# Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import flt
from erpnext import get_party_account_type
from erpnext.controllers.accounts_controller import AccountsController
from erpnext.accounts.general_ledger import make_gl_entries
from erpnext.accounts.party import get_party_account
from erpnext.accounts.utils import get_outstanding_invoices, get_negative_outstanding_invoices, get_account_currency
from erpnext.setup.utils import get_exchange_rate
from erpnext.controllers.accounts_controller import get_advance_payment_entries
from erpnext.accounts.doctype.payment_entry.payment_entry import get_company_defaults
from datetime import date

class AdjustmentEntry(AccountsController):
    def validate(self):
        self.validate_customer_supplier_account()

    def on_submit(self):
        if self.difference_amount:
            frappe.throw(_("Difference Amount must be zero"))
        self.make_gl_entries()

    def on_cancel(self):
        self.make_gl_entries(cancel=1)

    def validate_customer_supplier_account(self):
        customer_account = get_party_account("Customer", self.customer, self.company)
        supplier_account = get_party_account("Supplier", self.supplier, self.company)
        customer_account_currency = frappe.db.get_value("Account", customer_account,
                                               'account_currency')
        supplier_account_currency = frappe.db.get_value("Account", supplier_account,
                                                        'supplier_account')
        if customer_account_currency != supplier_account_currency:
            frappe.throw(_("Customer account currency ({0}) and supplier account currency ({1}) should be same")
                         .format(customer_account_currency, supplier_account_currency))
        elif customer_account_currency != self.payment_currency and self.company_currency != customer_account_currency:
            frappe.throw(_("Payment currency ({0}) should be same as Customer/Supplier account currency ({1})")
                         .format(self.payment_currency, customer_account_currency))


    def get_unreconciled_entries(self):
        self.check_mandatory_to_fetch()
        self.get_entries()

    def check_mandatory_to_fetch(self):
        for fieldname in self.get_mandatory_fields():
            if not self.get(fieldname):
                frappe.throw(_("Please select {0} first").format(self.meta.get_label(fieldname)))

    def get_mandatory_fields(self):
        mandatory_fields = ["company", "adjustment_type"]
        if self.adjustment_type != 'Purchase':
            mandatory_fields.append("customer")
        if self.adjustment_type != 'Sales':
            mandatory_fields.append("supplier")
        return mandatory_fields

    def get_party_details(self, type="debit_entries"):
        if type == 'debit_entries':
            party_type = "Customer"
            party = self.customer
        else:
            party_type = "Supplier"
            party = self.supplier
        account = get_party_account(party_type, party, self.company)
        order_doctype = "Sales Order" if party_type == "Customer" else "Purchase Order"
        account_currency = frappe.db.get_value("Account", account,
                            'account_currency')
        return [party_type, party, account, order_doctype, account_currency]


    def get_exchange_rates(self, entries):
        currencies = list(set([entry.get("currency") for entry in entries]))
        if self.payment_currency not in currencies:
            currencies.append(self.payment_currency)
        self.set('exchange_rates', [])
        for currency in currencies:
            exc = self.append('exchange_rates', {})
            exc.currency = currency
            exc.exchange_rate_to_payment_currency = get_exchange_rate(currency, self.payment_currency) or 1
            exc.exchange_rate_to_base_currency = get_exchange_rate(currency, self.company_currency) or 1

    def exchange_rates_to_dict(self):
        rates = {}
        for exchange_rate in self.exchange_rates:
            rates[exchange_rate.currency] = {
                "exchange_rate_to_payment_currency": exchange_rate.exchange_rate_to_payment_currency,
                "exchange_rate_to_base_currency": exchange_rate.exchange_rate_to_base_currency
            }
        return rates

    def get_entries(self):
        if self.adjustment_type == 'Sales':
            sales_invoices = self.get_invoices('debit_entries')
            payments = self.get_payments('debit_entries')
            self.get_exchange_rates(sales_invoices + payments)
            self.add_invoice_entries(sales_invoices, 'debit_entries')
            self.add_payment_entries(payments, 'credit_entries')
        elif self.adjustment_type == 'Purchase':
            purchase_invoices = self.get_invoices('credit_entries')
            payments = self.get_payments('credit_entries')
            self.get_exchange_rates(payments + purchase_invoices)
            self.add_invoice_entries(purchase_invoices, 'credit_entries')
            self.add_payment_entries(payments, 'debit_entries')
        else:
            sales_invoices = self.get_invoices('debit_entries')
            purchase_invoices = self.get_invoices('credit_entries')
            self.get_exchange_rates(sales_invoices+purchase_invoices)
            self.add_invoice_entries(sales_invoices, 'debit_entries')
            self.add_invoice_entries(purchase_invoices, 'credit_entries')

    def get_invoices(self, field_name):
        party_type, party, account, order_doctype, account_currency = self.get_party_details(field_name)
        positive_outstanding_invoices = get_outstanding_invoices(party_type, party, account)
        negative_outstanding_invoices = get_negative_outstanding_invoices(party_type,
                                                                  party, account,
                                                                  account_currency,
                                                                  self.company_currency)
        non_reconciled_invoices = negative_outstanding_invoices + positive_outstanding_invoices
        self.get_extra_invoice_details(non_reconciled_invoices)
        return non_reconciled_invoices

    def get_extra_invoice_details(self, outstanding_invoices):
        for d in outstanding_invoices:
            d["exchange_rate"] = 1
            if d.voucher_type in ("Sales Invoice", "Purchase Invoice"):
                d["exchange_rate"], d["currency"], d["cost_center"] = frappe.db.get_value(d.voucher_type, d.voucher_no, ["conversion_rate", "currency", "cost_center"])
            if d.voucher_type in ("Journal Entry"):
                debit_in_account_currency, debit, d["currency"], d["cost_center"] = frappe.db.get_value('GL Entry', d.name, ["debit_in_account_currency", "debit", "account_currency", "cost_center"])
                d["exchange_rate"] = debit / debit_in_account_currency
            if d.voucher_type in ("Purchase Invoice"):
                d["supplier_bill_no"], d["supplier_bill_date"] = frappe.db.get_value(d.voucher_type, d.voucher_no, ["bill_no", "bill_date"])

    def get_payments(self, field_name):
        party_type, party, account, order_doctype, account_currency = self.get_party_details(field_name)
        advance_payments = get_advance_payment_entries(party_type, party, account, order_doctype)
        self.get_extra_payment_details(advance_payments, field_name)
        return advance_payments

    def get_extra_payment_details(self, advances, field_name):
        for d in advances:
            d["exchange_rate"] = 1
            if d.reference_type in ("Payment Entry") and field_name == 'debit_entries':
                d["posting_date"], d["exchange_rate"], d["currency"] = frappe.db.get_value(d.reference_type, d.reference_name,
                                                                        ["posting_date", "target_exchange_rate", "paid_to_account_currency"])
            elif d.reference_type in ("Payment Entry") and field_name == 'credit_entries':
                d["posting_date"], d["exchange_rate"], d["currency"] = frappe.db.get_value(d.reference_type, d.reference_name, ["posting_date", "source_exchange_rate", "paid_from_account_currency"])

    def add_payment_entries(self, advances, field_name):
        exchange_rates = self.exchange_rates_to_dict()
        self.set(field_name, [])

        for advance in advances:
            ent = self.append(field_name, {})
            ent.voucher_type = advance.get('reference_type')
            ent.voucher_number = advance.get('reference_name')
            ent.voucher_date = advance.get('posting_date')
            ent.voucher_base_amount = advance.get('amount')
            ent.currency = advance.get("currency")
            ent.exchange_rate = advance.get('exchange_rate')
            ent.voucher_amount = ent.voucher_base_amount / ent.exchange_rate
            ent.recalculate_amounts(self.payment_currency, exchange_rates)

    def add_invoice_entries(self, invoices, field_name):
        exchange_rates = self.exchange_rates_to_dict()
        party_type, party, account, order_doctype, account_currency = self.get_party_details(field_name)
        self.set(field_name, [])

        for invoice in invoices:
            ent = self.append(field_name, {})
            ent.voucher_type = invoice.get('voucher_type')
            ent.voucher_number = invoice.get('voucher_no')
            ent.voucher_date = invoice.get('posting_date')
            ent.currency = invoice.get("currency")
            ent.exchange_rate = invoice.get('exchange_rate')
            ent.cost_center = invoice.get('cost_center')
            if account_currency != self.company_currency:
                ent.voucher_base_amount = invoice.get('outstanding_amount') * invoice.get('exchange_rate')
                ent.voucher_amount = invoice.get('outstanding_amount')
            else:
                ent.voucher_base_amount = invoice.get('outstanding_amount')
                ent.voucher_amount = ent.voucher_base_amount / ent.exchange_rate
            ent.recalculate_amounts(self.payment_currency, exchange_rates)
            ent.supplier_bill_no = invoice.get('supplier_bill_no')
            ent.supplier_bill_date = invoice.get('supplier_bill_date')

    def recalculate_tables(self):
        debit_entries = self.debit_entries
        credit_entries = self.credit_entries
        self.get_exchange_rates(debit_entries + credit_entries)
        self.recalculate_references(['debit_entries', 'credit_entries'])

    def recalculate_references(self, reference_types):
        exchange_rates = self.exchange_rates_to_dict()
        for reference_type in reference_types:
            entries = self.get(reference_type)
            if entries:
                for ent in entries:
                    ent.recalculate_amounts(self.payment_currency, exchange_rates)

    def calculate_summary_totals(self):
        self.receivable_adjusted = sum([flt(d.allocated_amount) for d in self.get("debit_entries")])
        self.payable_adjusted = sum([flt(d.allocated_amount) for d in self.get("credit_entries")])
        self.total_deductions = sum([flt(d.amount) for d in self.get("deductions")])
        self.difference_amount = abs(self.receivable_adjusted - self.payable_adjusted - self.total_deductions)

    def allocate_amount_to_references(self):
        total_debit_outstanding = sum([flt(d.voucher_payment_amount) for d in self.get("debit_entries")])
        total_credit_outstanding = sum([flt(c.voucher_payment_amount) for c in self.get("credit_entries")])
        exchange_rates = self.exchange_rates_to_dict()
        total_deductions = sum([flt(d.amount) for d in self.get("deductions")])
        allocate_order = ['credit_entries', 'debit_entries'] if total_debit_outstanding > total_credit_outstanding else ['debit_entries', 'credit_entries']
        for reference_type in allocate_order:
            allocated_oustanding = min(total_debit_outstanding, total_credit_outstanding) - total_deductions
            entries = self.get(reference_type)
            for ent in entries:
                ent.allocated_amount = 0
                if self.allocate_payment_amount:
                    if allocated_oustanding > 0:
                        if ent.voucher_payment_amount >= allocated_oustanding:
                            ent.allocated_amount = allocated_oustanding
                        else:
                            ent.allocated_amount = ent.voucher_payment_amount
                        allocated_oustanding -= flt(ent.allocated_amount)
                ent.recalculate_amounts(self.payment_currency, exchange_rates)
        self.calculate_summary_totals()

    def make_gl_entries(self, cancel=0, adv_adj=0):
        gl_entries = []
        self.add_party_gl_entries(gl_entries)
        self.add_deductions_gl_entries(gl_entries)
        self.add_gain_loss_entries(gl_entries)
        make_gl_entries(gl_entries, cancel=cancel, adv_adj=adv_adj)

    def add_party_gl_entries(self, gl_entries):
        party_details_dict = dict()
        for reference_type in ['debit_entries', 'credit_entries']:
            party_type, party, account, order_doctype, account_currency = self.get_party_details(reference_type)
            party_details_dict[reference_type] = dict({'party_type': party_type, 'party': party, 'account': account, 'order_doctype': order_doctype, 'account_currency': account_currency})
        for reference_type in ['debit_entries', 'credit_entries']:
            entries = self.get(reference_type)
            party_details = party_details_dict[reference_type]
            against_account = party_details_dict['credit_entries']['account'] if reference_type == 'debit_entries' else party_details_dict['debit_entries']['account']
            dr_or_cr = "credit" if get_party_account_type(party_details['party_type']) == 'Receivable' else "debit"
            for ent in entries:
                party_gl_dict = self.get_gl_dict({
                    "account": party_details['account'],
                    "party_type": party_details['party_type'],
                    "party": party_details['party'],
                    "against": against_account,
                    "account_currency": party_details['account_currency'],
                    "cost_center": self.cost_center
                 })
                party_gl_dict.update({
                    "against_voucher_type": ent.voucher_type,
                    "against_voucher": ent.voucher_number
                })
                allocated_amount_in_entry_currrency = ent.allocated_amount / ent.payment_exchange_rate
                allocated_amount_in_company_currency = allocated_amount_in_entry_currrency * ent.exchange_rate
                allocated_amount_in_account_currrency = ent.allocated_amount * ent.payment_exchange_rate if account_currency != self.company_currency else allocated_amount_in_company_currency
                party_gl_dict.update({
                    dr_or_cr + "_in_account_currency": allocated_amount_in_account_currrency,
                    dr_or_cr: allocated_amount_in_company_currency
                })
                gl_entries.append(party_gl_dict)

    def add_deductions_gl_entries(self, gl_entries):
        for d in self.get("deductions"):
            if d.amount:
                account_currency = get_account_currency(d.account)
                if account_currency != self.company_currency:
                    frappe.throw(_("Currency for {0} must be {1}").format(d.account, self.company_currency))

                gl_entries.append(
                    self.get_gl_dict({
                        "account": d.account,
                        "account_currency": account_currency,
                        "against": self.customer,
                        "debit_in_account_currency": d.amount,
                        "debit": d.amount,
                        "cost_center": d.cost_center
                    }, item=d)
                )

    def add_gain_loss_entries(self, gl_entries):
        company_details = get_company_defaults(self.company)
        exchange_gain_loss_account = company_details.exchange_gain_loss_account
        if exchange_gain_loss_account is None:
            frappe.throw("Exchange gain loss account not set for {0}").format(self.company)
        account_root_type = frappe.db.get_value("Account", exchange_gain_loss_account, "root_type")
        total_gain_loss = sum([flt(d.gain_loss_amount) for d in self.get("debit_entries")]) + sum([flt(d.gain_loss_amount) for d in self.get("credit_entries")])
        gl_dict = self.get_gl_dict({
                    "account": exchange_gain_loss_account,
                    "account_currency": self.company_currency,
                    "cost_center": self.cost_center or company_details.cost_center,
                 })
        if account_root_type == "Expense":
            dr_or_cr = "credit" if total_gain_loss > 0 else "debit"
        else:
            dr_or_cr = "debit" if total_gain_loss > 0 else "credit"
        gl_dict.update({
            dr_or_cr + "_in_account_currency": abs(total_gain_loss),
            dr_or_cr: abs(total_gain_loss)
        })
        gl_entries.append(gl_dict)
