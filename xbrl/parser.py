#! /usr/bin/env python
# encoding: utf-8

import re
import datetime
import six
import logging
import warnings

from xbrl.model import XBRL, GAAP, DEI, Custom, XBRLPreprocessedFile
from xbrl.serializers import GAAPSerializer, DEISerializer

def soup_maker(fh):
    """ Takes a file handler returns BeautifulSoup"""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(fh, "lxml")
        for tag in soup.find_all():
            tag.name = tag.name.lower()
    except ImportError:
        from BeautifulSoup import BeautifulStoneSoup
        soup = BeautifulStoneSoup(fh)
    return soup


class XBRLParser(object):

    def __init__(self, precision=0):
        if precision:
            warnings.warn("The precision argument has been deprecated. The argument will not affect any results.", DeprecationWarning, stacklevel=2)
        self.logger = logging.getLogger(__name__)

    def parse(self, file_handle):
        """
        parse is the main entry point for an XBRLParser. It takes a file
        handle.
        """

        xbrl_obj = XBRL()

        # if no file handle was given create our own
        if not hasattr(file_handle, 'read'):
            file_handler = open(file_handle)
        else:
            file_handler = file_handle

        # Store the headers
        xbrl_file = XBRLPreprocessedFile(file_handler)

        xbrl = soup_maker(xbrl_file.fh)
        file_handler.close()
        xbrl_base = xbrl.find(name=re.compile("xbrl*:*"))

        if xbrl.find('xbrl') is None and xbrl_base is None:
            raise XBRLParserException('The xbrl file is empty!')

        # lookahead to see if we need a custom leading element
        lookahead = xbrl.find(name=re.compile("context",
                              re.IGNORECASE | re.MULTILINE)).name
        if ":" in lookahead:
            self.xbrl_base = lookahead.split(":")[0] + ":"
        else:
            self.xbrl_base = ""

        return xbrl

    def parseGAAP(self,
                  xbrl,
                  doc_date="",
                  context="current",
                  ignore_errors=0):
        """
        Parse GAAP from our XBRL soup and return a GAAP object.
        """
        gaap_obj = GAAP()

        # the default is today
        if doc_date == "":
            doc_date = str(datetime.date.today())
        doc_date = re.sub(r"[^0-9]+", "", doc_date)

        # current is the previous quarter
        if context == "current":
            context = 90

        if context == "year":
            context = 360

        context = int(context)

        if context % 90 == 0:
            context_extended = list(range(context, context + 9))
            expected_start_date = \
                datetime.datetime.strptime(doc_date, "%Y%m%d") \
                - datetime.timedelta(days=context)
        elif context == "instant":
            expected_start_date = None
        else:
            raise XBRLParserException('invalid context')

        # we need expected end date unless instant
        if context != "instant":
            expected_end_date = \
                datetime.datetime.strptime(doc_date, "%Y%m%d")

        doc_root = ""

        # we might need to attach the document root
        if len(self.xbrl_base) > 1:
            doc_root = self.xbrl_base

        # collect all contexts up that are relevant to us
        # TODO - Maybe move this to Preprocessing Ingestion
        context_ids = []
        context_tags = xbrl.find_all(name=re.compile(doc_root + "context",
                                     re.IGNORECASE | re.MULTILINE))

        try:
            for context_tag in context_tags:
                # we don't want any segments
                if context_tag.find(doc_root + "entity") is None:
                    continue
                if context_tag.find(doc_root + "entity").find(
                doc_root + "segment") is None:
                    context_id = context_tag.attrs['id']

                    found_start_date = None
                    found_end_date = None

                    if context_tag.find(doc_root + "instant"):
                        instant = \
                            datetime.datetime.strptime(re.compile('[^\d]+')
                                                       .sub('', context_tag
                                                       .find(doc_root +
                                                             "instant")
                                                        .text)[:8], "%Y%m%d")
                        if instant == expected_end_date:
                            context_ids.append(context_id)
                            continue

                    if context_tag.find(doc_root + "period").find(
                    doc_root + "startdate"):
                        found_start_date = \
                            datetime.datetime.strptime(re.compile('[^\d]+')
                                                       .sub('', context_tag
                                                       .find(doc_root +
                                                             "period")
                                                       .find(doc_root +
                                                             "startdate")
                                                        .text)[:8], "%Y%m%d")
                    if context_tag.find(doc_root + "period").find(doc_root +
                    "enddate"):
                        found_end_date = \
                            datetime.datetime.strptime(re.compile('[^\d]+')
                                                       .sub('', context_tag
                                                       .find(doc_root +
                                                             "period")
                                                       .find(doc_root +
                                                             "enddate")
                                                       .text)[:8], "%Y%m%d")
                    if found_end_date and found_start_date:
                        for ce in context_extended:
                            if found_end_date - found_start_date == \
                            datetime.timedelta(days=ce):
                                if found_end_date == expected_end_date:
                                    context_ids.append(context_id)
        except IndexError:
            raise XBRLParserException('problem getting contexts')

        gaap_obj.assets = self.get_tag(xbrl, "us-gaap:assets$", ignore_errors, context_ids)

        current_assets = \
            xbrl.find_all("us-gaap:assetscurrent")
        gaap_obj.current_assets = self.data_processing(current_assets,
            xbrl, ignore_errors, context_ids)

        non_current_assets = \
            xbrl.find_all(name=re.compile("(us-gaap:)[^s]*(assetsnoncurrent)",
                          re.IGNORECASE | re.MULTILINE))
        if non_current_assets == 0 or not non_current_assets:
            # Assets  = AssetsCurrent  +  AssetsNoncurrent
            gaap_obj.non_current_assets = gaap_obj.assets \
                - gaap_obj.current_assets
        else:
            gaap_obj.non_current_assets = \
                self.data_processing(non_current_assets, xbrl,
                    ignore_errors, context_ids)

        gaap_obj.liabilities_and_equity = self.get_tag(xbrl, "(us-gaap:)[^s]*(liabilitiesand)", ignore_errors, context_ids)
        gaap_obj.liabilities = self.get_tag(xbrl, "(us-gaap:)[^s]*(liabilities)", ignore_errors, context_ids)
        gaap_obj.current_liabilities = self.get_tag(xbrl, "(us-gaap:)[^s]*(currentliabilities)", ignore_errors, context_ids)
        gaap_obj.noncurrent_liabilities = self.get_tag(xbrl, "(us-gaap:)[^s]*(noncurrentliabilities)", ignore_errors, context_ids)

        gaap_obj.commitments_and_contingencies = self.get_tag(xbrl, "(us-gaap:commitmentsandcontingencies)", ignore_errors, context_ids)

        redeemable_noncontrolling_interest = \
            xbrl.find_all(name=re.compile("(us-gaap:redeemablenoncontrolling\
                          interestequity)", re.IGNORECASE | re.MULTILINE))
        gaap_obj.redeemable_noncontrolling_interest = \
            self.data_processing(redeemable_noncontrolling_interest,
                xbrl, ignore_errors, context_ids)

        gaap_obj.temporary_equity = self.get_tag(xbrl, "(us-gaap:)[^s]*(temporaryequity)", ignore_errors, context_ids)

        gaap_obj.equity = self.get_tag(xbrl, "(us-gaap:)[^s]*(equity)", ignore_errors, context_ids)

        gaap_obj.equity_attributable_interest = self.get_tag(xbrl, "(us-gaap:minorityinterest)", ignore_errors, context_ids)

        gaap_obj.stockholders_equity = self.get_tag(xbrl, "(us-gaap:stockholdersequity)", ignore_errors, context_ids)
        gaap_obj.equity_attributable_parent = self.get_tag(xbrl, "(us-gaap:liabilitiesandpartnerscapital)", ignore_errors, context_ids)

        # Incomes #
        gaap_obj.revenues = self.get_tag(xbrl, "(us-gaap:)[^s]*(revenue)", ignore_errors, context_ids)


        gaap_obj.cost_of_revenue = self.get_tag(xbrl, [
            "(us-gaap:costofrevenue)",
            "(us-gaap:costofservices)",
            "(us-gaap:costofgoodssold)",
            "(us-gaap:costofgoodsandservicessold)"
        ], ignore_errors, context_ids)

        gaap_obj.gross_profit = self.get_tag(xbrl, "(us-gaap:)[^s]*(grossprofit)", ignore_errors, context_ids)
        gaap_obj.operating_expenses = self.get_tag(xbrl, "(us-gaap:operating)[^s]*(expenses)", ignore_errors, context_ids)
        gaap_obj.costs_and_expenses = self.get_tag(xbrl, "(us-gaap:)[^s]*(costsandexpenses)", ignore_errors, context_ids)
        gaap_obj.other_operating_income = self.get_tag(xbrl, "(us-gaap:otheroperatingincome)", ignore_errors, context_ids)
        gaap_obj.operating_income_loss = self.get_tag(xbrl, "(us-gaap:otheroperatingincome)", ignore_errors, context_ids)
        gaap_obj.nonoperating_income_loss = self.get_tag(xbrl, "(us-gaap:nonoperatingincomeloss)", ignore_errors, context_ids)
        gaap_obj.interest_and_debt_expense = self.get_tag(xbrl, "(us-gaap:interestanddebtexpense)", ignore_errors, context_ids)


        gaap_obj.income_before_equity_investments = self.get_tag(xbrl, "(us-gaap:incomelossfromcontinuing"
                                          "operationsbeforeincometaxes"
                                          "minorityinterest)", ignore_errors, context_ids)

        gaap_obj.income_from_equity_investments = self.get_tag(xbrl, "(us-gaap:incomelossfromequity"
                          "methodinvestments)", ignore_errors, context_ids)

        gaap_obj.income_tax_expense_benefit = self.get_tag(xbrl, "(us-gaap:incometaxexpensebenefit)", ignore_errors, context_ids)

        gaap_obj.income_continuing_operations_tax = self.get_tag(xbrl, "(us-gaap:IncomeLossBeforeExtraordinaryItemsAndCumulativeEffectOfChangeInAccountingPrinciple)", ignore_errors, context_ids)

        gaap_obj.income_discontinued_operations = self.get_tag(xbrl, "(us-gaap:)[^s]*(discontinuedoperation)", ignore_errors, context_ids)

        gaap_obj.extraordary_items_gain_loss = self.get_tag(xbrl, "(us-gaap:extraordinaryitemnetoftax)", ignore_errors, context_ids)

        income_loss = \
            xbrl.find_all(name=re.compile("(us-gaap:)[^s]*(incomeloss)",
                          re.IGNORECASE | re.MULTILINE))
        gaap_obj.income_loss = \
            self.data_processing(income_loss, xbrl, ignore_errors,
                context_ids)
        income_loss += xbrl.find_all(name=re.compile("(us-gaap:profitloss)",
                                     re.IGNORECASE | re.MULTILINE))
        gaap_obj.income_loss = \
            self.data_processing(income_loss, xbrl, ignore_errors,
                                 context_ids)

        gaap_obj.net_income_shareholders = self.get_tag(xbrl, "(us-gaap:netincomeavailabletocommonstockholdersbasic)", ignore_errors, context_ids)

        gaap_obj.preferred_stock_dividends = self.get_tag(xbrl, "(us-gaap:preferredstockdividendsandotheradjustments)", ignore_errors, context_ids)

        gaap_obj.net_income_loss_noncontrolling = self.get_tag(xbrl, "(us-gaap:netincomelossattributabletononcontrollinginterest)", ignore_errors, context_ids)
        gaap_obj.net_income_loss = self.get_tag(xbrl, "^us-gaap:netincomeloss$", ignore_errors, context_ids)

        # Comprehensive income
        gaap_obj.comprehensive_income = self.get_tag(xbrl, "(us-gaap:comprehensiveincome)", ignore_errors, context_ids)
        gaap_obj.comprehensive_income_parent = self.get_tag(xbrl, "(us-gaap:comprehensiveincomenetoftax)", ignore_errors, context_ids)
        gaap_obj.comprehensive_income_interest = self.get_tag(xbrl, "(us-gaap:comprehensiveincomenetoftaxattributabletononcontrollinginterest)", ignore_errors, context_ids)
        gaap_obj.other_comprehensive_income = self.get_tag(xbrl, "(us-gaap:othercomprehensiveincomelossnetoftax)", ignore_errors, context_ids)

        # Net cash flow statements
        gaap_obj.net_cash_flows_operating = self.get_tag(xbrl, "(us-gaap:netcashprovidedbyusedinoperatingactivities)", ignore_errors, context_ids)
        gaap_obj.net_cash_flows_investing = self.get_tag(xbrl, "(us-gaap:netcashprovidedbyusedininvestingactivities)", ignore_errors, context_ids)
        gaap_obj.net_cash_flows_financing = self.get_tag(xbrl, "(us-gaap:netcashprovidedbyusedinfinancingactivities)", ignore_errors, context_ids)

        gaap_obj.net_cash_flows_operating_continuing = self.get_tag(xbrl, "(us-gaap:netcashprovidedbyusedinoperatingactivitiescontinuingoperations)", ignore_errors, context_ids)
        gaap_obj.net_cash_flows_investing_continuing = self.get_tag(xbrl, "(us-gaap:netcashprovidedbyusedininvestingactivitiescontinuingoperations)", ignore_errors, context_ids)
        gaap_obj.net_cash_flows_financing_continuing = self.get_tag(xbrl, "(us-gaap:netcashprovidedbyusedinfinancingactivitiescontinuingoperations)", ignore_errors, context_ids)

        gaap_obj.net_cash_flows_operating_discontinued = self.get_tag(xbrl, "(us-gaap:cashprovidedbyusedinoperatingactivitiesdiscontinuedoperations)", ignore_errors, context_ids)
        gaap_obj.net_cash_flows_investing_discontinued = self.get_tag(xbrl, "(us-gaap:cashprovidedbyusedininvestingactivitiesdiscontinuedoperations)", ignore_errors, context_ids)

        gaap_obj.net_cash_flows_discontinued = self.get_tag(xbrl, "(us-gaap:netcashprovidedbyusedindiscontinuedoperations)", ignore_errors, context_ids)
        gaap_obj.common_shares_outstanding = self.get_tag(xbrl, "(us-gaap:commonstocksharesoutstanding)", ignore_errors, context_ids)
        gaap_obj.common_shares_issued = self.get_tag(xbrl, "(us-gaap:commonstocksharesissued)", ignore_errors, context_ids)
        gaap_obj.common_shares_authorized = self.get_tag(xbrl, "(us-gaap:commonstocksharesauthorized)", ignore_errors, context_ids)

        return gaap_obj

    def parseDEI(self,
                 xbrl,
                 ignore_errors=0):
        """
        Parse DEI from our XBRL soup and return a DEI object.
        """
        dei_obj = DEI()

        dei_obj.trading_symbol = self.get_tag(xbrl, "(dei:tradingsymbol)", tag_type="String", no_context=True)
        dei_obj.company_name = self.get_tag(xbrl, "(dei:entityregistrantname)", tag_type="String", no_context=True)
        dei_obj.shares_outstanding = self.get_tag(xbrl, "(dei:entitycommonstocksharesoutstanding)", no_context=True)
        dei_obj.public_float = self.get_tag(xbrl, "(dei:entitycommonstocksharesoutstanding)", no_context=True)
        dei_obj.public_float = self.get_tag(xbrl, "(dei:entitypublicfloat)", no_context=True)

        return dei_obj

    def parseCustom(self,
                    xbrl,
                    ignore_errors=0):
        """
        Parse company custom entities from XBRL and return an Custom object.
        """
        custom_obj = Custom()

        custom_data = xbrl.find_all(re.compile('^((?!(us-gaap|dei|xbrll|xbrldi)).)*:\s*',
            re.IGNORECASE | re.MULTILINE))

        elements = {}
        for data in custom_data:
            if XBRLParser().is_number(data.text):
                setattr(custom_obj, data.name.split(':')[1], data.text)

        return custom_obj

    @staticmethod
    def trim_decimals(s, precision=-3):
        """
        Convert from scientific notation using precision
        """
        encoded = s.encode('ascii', 'ignore')
        str_val = ""
        if six.PY3:
            str_val = str(encoded, encoding='ascii', errors='ignore')
        else:
            str_val = str(encoded)

        # Do nothing if precision is 0
        if precision != 0:
            str_val = str_val[:precision]

        if len(str_val) > 0:
            return float(str_val)
        else:
            return 0

    @staticmethod
    def is_number(s):
        """
        Test if value is numeric
        """
        try:
            s = float(s)
            return True
        except ValueError:
            return False

    def get_tag(self,
                xbrl,
                tag,
                ignore_errors=0,
                context_ids=[],
                tag_type="Number",
                no_context=False):
        """
        Returns a tag's value from the XBRL soup.

        :param xbrl: The XBRL soup object returned by parse()
        :param tag: A regex for the tag you would like to retrieve.
        :param tag_type: Valid types are 'String' and 'Number'
        :param ignore_errors: 0: raise exception, halt, 1: ignore, continue, 2: ignore, continue, log

        :returns: The tag's value in the XBRL soup or 0.
        """

        if isinstance(tag, list):
            tags = []
            for _tag in tag:
                tags += xbrl.find_all(name=re.compile(_tag, re.IGNORECASE | re.MULTILINE))
        else:
            tags = xbrl.find_all(name=re.compile(tag, re.IGNORECASE | re.MULTILINE))
        return self.data_processing(tags,
                                    xbrl,
                                    ignore_errors,
                                    context_ids,
                                    options={'type': tag_type,
                                            'no_context': no_context})

    def data_processing(self,
                        elements,
                        xbrl,
                        ignore_errors,
                        context_ids=[],
                        **kwargs):
        """
        Process a XBRL tag object and extract the correct value as
        stated by the context.
        """
        options = kwargs.get('options', {'type': 'Number',
                                         'no_context': False})

        if options['type'] == 'String':
            if len(elements) > 0:
                    return elements[0].text

        if options['no_context'] is True:
            if len(elements) > 0 and XBRLParser().is_number(elements[0].text):
                    return elements[0].text

        try:
            # Extract the correct values by context
            correct_elements = []
            for element in elements:
                std = element.attrs['contextref']
                if std in context_ids:
                    correct_elements.append(element)
            elements = correct_elements

            if len(elements) > 0 and XBRLParser().is_number(elements[0].text):
                attr_precision = elements[0].attrs['decimals']
                if attr_precision is not None:
                    if attr_precision == "INF":
                        # INF precision implies 0.
                        attr_precision = 0

                if elements:
                    return XBRLParser().trim_decimals(elements[0].text, int(attr_precision))
                else:
                    return 0
            else:
                return 0
        except Exception as e:
            print(str(e) + " error at " +
                ''.join(elements[0].text))
            if ignore_errors == 0:
                raise XBRLParserException('value extraction error')
            elif ignore_errors == 1:
                return 0
            elif ignore_errors == 2:
                self.logger.error(str(e) + " error at " +
                    ''.join(elements[0].text))


class XBRLParserException(Exception):
    pass
