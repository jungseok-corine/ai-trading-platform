from decimal import Decimal

from pydantic import BaseModel


class PriceQuote(BaseModel):
    symbol_code: str
    current_price: Decimal
    change: Decimal
    change_rate: Decimal
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    volume: int


class MinuteCandle(BaseModel):
    business_date: str
    trade_time: str
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: int


class AccountHolding(BaseModel):
    symbol_code: str
    symbol_name: str
    quantity: int
    avg_purchase_price: Decimal
    current_price: Decimal
    evaluation_amount: Decimal
    profit_loss_amount: Decimal
    profit_loss_rate: Decimal


class AccountSummary(BaseModel):
    total_deposit: Decimal
    total_purchase_amount: Decimal
    total_evaluation_amount: Decimal
    total_profit_loss_amount: Decimal


class AccountBalance(BaseModel):
    holdings: list[AccountHolding]
    summary: AccountSummary
