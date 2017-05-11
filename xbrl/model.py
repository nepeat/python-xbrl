import re

try:
    from collections import OrderedDict
except ImportError:
    from ordereddict import OrderedDict

try:
    from io import StringIO
except ImportError:
    from StringIO import StringIO


class XBRLFile(object):
    def __init__(self, fh):
        """
        fh should be a seekable file-like byte stream object
        """
        self.headers = OrderedDict()
        self.fh = fh


# Preprocessing to fix broken XML
# TODO - Run tests to see if other XML processing errors can occur
class XBRLPreprocessedFile(XBRLFile):
    def __init__(self, fh):
        super(XBRLPreprocessedFile, self).__init__(fh)

        if self.fh is None:
            return

        xbrl_string = self.fh.read()

        # find all closing tags as hints
        closing_tags = [t.upper() for t in re.findall(r'(?i)</([a-z0-9_\.]+)>',
                        xbrl_string)]

        # close all tags that don't have closing tags and
        # leave all other data intact
        last_open_tag = None
        tokens = re.split(r'(?i)(</?[a-z0-9_\.]+>)', xbrl_string)
        new_fh = StringIO()
        for idx, token in enumerate(tokens):
            is_closing_tag = token.startswith('</')
            is_processing_tag = token.startswith('<?')
            is_cdata = token.startswith('<!')
            is_tag = token.startswith('<') and not is_cdata
            is_open_tag = is_tag and not is_closing_tag \
                and not is_processing_tag
            if is_tag:
                if last_open_tag is not None:
                    new_fh.write("</%s>" % last_open_tag)
                    last_open_tag = None
            if is_open_tag:
                tag_name = re.findall(r'(?i)<*>', token)[0]
                if tag_name.upper() not in closing_tags:
                    last_open_tag = tag_name
            new_fh.write(token)
        new_fh.seek(0)
        self.fh = new_fh


class XBRL(object):
    def __str__(self):
        return ""

# Base GAAP object
class GAAP(object):
    def __init__(self,
                 assets=0.0,
                 current_assets=0.0,
                 non_current_assets=0.0,
                 liabilities_and_equity=0.0,
                 liabilities=0.0,
                 current_liabilities=0.0,
                 noncurrent_liabilities=0.0,
                 commitments_and_contingencies=0.0,
                 redeemable_noncontrolling_interest=0.0,
                 temporary_equity=0.0,
                 equity=0.0,
                 equity_attributable_interest=0.0,
                 equity_attributable_parent=0.0,
                 stockholders_equity=0.0,
                 revenue=0.0,
                 cost_of_revenue=0.0,
                 gross_profit=0.0,
                 costs_and_expenses=0.0,
                 other_operating_income=0.0,
                 operating_income_loss=0.0,
                 nonoperating_income_loss=0.0,
                 interest_and_debt_expense=0.0,
                 income_before_equity_investments=0.0,
                 income_from_equity_investments=0.0,
                 income_tax_expense_benefit=0.0,
                 extraordary_items_gain_loss=0.0,
                 income_loss=0.0,
                 net_income_shareholders=0.0,
                 preferred_stock_dividends=0.0,
                 net_income_loss_noncontrolling=0.0,
                 net_income_parent=0.0,
                 net_income_loss=0.0,
                 other_comprehensive_income=0.0,
                 comprehensive_income=0.0,
                 comprehensive_income_parent=0.0,
                 comprehensive_income_interest=0.0,
                 net_cash_flows_operating=0.0,
                 net_cash_flows_investing=0.0,
                 net_cash_flows_financing=0.0,
                 net_cash_flows_operating_continuing=0.0,
                 net_cash_flows_investing_continuing=0.0,
                 net_cash_flows_financing_continuing=0.0,
                 net_cash_flows_operating_discontinued=0.0,
                 net_cash_flows_investing_discontinued=0.0,
                 net_cash_flows_discontinued=0.0,
                 common_shares_outstanding=0.0,
                 common_shares_issued=0.0,
                 common_shares_authorized=0.0):
        self.assets = assets
        self.current_assets = current_assets
        self.non_current_assets = non_current_assets
        self.liabilities_and_equity = liabilities_and_equity
        self.liabilities = liabilities
        self.current_liabilities = current_liabilities
        self.noncurrentLiabilities = noncurrent_liabilities
        self.commitments_and_contingencies = commitments_and_contingencies
        self.redeemable_noncontrolling_interest = \
            redeemable_noncontrolling_interest
        self.temporary_equity = temporary_equity
        self.equity = equity
        self.equity_attributable_interest = equity_attributable_interest
        self.equity_attributable_parent = equity_attributable_parent
        self.stockholders_equity = stockholders_equity
        self.revenue = revenue
        self.cost_of_revenue = cost_of_revenue
        self.gross_profit = gross_profit
        self.costs_and_expenses = costs_and_expenses
        self.other_operating_income = other_operating_income
        self.nonoperating_income_loss = nonoperating_income_loss
        self.interest_and_debt_expense = interest_and_debt_expense
        self.income_before_equity_investments = \
            income_before_equity_investments
        self.income_from_equity_investments = income_from_equity_investments
        self.income_tax_expense_benefit = income_tax_expense_benefit
        self.net_income_shareholders = net_income_shareholders
        self.extraordary_items_gain_loss = extraordary_items_gain_loss
        self.income_loss = income_loss
        self.net_income_shareholders = net_income_shareholders
        self.preferred_stock_dividends = preferred_stock_dividends
        self.net_income_loss_noncontrolling = net_income_loss_noncontrolling
        self.net_income_parent = net_income_parent
        self.net_income_loss = net_income_loss
        self.other_comprehensive_income = other_comprehensive_income
        self.comprehensive_income = comprehensive_income
        self.comprehensive_income_parent = comprehensive_income_parent
        self.comprehensive_income_interest = comprehensive_income_interest
        self.net_cash_flows_operating = net_cash_flows_operating
        self.net_cash_flows_investing = net_cash_flows_investing
        self.net_cash_flows_financing = net_cash_flows_financing
        self.net_cash_flows_operating_continuing = \
            net_cash_flows_operating_continuing
        self.net_cash_flows_investing_continuing = \
            net_cash_flows_investing_continuing
        self.net_cash_flows_financing_continuing = \
            net_cash_flows_financing_continuing
        self.net_cash_flows_operating_discontinued = \
            net_cash_flows_operating_discontinued
        self.net_cash_flows_investing_discontinued = \
            net_cash_flows_investing_discontinued
        self.net_cash_flows_discontinued = net_cash_flows_discontinued
        self.common_shares_outstanding = common_shares_outstanding
        self.common_shares_issued = common_shares_issued
        self.common_shares_authorized = common_shares_authorized

# Base DEI object
class DEI(object):
    def __init__(self,
                 trading_symbol='',
                 company_name='',
                 shares_outstanding=0.0,
                 public_float=0.0):
        self.trading_symbol = trading_symbol
        self.company_name = company_name
        self.shares_outstanding = shares_outstanding
        self.public_float = public_float


# Base Custom object
class Custom(object):

    def __init__(self):
        return None

    def __call__(self):
        return self.__dict__.items()
