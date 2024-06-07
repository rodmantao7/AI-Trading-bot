from lumibot.brokers import Alpaca
from lumibot.backtesting import YahooDataBacktesting
from lumibot.strategies.strategy import Strategy
from lumibot.traders import Trader
from datetime import datetime
from alpaca_trade_api import REST, TimeFrame
from timedelta import Timedelta
from finbert_utils import estimate_sentiment
import pandas as pd
import numpy as np
import math

API_KEY = "PKXNS6BLUP6I6ZFE6Q5F"
API_SECRET = "WCy8MHuTZwnWwwMGCIccZMQtn5R4c3K3RLIzn4vZ"
BASE_URL = "https://paper-api.alpaca.markets/v2"

ALPACA_CREDS = {
    "API_KEY":API_KEY,
    "API_SECRET":API_SECRET,
    "PAPER" : True
}

class MLTrader(Strategy):
    def initialize(self, symbol:str="SPY", cash_at_risk:float=.5, fast_period: int = 10, slow_period: int = 50):
        self.symbol = symbol
        self.sleeptime = "24H"
        self.last_trade = None
        self.cash_at_risk = cash_at_risk
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.api = REST(base_url=BASE_URL, key_id=API_KEY, secret_key=API_SECRET)
        self.data = pd.DataFrame()
    
    def position_sizing(self):
        cash = self.get_cash()
        last_price = self.get_last_price(self.symbol)
        quantity = math.floor(cash * self.cash_at_risk / last_price)
        return cash, last_price, quantity
    
    def fetch_data(self):
        end_date = self.get_datetime()
        start_date = end_date - Timedelta(days=90)  # Fetch 1 day of minute-level data
        bars = self.api.get_bars(self.symbol, timeframe= TimeFrame.Day, start=start_date.isoformat(), end=end_date.isoformat()).df
        self.data = bars[['close']].copy()
        self.data.columns = ['close']

    def calculate_moving_averages(self):
        self.data['fast_ma'] = self.data['close'].rolling(window=self.fast_period).mean()
        self.data['slow_ma'] = self.data['close'].rolling(window=self.slow_period).mean()
    
    def check_crossover(self):
        if len(self.data) < self.slow_period:
            return None
        fast_ma = self.data['fast_ma'].iloc[-1]
        slow_ma = self.data['slow_ma'].iloc[-1]
        prev_fast_ma = self.data['fast_ma'].iloc[-2]
        prev_slow_ma = self.data['slow_ma'].iloc[-2]
        if fast_ma > slow_ma and prev_fast_ma <= prev_slow_ma:
            return 'buy'
        elif fast_ma < slow_ma and prev_fast_ma >= prev_slow_ma:
            return 'sell'
        return None

    def get_dates(self):
        today = self.get_datetime()
        three_days_prior = today - Timedelta(days=3)
        return today.strftime('%Y-%m-%d'), three_days_prior.strftime('%Y-%m-%d')
        
    def get_sentiment(self):
        today, three_days_prior = self.get_dates()
        news = self.api.get_news(symbol=self.symbol, start=three_days_prior, end=today)
        news = [ev.__dict__["_raw"]["headline"] for ev in news]
        probability, sentiment = estimate_sentiment(news)
        return probability, sentiment
    
    def on_trading_iteration(self):
        cash, last_price, quantity = self.position_sizing()
        probability, sentiment = self.get_sentiment()
        self.fetch_data()
        self.calculate_moving_averages()
        signal = self.check_crossover()
        if cash > last_price:  
            if signal == 'buy' or (sentiment == "positive" and probability > .999):
                if self.last_trade == "sell":
                    self.sell_all()
                order = self.create_order(
                    self.symbol,
                    quantity, 
                    "buy",
                    type="bracket",
                    take_profit_price = last_price * 1.20,
                    stop_loss_price = last_price * .95
                )
                self.submit_order(order)
                self.last_trade = "buy"
            elif signal == 'sell' or (sentiment == "negative" and probability >.999):
                if self.last_trade == "buy":
                    self.sell_all()
                order = self.create_order(
                    self.symbol,
                    quantity, 
                    "sell",
                    type="bracket",
                    take_profit_price = last_price * .8,
                    stop_loss_price = last_price * 1.05
                )
                self.submit_order(order)
                self.last_trade = "sell"

start_date = datetime(2020, 1, 1)
end_date = datetime(2024, 5, 31)
broker = Alpaca(ALPACA_CREDS)
strategy = MLTrader(name='mlstrat', broker=broker, parameters={"symbol":"SPY", "cash_at_risk":.5})
strategy.backtest(
    YahooDataBacktesting, 
    start_date, 
    end_date,
    parameters={"symbol":"SPY", "cash_at_risk":.5} 
)