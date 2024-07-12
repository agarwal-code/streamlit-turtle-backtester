import pandas as pd
import numpy as np
import warnings
import hashlib
from functools import reduce
from io import BytesIO, StringIO
import plotly.express as px
from copy import deepcopy
import xlsxwriter


class Unit:

    def __init__(
        self,
        tradeID,
        long,
        price,
        time,
        tickNum,
        ATR,
        stopLossFactor,
        unitSize,
        lotSize,
        marginFactor,
        secName,
    ):
        self.tradeID = tradeID
        self.long = long
        self.price = price
        self.time = time
        self.tickNum = tickNum
        self.ATR = ATR
        self.stopLossFactor = stopLossFactor
        self.originalStopPrice = (
            (price - self.stopLossFactor * ATR)
            if long
            else (price + self.stopLossFactor * ATR)
        )
        self.stopPrice = self.originalStopPrice
        self.unitSize = unitSize
        self.lotSize = lotSize
        self.value = price * unitSize * lotSize
        self.marginFactor = marginFactor
        self.marginReq = self.value * self.marginFactor
        self.secName = secName

    def isLong(self):
        return self.long

    def isShort(self):
        return not self.long

    def __str__(self) -> str:
        status = "Long" if self.long else "Short"
        return f"""{status} unit for {self.secName}, with size {self.unitSize} contracts.
    Price of {self.price}, at time={self.time}, 
    with stop price {self.stopPrice} and ATR={self.ATR}."""


class Security:

    def __init__(
        self,
        Pf,
        initialData,
        name="test",
        lotSize=None,
        marginFactor=None,
        maxUnits=None,
        ATRAverageRange=None,
        stopLossFactor=None,
        transCost=None,
        slippagePerContract=None,
    ):

        self.Pf = Pf
        self.histData = initialData
        self.name = name

        self.lotSize = self.Pf.lotSize if lotSize is None else lotSize
        self.marginFactor = (
            self.Pf.marginFactor if marginFactor is None else marginFactor
        )
        self.maxUnits = self.Pf.maxUnits if maxUnits is None else maxUnits
        self.ATRAverageRange = (
            self.Pf.ATRAverageRange if ATRAverageRange is None else ATRAverageRange
        )
        self.stopLossFactor = (
            self.Pf.stopLossFactor if stopLossFactor is None else stopLossFactor
        )
        self.transCost = self.Pf.transCost if transCost is None else transCost
        self.slippagePerContract = (
            self.Pf.slippagePerContract
            if slippagePerContract is None
            else slippagePerContract
        )

        self.EMA_length_larger = self.Pf.EMA_length_larger
        self.EMA_length_smaller = self.Pf.EMA_length_smaller
        self.signal_EMA_length = self.Pf.signal_EMA_length
        self.smoothing = self.Pf.smoothing
        self.computeInitialMACD()  # specify the attributes it initializes and computes here TBD

        self.longPositions = []
        self.shortPositions = []

        self.equity = 0

        self.ATR = self.computeInitialATRs()
        self.unitSize = 0
        self.updateUnitSize()

        self.longEntryATR = 0
        self.shortEntryATR = 0

    def computeInitialATRs(self):
        histPriceData = self.histData["price"].values
        TRlist = [
            abs(histPriceData[i] - histPriceData[i - 1])
            for i in range(1, self.ATRAverageRange + 1)
        ]
        ATR = np.mean(TRlist)
        for i in range(self.ATRAverageRange + 1, len(histPriceData)):
            TR = abs(histPriceData[i] - histPriceData[i - 1])
            ATR = (((self.ATRAverageRange - 1) * ATR) + TR) / self.ATRAverageRange

        return ATR

    def updateATR(self, currPrice):
        prevPrice = self.histData["price"].iat[-1]
        trueRange = abs(currPrice - prevPrice)
        self.ATR = (
            ((self.ATRAverageRange - 1) * self.ATR) + trueRange
        ) / self.ATRAverageRange

    def updateUnitSize(self):
        # compute Unit Sizes (i.e., number of contracts in one unit); truncate to ensure integer number
        self.unitSize = int(
            (self.Pf.riskPercentOfAccount / 100 * self.Pf.notionalAccountSize)
            / (self.ATR * self.lotSize)
        )
        if self.unitSize < 0:
            self.unitSize = 0

    def updateEMA(self, EMA, length, smoothing, price):
        multiplier = smoothing / (length + 1)
        EMA = price * multiplier + (1 - multiplier) * EMA
        return EMA

    def computeInitialEMAs(self, length):
        priceData = self.histData["price"]
        self.histData.loc[length - 1, str(length) + "-EMA"] = priceData[:length].mean()
        for i in range(length, len(self.histData.index)):
            self.histData.loc[i, str(length) + "-EMA"] = self.updateEMA(
                EMA=self.histData.loc[i - 1, str(length) + "-EMA"],
                length=length,
                smoothing=self.smoothing,
                price=self.histData.loc[i, "price"],
            )

    def computeInitialMACD(self):
        self.computeInitialEMAs(self.EMA_length_smaller)
        self.computeInitialEMAs(self.EMA_length_larger)

        self.histData["MACD"] = (
            self.histData[str(self.EMA_length_smaller) + "-EMA"]
            - self.histData[str(self.EMA_length_larger) + "-EMA"]
        )

        self.histData.loc[
            (self.EMA_length_larger - 1) + (self.signal_EMA_length - 1), "Signal"
        ] = self.histData.loc[
            (self.EMA_length_larger - 1) : (self.EMA_length_larger - 1)
            + self.signal_EMA_length,
            "MACD",
        ].mean()
        for i in range(
            (self.EMA_length_larger - 1) + self.signal_EMA_length,
            len(self.histData.index),
        ):
            self.histData.loc[i, "Signal"] = self.updateEMA(
                EMA=self.histData.loc[i - 1, "Signal"],
                length=self.signal_EMA_length,
                smoothing=self.smoothing,
                price=self.histData.loc[i - 1, "MACD"],
            )

        self.EMA_larger = self.histData[str(self.EMA_length_larger) + "-EMA"].iloc[-1]
        self.EMA_smaller = self.histData[str(self.EMA_length_smaller) + "-EMA"].iloc[-1]
        self.MACD = self.histData["MACD"].iloc[-1]
        self.signal = self.histData["Signal"].iloc[-1]

    def updateMACD(self, currPrice):
        self.EMA_larger = self.updateEMA(
            EMA=self.EMA_larger,
            length=self.EMA_length_larger,
            smoothing=self.smoothing,
            price=currPrice,
        )
        self.EMA_smaller = self.updateEMA(
            EMA=self.EMA_smaller,
            length=self.EMA_length_smaller,
            smoothing=self.smoothing,
            price=currPrice,
        )
        self.MACD = self.EMA_smaller - self.EMA_larger
        self.signal = self.updateEMA(
            EMA=self.signal,
            length=self.signal_EMA_length,
            smoothing=self.smoothing,
            price=self.MACD,
        )
        lastRowIndex = len(self.histData.index) - 1
        self.histData.loc[lastRowIndex, str(self.EMA_length_larger) + "-EMA"] = (
            self.EMA_larger
        )
        self.histData.loc[lastRowIndex, str(self.EMA_length_smaller) + "-EMA"] = (
            self.EMA_smaller
        )
        self.histData.loc[lastRowIndex, "MACD"] = self.MACD
        self.histData.loc[lastRowIndex, "Signal"] = self.signal

    def priceTotal(self, price, unitSize):
        return price * unitSize * self.lotSize

    def goLong(self, price, time, tradeID, tickNum):
        maxUnitSize = int(
            self.Pf.maxMargin / (self.marginFactor * price * self.lotSize)
        )
        unitSize = maxUnitSize if self.unitSize > maxUnitSize else self.unitSize

        newLongUnit = Unit(
            tradeID=tradeID,
            long=True,
            price=price,
            time=time,
            tickNum=tickNum,
            ATR=self.longEntryATR,
            unitSize=unitSize,
            secName=self.name,
            stopLossFactor=self.stopLossFactor,
            lotSize=self.lotSize,
            marginFactor=self.marginFactor,
        )
        self.longPositions.append(newLongUnit)
        buyAmount = newLongUnit.value
        self.equity -= buyAmount
        return newLongUnit

    def goShort(self, price, time, tradeID, tickNum):
        maxUnitSize = int(
            self.Pf.maxMargin / (self.marginFactor * price * self.lotSize)
        )
        unitSize = maxUnitSize if self.unitSize > maxUnitSize else self.unitSize

        newShortUnit = Unit(
            tradeID=tradeID,
            long=False,
            price=price,
            time=time,
            tickNum=tickNum,
            ATR=self.shortEntryATR,
            unitSize=unitSize,
            secName=self.name,
            stopLossFactor=self.stopLossFactor,
            lotSize=self.lotSize,
            marginFactor=self.marginFactor,
        )
        self.shortPositions.append(newShortUnit)
        sellAmount = newShortUnit.value
        self.equity += sellAmount
        return newShortUnit

    def getPopStats(self, sellPrice, buyPrice, unitSize):
        buyValue = buyPrice * unitSize * self.lotSize
        sellValue = sellPrice * unitSize * self.lotSize
        grossProfit = sellValue - buyValue
        slippageCost = 2 * self.slippagePerContract * self.lotSize * unitSize
        sellTransCost = (
            self.transCost
            * (sellPrice - self.slippagePerContract)
            * self.lotSize
            * unitSize
        )
        buyTransCost = (
            self.transCost
            * (buyPrice + self.slippagePerContract)
            * self.lotSize
            * unitSize
        )
        transCost = sellTransCost + buyTransCost
        # below method is equivalent but above three lines are more obvious
        # transCost = self.transCost * (sellPrice + buyPrice) * self.lotSize * unitSize
        netProfit = sellValue - buyValue - slippageCost - transCost
        return grossProfit, slippageCost, transCost, netProfit

    def popLongUnit(self, currPrice, index):
        unit = self.longPositions.pop(index)
        sellAmount = self.priceTotal(currPrice, unit.unitSize)
        self.equity += sellAmount
        return (
            unit,
            sellAmount,
            *self.getPopStats(
                sellPrice=currPrice, buyPrice=unit.price, unitSize=unit.unitSize
            ),
        )

    def popShortUnit(self, currPrice, index):
        unit = self.shortPositions.pop(index)
        buyAmount = self.priceTotal(currPrice, unit.unitSize)
        self.equity -= buyAmount
        return (
            unit,
            buyAmount,
            *self.getPopStats(
                sellPrice=unit.price, buyPrice=currPrice, unitSize=unit.unitSize
            ),
        )

    def isLongEntered(self):
        return len(self.longPositions) > 0

    def isShortEntered(self):
        return len(self.shortPositions) > 0

    def isLoaded(self):
        return len(self.longPositions) + len(self.shortPositions) >= self.maxUnits

    def summarizeLongPositions(self):
        for unit in self.longPositions:
            print(unit)

    def summarizeShortPositions(self):
        for unit in self.shortPositions:
            print(unit)

    def summarizeAllPositions(self):
        self.summarizeLongPositions()
        self.summarizeShortPositions()

    def getNumLongPositions(self):
        return len(self.longPositions)

    def getNumShortPositions(self):
        return len(self.shortPositions)

    def getNumTotalPositions(self):
        return len(self.longPositions) + len(self.shortPositions)

    def getQuickSummary(self):
        return (
            str(self.getNumLongPositions())
            + "L"
            + " "
            + str(self.getNumShortPositions())
            + "S"
        )


class Portfolio:

    def __init__(
        self,
        securities=None,
        lotSize=15,
        transCost=0.001,
        slippagePerContract=0.5,
        entryType="Breakout",
        longAtHigh=False,
        longBreakout=20,
        shortBreakout=20,
        EMA_length_larger=26,
        EMA_length_smaller=12,
        smoothing=2,
        signal_EMA_length=9,
        ATRAverageRange=20,
        addExtraUnits="As new unit",
        extraUnitATRFactor=0.5,
        useStops=True,
        stopLossFactor=2,
        adjustStopsOnMoreUnits=True,
        adjustStopATRFactor=0.5,
        exitType="Timed",
        exitLongBreakout=5,
        exitShortBreakout=5,
        notionalAccountSize=1000000,
        adjustNotionalAccountSize=True,
        riskPercentOfAccount=1,
        maxPositionLimitEachWay=12,
        maxUnits=4,
        marginFactor=0.25,
        maxMargin=10000000,
    ):

        # list of securities in this portfolio
        self.securities = [] if securities is None else securities

        # lot sizes of securities in portfolio, can be overidden by individual securities (one lot contains lotSize contracts)
        self.lotSize = lotSize

        # transaction cost per rupee of value traded
        self.transCost = transCost

        # slippage cost per contract traded (one lot contains lotSize contracts)
        self.slippagePerContract = slippagePerContract

        # parameters for entry strategy
        self.entryType = entryType
        self.longAtHigh = longAtHigh
        # breakout parameters
        self.longBreakout = longBreakout
        self.shortBreakout = shortBreakout
        # MACD parameters
        self.EMA_length_larger = EMA_length_larger
        self.EMA_length_smaller = EMA_length_smaller
        self.smoothing = smoothing
        self.signal_EMA_length = signal_EMA_length

        # how long should the averaging period for ATR be
        self.ATRAverageRange = ATRAverageRange

        # parameters for adding more units after already entered
        self.addExtraUnits = addExtraUnits
        self.extraUnitATRFactor = extraUnitATRFactor

        # parameters for setting stops
        self.useStops = useStops
        self.stopLossFactor = stopLossFactor
        self.adjustStopsOnMoreUnits = adjustStopsOnMoreUnits
        self.adjustStopATRFactor = adjustStopATRFactor

        # parameters for exit strategy
        self.exitType = exitType
        self.exitLongBreakout = exitLongBreakout
        self.exitShortBreakout = exitShortBreakout
        self.exit_long_breakout_timedelta = pd.Timedelta(seconds=self.exitLongBreakout)
        self.exit_short_breakout_timedelta = pd.Timedelta(
            seconds=self.exitShortBreakout
        )

        # size of notional account in rupees
        self.startingNotionalAccountSize = notionalAccountSize
        self.notionalAccountSize = notionalAccountSize

        self.adjustNotionalAccountSize = adjustNotionalAccountSize

        # amount of risk (in percentage points of account size) willing to tolerate per trade per "day"
        # i.e. when using units, 1 ATR movement of price should
        # represent riskPercentOfAccount * accountSize equity movement
        self.riskPercentOfAccount = riskPercentOfAccount

        # total number of long / short positions (each) allowed
        self.maxPositionLimitEachWay = maxPositionLimitEachWay

        # max number of units allowed per security
        self.maxUnits = maxUnits

        # fraction of nominal value required as margin
        self.marginFactor = marginFactor
        self.maxMargin = maxMargin

        self.marginTotal = 0

        # minimum length of initial data
        self.minLengthOfInitialData = (
            max(
                ATRAverageRange,
                longBreakout,
                shortBreakout,
                EMA_length_larger + EMA_length_smaller,
            )
            + 1
        )

        # counter variables to keep track of number of active long and short positions
        self.numLongPositions = 0
        self.numShortPositions = 0

        # start with zero gross equity
        self.equity = 0

        # real equity takes into account slippage and transaction costs
        self.netEquity = 0

        # start with 0 running total profit
        self.grossProfit = 0
        self.totalNetProfits = 0

        self.totalSlippageCost = 0
        self.totalTransactionCost = 0
        self.averageNetProfit = 0
        self.averageGrossProfit = 0

        tradeBookColumns = [
            "Entry Time",
            "Exit Time",
            "Exit Type",
            "Security",
            "Long / Short",
            "Entry Price",
            "Exit Price",
            "Stop Price",
            "Breakout Exit Price",
            "Position Size",
            "Lot Size",
            "Gross Profit",
            "Slippage Cost",
            "Transaction Cost",
            "Net Profit",
            "Total Net Profits at Entry",
            "ATR at Entry",
            "ATR at Exit",
            "Notional Account at Entry",
            "Trade Margin",
            "Total Margin",
            "Sec Status",
            "Pf Status",
        ]
        self.tradeBook = pd.DataFrame(columns=tradeBookColumns)

    def addSecurity(
        self,
        initialData,
        name="test",
        lotSize=None,
        maxUnits=None,
        ATRAverageRange=None,
        stopLossFactor=None,
        transCost=None,
        slippagePerContract=None,
    ):
        sec = Security(
            Pf=self,
            initialData=initialData,
            lotSize=lotSize,
            name=name,
            maxUnits=maxUnits,
            ATRAverageRange=ATRAverageRange,
            stopLossFactor=stopLossFactor,
            transCost=transCost,
            slippagePerContract=slippagePerContract,
        )
        self.securities.append(sec)

    def generateTradeID(self, timestamp, instrument):
        # Create a unique string from timestamp and instrument
        unique_string = f"{timestamp}_{instrument}"

        # Use hashlib to create a hash of the unique string
        hash_object = hashlib.md5(unique_string.encode())  # Using MD5
        tradeID = (
            hash_object.hexdigest()
        )  # Converts the hash object to a hexadecimal string

        return tradeID

    def goLong(self, sec, price, time, tickNum):
        tradeID = self.generateTradeID(time, sec.name)
        newLongUnit = sec.goLong(price, time, tradeID, tickNum)
        buyAmount = newLongUnit.value
        marginReq = newLongUnit.marginReq

        self.marginTotal += marginReq

        self.numLongPositions += 1
        self.equity -= buyAmount

        newBookRow = {
            "Entry Time": time,
            "Security": sec.name,
            "Long / Short": "Long",
            "Entry Price": price,
            "Position Size": newLongUnit.unitSize,
            "Lot Size": sec.lotSize,
            "ATR at Entry": sec.ATR,
            "Total Net Profits at Entry": self.totalNetProfits,
            "Notional Account at Entry": self.notionalAccountSize,
            "Trade Margin": marginReq,
            "Total Margin": self.marginTotal,
            "Sec Status": sec.getQuickSummary(),
            "Pf Status": self.getQuickSummary(),
        }
        appendToDataFrame(self.tradeBook, newBookRow, tradeID)

    def goShort(self, sec, price, time, tickNum):
        tradeID = self.generateTradeID(time, sec.name)
        newShortUnit = sec.goShort(price, time, tradeID, tickNum)
        sellAmount = newShortUnit.value
        marginReq = newShortUnit.marginReq

        self.marginTotal += marginReq

        self.numShortPositions += 1
        self.equity += sellAmount

        newBookRow = {
            "Entry Time": time,
            "Security": sec.name,
            "Long / Short": "Short",
            "Entry Price": price,
            "Position Size": newShortUnit.unitSize,
            "Lot Size": sec.lotSize,
            "ATR at Entry": sec.ATR,
            "Total Net Profits at Entry": self.totalNetProfits,
            "Notional Account at Entry": self.notionalAccountSize,
            "Trade Margin": marginReq,
            "Total Margin": self.marginTotal,
            "Sec Status": sec.getQuickSummary(),
            "Pf Status": self.getQuickSummary(),
        }
        appendToDataFrame(self.tradeBook, newBookRow, tradeID)

    def popLong(self, sec, price, time, index):
        unit, sellAmount, grossProfit, slippageCost, transCost, netProfit = (
            sec.popLongUnit(price, index)
        )
        self.numLongPositions -= 1
        self.equity += sellAmount
        self.totalNetProfits += netProfit
        self.marginTotal -= unit.marginReq

        columns_to_update = [
            "Stop Price",
            "Exit Time",
            "Exit Type",
            "Exit Price",
            "Gross Profit",
            "Slippage Cost",
            "Transaction Cost",
            "Net Profit",
            "ATR at Exit",
        ]
        values_to_update = [
            unit.stopPrice,
            time,
            self.exitType,
            price,
            grossProfit,
            slippageCost,
            transCost,
            netProfit,
            sec.ATR,
        ]
        updateRowOfDataFrame(
            self.tradeBook, unit.tradeID, values_to_update, columns_to_update
        )
        if self.adjustNotionalAccountSize:
            self.notionalAccountSize += netProfit

    def popShort(self, sec, price, time, index):
        unit, buyAmount, grossProfit, slippageCost, transCost, netProfit = (
            sec.popShortUnit(price, index)
        )
        self.numShortPositions -= 1
        self.equity -= buyAmount
        self.totalNetProfits += netProfit
        self.marginTotal -= unit.marginReq

        columns_to_update = [
            "Stop Price",
            "Exit Time",
            "Exit Type",
            "Exit Price",
            "Gross Profit",
            "Slippage Cost",
            "Transaction Cost",
            "Net Profit",
            "ATR at Exit",
        ]
        values_to_update = [
            unit.stopPrice,
            time,
            self.exitType,
            price,
            grossProfit,
            slippageCost,
            transCost,
            netProfit,
            sec.ATR,
        ]
        updateRowOfDataFrame(
            self.tradeBook, unit.tradeID, values_to_update, columns_to_update
        )
        if self.adjustNotionalAccountSize:
            self.notionalAccountSize += netProfit

    def exitAllLongSec(self, sec, currPrice, time):
        while sec.longPositions:
            self.popLong(sec, currPrice, time, -1)

    def exitAllShortSec(self, sec, currPrice, time):
        while sec.shortPositions:
            self.popShort(sec, currPrice, time, -1)

    def exitAllLong(self, currPriceList, time):
        for sec, currPrice in zip(self.securities, currPriceList):
            self.exitAllLongSec(sec, currPrice, time)

    def exitAllShort(self, currPriceList, time):
        for sec, currPrice in zip(self.securities, currPriceList):
            self.exitAllShortSec(sec, currPrice, time)

    def exitAll(self, currPriceList, time):
        self.exitAllLong(currPriceList, time)
        self.exitAllShort(currPriceList, time)

    def isLongLoaded(self):
        return self.numLongPositions >= self.maxPositionLimitEachWay

    def isShortLoaded(self):
        return self.numShortPositions >= self.maxPositionLimitEachWay

    def getQuickSummary(self):
        numLong = 0
        numShort = 0
        for sec in self.securities:
            numLong += sec.getNumLongPositions()
            numShort += sec.getNumShortPositions()
        if (not (numLong == self.numLongPositions)) or (
            not (numShort == self.numShortPositions)
        ):
            raise RuntimeError("Doesn't match")

        return (
            str(self.numLongPositions) + "L" + " " + str(self.numShortPositions) + "S"
        )

    def updateATRs(self, currPriceList):
        for sec, currPrice in zip(self.securities, currPriceList):
            sec.updateATR(currPrice)

    def updateMACD(self, currPriceList):
        for sec, currPrice in zip(self.securities, currPriceList):
            sec.updateMACD(currPrice)

    def updateUnitSizes(self):
        for sec in self.securities:
            sec.updateUnitSize()

    def updateHistData(self, currPriceList, timeStamp):
        for sec, currPrice in zip(self.securities, currPriceList):
            newRow = {"time": timeStamp, "price": currPrice}
            appendToDataFrame(df=sec.histData, row=newRow)

    def checkToAddNewUnit(self, sec, currPrice, time, tickNum, type, entryType):
        priceCondition = True
        currMACD = sec.MACD
        prevMACD = sec.histData["MACD"].iat[-2]
        currSignal = sec.signal
        prevSignal = sec.histData["Signal"].iat[-2]
        if type == "long":
            entryATR = "longEntryATR"
            tradingFunction = self.goLong
        elif type == "short":
            entryATR = "shortEntryATR"
            tradingFunction = self.goShort

        # Three different type of mutually exclusive entries
        if "Breakout" in entryType:
            breakout_length = getattr(self, type + "Breakout")
            # breakout_seconds = pd.Timedelta(seconds=breakout_length)
            # recentData = sec.histData[sec.histData["time"] >= time - breakout_seconds]
            recentData = sec.histData.iloc[-breakout_length:]
            if len(recentData) < breakout_length:
                prevHigh = np.nan
                prevLow = np.nan
            else:
                prevHigh = recentData["price"].max()
                prevLow = recentData["price"].min()

            if type == "long":
                priceCondition = (
                    currPrice > prevHigh if self.longAtHigh else currPrice < prevLow
                )
                if "MACD-Signal Condition" in entryType:
                    priceCondition = priceCondition and (currMACD > currSignal)
            elif type == "short":
                priceCondition = (
                    currPrice < prevLow if self.longAtHigh else currPrice > prevHigh
                )
                if "MACD-Signal Condition" in entryType:
                    priceCondition = priceCondition and (currMACD < currSignal)
        elif "MACD-Signal Crossover" in entryType:
            if type == "long":
                priceCondition = (currMACD > currSignal) and (prevMACD < prevSignal)
            elif type == "short":
                priceCondition = (currMACD < currSignal) and (prevMACD > prevSignal)
        elif "MACD-Zero Crossover" in entryType:
            if type == "long":
                priceCondition = (currMACD > 0) and (prevMACD < 0)
            elif type == "short":
                priceCondition = (currMACD < 0) and (prevMACD > 0)

        # Finally check the MACD sign condition
        if "Polarity Condition" in entryType:
            if type == "long":
                priceCondition = priceCondition and (prevSignal < 0)
            elif type == "short":
                priceCondition = priceCondition and (prevSignal > 0)

        if priceCondition:
            sec.updateUnitSize()
            setattr(sec, entryATR, sec.ATR)
            tradingFunction(sec, currPrice, time, tickNum)
            return True

        return False

    def checkToAddMoreUnits(self, sec, currPrice, time, tickNum, type):
        if type == "long":
            latestUnit = sec.longPositions[-1]
            priceDifference = currPrice - latestUnit.price
            entryATR = sec.longEntryATR
            positions = sec.longPositions
            adjustStopATRFactor = self.adjustStopATRFactor
            tradingFunction = self.goLong
        elif type == "short":
            latestUnit = sec.shortPositions[-1]
            priceDifference = latestUnit.price - currPrice
            entryATR = sec.shortEntryATR
            positions = sec.shortPositions
            adjustStopATRFactor = -self.adjustStopATRFactor
            tradingFunction = self.goShort
        else:
            raise RuntimeError("Invalid type in tryToAddMoreUnits.")

        if priceDifference >= self.extraUnitATRFactor * entryATR:
            tradingFunction(sec, currPrice, time, tickNum)
            if self.adjustStopsOnMoreUnits:
                totalUnitsNow = len(positions)
                for unitNo, unit in enumerate(positions):
                    unit.stopPrice = (
                        unit.originalStopPrice
                        + (totalUnitsNow - 1 - unitNo) * adjustStopATRFactor * unit.ATR
                    )
            return True

        return False

    def addUnits(self, currPriceList, time, tickNum, position_type):
        unitsAdded = 0
        Position_type = position_type.capitalize()
        for secNo, sec in enumerate(self.securities):
            if (not sec.isLoaded()) and (
                not getattr(self, f"is{Position_type}Loaded")()
            ):
                currPrice = currPriceList[secNo]
                if not getattr(sec, f"is{Position_type}Entered")():
                    unitsAdded += self.checkToAddNewUnit(
                        sec=sec,
                        currPrice=currPrice,
                        time=time,
                        tickNum=tickNum,
                        type=position_type,
                        entryType=self.entryType,
                    )
                else:
                    if self.addExtraUnits == "As new unit":
                        unitsAdded += self.checkToAddNewUnit(
                            sec=sec,
                            currPrice=currPrice,
                            time=time,
                            tickNum=tickNum,
                            type=position_type,
                            entryType=self.entryType,
                        )
                    elif self.addExtraUnits == "Using ATR":
                        unitsAdded += self.checkToAddMoreUnits(
                            sec, currPrice, time, tickNum, position_type
                        )
                    elif self.addExtraUnits == "No":
                        pass
                    else:
                        raise RuntimeError(
                            "Invalid type for Portfolio attribute addExtraUnits"
                        )
        return unitsAdded

    def checkEntries(self, currPriceList, time, tickNum):
        unitsAdded = 0
        unitsAdded += self.addUnits(currPriceList, time, tickNum, "long")
        unitsAdded += self.addUnits(currPriceList, time, tickNum, "short")
        return unitsAdded

    def checkStopsByPositionType(self, currPriceList, time, positionType):
        numStoppedOut = 0
        if positionType == "long":
            stopCondition = "currPrice < unit.stopPrice"
        elif positionType == "short":
            stopCondition = "currPrice > unit.stopPrice"
        popFunction = getattr(self, f"pop{positionType.capitalize()}")

        for secNo, sec in enumerate(self.securities):
            positions = getattr(sec, f"{positionType}Positions")
            currPrice = currPriceList[secNo]
            for unitNo in range(len(positions) - 1, -1, -1):
                unit = positions[unitNo]
                if eval(stopCondition):
                    popFunction(sec, currPrice, time, unitNo)
                    updateRowOfDataFrame(
                        df=self.tradeBook,
                        index=unit.tradeID,
                        values=["Stop out"],
                        columns=["Exit Type"],
                    )
                    numStoppedOut += 1

        return numStoppedOut

    def checkStops(self, currPriceList, time):

        if not self.useStops:
            return

        totalStoppedOut = self.checkStopsByPositionType(
            currPriceList=currPriceList, time=time, positionType="long"
        ) + self.checkStopsByPositionType(
            currPriceList=currPriceList, time=time, positionType="short"
        )

        return totalStoppedOut

    def checkExits(self, currPriceList, time, tickNum):

        numExits = 0

        if self.exitType == "Timed":
            for sec, currPrice in zip(self.securities, currPriceList):
                # can only check the first position each time because positions are stored
                # in ascending order w.r.t. time
                while sec.longPositions and (
                    tickNum - sec.longPositions[0].tickNum >= self.exitLongBreakout
                ):
                    self.popLong(sec, currPrice, time, 0)
                    numExits += 1
                while sec.shortPositions and (
                    tickNum - sec.shortPositions[0].tickNum >= self.exitShortBreakout
                ):
                    self.popShort(sec, currPrice, time, 0)
                    numExits += 1
        elif self.exitType == "Breakout":
            for sec, currPrice in zip(self.securities, currPriceList):
                histPriceData = sec.histData["price"]
                if sec.isLongEntered():
                    prevLow = histPriceData[-self.exitLongBreakout :].min()
                    if currPrice < prevLow:
                        while sec.longPositions:
                            unit = sec.longPositions[-1]
                            self.popLong(sec, currPrice, time, -1)
                            updateRowOfDataFrame(
                                df=self.tradeBook,
                                index=unit.tradeID,
                                values=[prevLow],
                                columns=["Breakout Exit Price"],
                            )
                            numExits += 1
                if sec.isShortEntered():
                    prevHigh = histPriceData[-self.exitLongBreakout :].max()
                    if currPrice > prevHigh:
                        while sec.shortPositions:
                            unit = sec.shortPositions[-1]
                            self.popShort(sec, currPrice, time, -1)
                            updateRowOfDataFrame(
                                df=self.tradeBook,
                                index=unit.tradeID,
                                values=[prevHigh],
                                columns=["Breakout Exit Price"],
                            )
                            numExits += 1
        elif self.exitType == "MACD-Signal Crossover":
            for sec, currPrice in zip(self.securities, currPriceList):
                currMACD = sec.MACD
                prevMACD = sec.histData["MACD"].iat[-2]
                currSignal = sec.signal
                prevSignal = sec.histData["Signal"].iat[-2]
                if (currMACD < currSignal) and (prevMACD > prevSignal):
                    while sec.longPositions:
                        unit = sec.longPositions[-1]
                        self.popLong(sec, currPrice, time, -1)
                        numExits += 1
                if (currMACD > currSignal) and (prevMACD < prevSignal):
                    while sec.shortPositions:
                        unit = sec.shortPositions[-1]
                        self.popShort(sec, currPrice, time, -1)
                        numExits += 1

        else:
            raise RuntimeError(
                "Portfolio attribute exitType is neither Timed nor Breakout."
            )

        return numExits

    def preparePortfolioFromDataFrames(self, dataframesDict, lotSizeDict=None):
        dataframesDict = deepcopy(dataframesDict)

        # Function to merge DataFrames on 'time'
        def merge_dfs_on_time(df_list):
            # Use functools.reduce to perform cumulative inner merge
            merged_df = reduce(
                lambda left, right: pd.merge(left, right, on="time", how="inner"),
                df_list,
            )
            merged_df.reset_index(drop=True, inplace=True)
            return merged_df

        # Preparing each DataFrame by renaming the 'price' column to a unique name
        for i, df in enumerate(dataframesDict.values()):
            df.rename(columns={"price": f"price_{i + 1}"}, inplace=True)

        # Merge all DataFrames
        df = merge_dfs_on_time(list(dataframesDict.values()))

        # # Retain only the longest continuous sequence of data points
        # df = retain_largest_continuous_sequence(df)

        df.reset_index(inplace=True, drop=True)

        # Get a list of all columns that start with 'price_'
        price_columns = [col for col in df.columns if col.startswith("price_")]

        for col, secName in zip(price_columns, dataframesDict.keys()):
            initialData = df.iloc[: self.minLengthOfInitialData][["time", col]].copy()
            initialData.rename(columns={col: "price"}, inplace=True)
            if lotSizeDict is None:
                self.addSecurity(initialData=initialData, name=secName)
            else:
                self.addSecurity(
                    initialData=initialData, name=secName, lotSize=lotSizeDict[secName]
                )

        df = df.iloc[self.minLengthOfInitialData :].copy()
        df.reset_index(inplace=True, drop=True)

        self.priceData = df

    def run_simulation(self, progress_callback=None):
        # Cache the locations of price columns once, outside of the loop
        price_column_numbers = [
            self.priceData.columns.get_loc(col)
            for col in self.priceData.columns
            if col.startswith("price")
        ]

        def get_time_and_prices(row):
            # Extract time and prices from a given row
            time = row["time"]
            prices = [row.iloc[col] for col in price_column_numbers]
            return time, prices

        total_rows = len(self.priceData.index)
        for rowNo in range(total_rows):
            row = self.priceData.iloc[rowNo]
            time, prices = get_time_and_prices(row)
            self.updateATRs(prices)
            self.updateMACD(prices)
            self.updateUnitSizes()
            self.checkStops(prices, time)
            self.checkExits(currPriceList=prices, time=time, tickNum=rowNo)
            self.checkEntries(currPriceList=prices, time=time, tickNum=rowNo)
            self.updateHistData(prices, time)

            # Update progress bar if a callback is provided
            if progress_callback:
                progress_callback((rowNo + 1) / total_rows)

        # Handle final row
        final_row = self.priceData.iloc[-1]
        time, prices = get_time_and_prices(final_row)
        self.exitAll(prices, time)
        self.processTradeBook()

    def processTradeBook(self):
        # self.tradeBook["Running Net Profit"] = self.tradeBook["Net Profit"].cumsum()
        # self.totalNetProfits = self.tradeBook["Net Profit"].sum()
        self.grossProfit = self.tradeBook["Gross Profit"].sum()
        self.totalSlippageCost = self.tradeBook["Slippage Cost"].sum()
        self.totalTransactionCost = self.tradeBook["Transaction Cost"].sum()
        self.averageNetProfit = self.tradeBook["Net Profit"].mean()
        self.averageGrossProfit = self.tradeBook["Gross Profit"].mean()

        if not self.useStops:
            self.tradeBook.drop("Stop Price", axis=1, inplace=True)

    def getStats(self):
        # tradeBookColumns = [
        #     "Entry time",
        #     "Exit time",
        #     "Security",
        #     "Long / Short",
        #     "Entry Price",
        #     "Exit Price",
        #     "Position Size",
        #     "Gross Profit",
        #     "Slippage cost",
        #     "Transaction cost",
        #     "Net Profit",
        # ]
        max_margin_index = self.tradeBook["Total Margin"].idxmax()
        entry_time = self.tradeBook.loc[max_margin_index, "Entry Time"]
        row_number = (
            self.tradeBook.index.get_loc(max_margin_index) + 2
        )  # + 1 for header and + 1 because python is zero indexed as opposed to excel
        margin_string = f"{self.tradeBook['Total Margin'].max():,.2f} at {entry_time} (Row {row_number} in excel sheet)"

        stats = {
            "Net Profit": f"{self.totalNetProfits:,.2f}",
            "Gross Profit": f"{self.grossProfit:,.2f}",
            "Slippage Cost": f"{self.totalSlippageCost:,.2f}",
            "Transaction Cost": f"{self.totalTransactionCost:,.2f}",
            "Average Net Profit": f"{self.averageNetProfit:,.2f}",
            "Average Gross Profit": f"{self.averageGrossProfit:,.2f}",
            "Maximum Total Margin Requirement": margin_string,
        }

        return stats

    def getPortfolioParametersDict(self):
        data_dict = {
            "Transaction cost": self.transCost,
            "Slippage per contract": self.slippagePerContract,
            "Entry strategy": str(self.entryType),
        }
        if "Breakout" in self.entryType:
            data_dict["Long at highs"] = self.longAtHigh
            data_dict["Long breakout length"] = self.longBreakout
            data_dict["Short breakout length"] = self.shortBreakout
        if "MACD" in self.entryType or "Signal" in self.entryType:
            data_dict["Longer EMA length"] = self.EMA_length_larger
            data_dict["Shorter EMA length"] = self.EMA_length_smaller
            data_dict["Smoothing factor"] = self.smoothing
            data_dict["Signal EMA length"] = self.signal_EMA_length

        # how long should the averaging period for ATR be
        data_dict["ATR Average Range"] = self.ATRAverageRange

        # parameters for adding more units after already entered
        data_dict["Add extra units"] = self.addExtraUnits
        data_dict["Extra unit ATR factor"] = self.extraUnitATRFactor

        # parameters for setting stops
        data_dict["Use stops"] = self.useStops
        data_dict["Stop Loss ATR factor"] = self.stopLossFactor
        data_dict["Adjust stops on adding additional units"] = (
            self.adjustStopsOnMoreUnits
        )
        data_dict["Adjust stop ATR Factor"] = self.adjustStopATRFactor

        # parameters for exit strategy
        data_dict["Exit strategy"] = self.exitType
        data_dict[f"Long exit {self.exitType}"] = self.exitLongBreakout
        data_dict[f"Short exit {self.exitType}"] = self.exitShortBreakout

        # size of notional account in rupees
        data_dict["Starting notional Account Size"] = self.startingNotionalAccountSize

        # amount of risk (in percentage points of account size) willing to tolerate per trade per "day"
        # i.e. when using units, 1 ATR movement of price should
        # represent riskPercentOfAccount * accountSize equity movement
        data_dict["Risk per trade per tick as percent of account size"] = (
            self.riskPercentOfAccount
        )

        # total number of long / short positions (each) allowed
        data_dict["Max position limit each way"] = self.maxPositionLimitEachWay

        # max number of units allowed per security
        data_dict["Max units per security"] = self.maxUnits

        data_dict["Margin percentage"] = self.marginFactor
        data_dict["Max margin per trade"] = self.maxMargin

        return data_dict

    def getTradeBook(self, format=None, parameter_sheet=False):
        if format is None:
            return self.tradeBook
        elif format == "excel":
            excel_io = dataframe_to_excel(self.tradeBook)

            if parameter_sheet:

                parameter_dict = self.getPortfolioParametersDict()

                excel_io = add_sheet_from_dict(
                    excel_io=excel_io,
                    data_dict=parameter_dict,
                    sheet_name="Parameters",
                    col_names=["Parameter", "Value"],
                )

            return excel_io
        elif format == "csv":
            return dataframe_to_csv(self.tradeBook)
        else:
            raise RuntimeError("Invalid format provided")


def prepareDataFramesFromExcel(excel_file, sheet_names):
    # Retrieve a dictionary of dataframes, with sheet_name as key
    dataframesDict = pd.read_excel(excel_file, sheet_name=list(sheet_names), header=1)

    # Process each sheet
    for key, df in dataframesDict.items():
        # Assuming columns are identified by names containing keywords
        time_col = next((col for col in df.columns if "time" in col.lower()), None)
        price_col = next(
            (
                col
                for col in df.columns
                if "net" in col.lower()
                or "amount" in col.lower()
                or "price" in col.lower()
            ),
            None,
        )

        if time_col is None:
            raise RuntimeError("Could not identify time column in data")
        if price_col is None:
            raise RuntimeError("Could not identify price column in data")

        # Rename columns based on detected names
        df.rename(columns={time_col: "time", price_col: "price"}, inplace=True)

        # Convert 'time' to datetime
        try:
            df["time"] = pd.to_datetime(
                df["time"], format="%d/%m/%Y, %I:%M:%S %p", errors="raise"
            )
        except ValueError:
            pass

        df["price"] = pd.to_numeric(df["price"], errors="coerce").abs()

        # # Retain only the longest continuous sequence of data points
        # df = retain_largest_continuous_sequence(df)
        # df.reset_index(inplace=True, drop=True)

        # Remove duplicate times
        df.drop_duplicates(subset=["time"], inplace=True)

        # Handling missing values - example of dropping them
        df.dropna(subset=["time", "price"], inplace=True)

        # df.sort_values(by="time", ascending=True, inplace=True)

        # Reassign cleaned dataframe back to dictionary
        dataframesDict[key] = df[["time", "price"]].copy()

    return dataframesDict


def computeEdgeRatios(
    dfDict,
    timePeriodRangeStart=1,
    timePeriodRangeEnd=50,
    timePeriodStep=1,
    longBreakout=20,
    shortBreakout=20,
    longAtHigh=False,
    ATRAverageRange=20,
    getPlots=False,
):

    # ensure we do not alter the original passed dictionary of dataframes by using a deepcopy instead
    dfDict = deepcopy(dfDict)

    def computeBreakoutsAndATRs(df):
        df["price"] = abs(df["price"])
        df["TR"] = abs(df["price"].diff())
        df = df.drop(df.index[0])
        df.reset_index(inplace=True, drop=True)
        df.loc[ATRAverageRange, "ATR"] = df.loc[1:ATRAverageRange, "TR"].mean()
        for i in range(ATRAverageRange + 1, len(df.index)):
            df.loc[i, "ATR"] = (
                (ATRAverageRange - 1) * df.loc[i - 1, "ATR"] + df.loc[i, "TR"]
            ) / ATRAverageRange

        df["highs"] = (
            df["price"]
            .rolling(window=longBreakout, min_periods=longBreakout)
            .max()
            .shift(1)
        )
        df["lows"] = (
            df["price"]
            .rolling(window=shortBreakout, min_periods=shortBreakout)
            .min()
            .shift(1)
        )

        if longAtHigh:
            df["longEntry"] = df["price"] > df["highs"]
            df["shortEntry"] = df["price"] < df["lows"]
        else:
            df["longEntry"] = df["price"] < df["lows"]
            df["shortEntry"] = df["price"] > df["highs"]

        return df

    timePeriods = list(
        range(timePeriodRangeStart, timePeriodRangeEnd + 1, timePeriodStep)
    )
    numtimePeriods = len(timePeriods)

    def computeEdgeRatiosAndSumsForSec(df):
        prices = df["price"].values
        atrs = df["ATR"].values
        long_entries = df["longEntry"].values
        short_entries = df["shortEntry"].values

        E_ratios = []
        sumMFEs = []
        sumMAEs = []

        for timePeriod in timePeriods:
            # Rolling calculations
            rolling_max = (
                pd.Series(prices)
                .rolling(window=timePeriod + 1)
                .max()
                .shift(-timePeriod)
            )
            rolling_min = (
                pd.Series(prices)
                .rolling(window=timePeriod + 1)
                .min()
                .shift(-timePeriod)
            )

            sumMFE, sumMAE, count = 0.0, 0.0, 0

            for i in range(len(df) - timePeriod):
                if long_entries[i] or short_entries[i]:
                    currPrice = prices[i]
                    currATR = atrs[i]

                    if long_entries[i]:
                        MFE = rolling_max[i] - currPrice
                        MAE = currPrice - rolling_min[i]
                    elif short_entries[i]:
                        MFE = currPrice - rolling_min[i]
                        MAE = rolling_max[i] - currPrice

                    norMFE = MFE / currATR
                    norMAE = MAE / currATR
                    sumMFE += norMFE
                    sumMAE += norMAE
                    count += 1

            if count > 0:
                # averageMFE = sumMFE / count
                # averageMAE = sumMAE / count
                sumMFEs.append(sumMFE)
                sumMAEs.append(sumMAE)
                if sumMAE == 0:
                    E_ratio = np.inf
                    if sumMFE == 0:
                        E_ratio = np.nan
                else:
                    E_ratio = sumMFE / sumMAE
                E_ratios.append(E_ratio)
            else:
                sumMFEs.append(np.nan)
                sumMAEs.append(np.nan)
                E_ratios.append(np.nan)

        return sumMFEs, sumMAEs, E_ratios

    # TBD can doing below using numpy
    E_ratios = {}
    allSecMFEs = [0] * numtimePeriods
    allSecMAEs = [0] * numtimePeriods
    for (
        sec,
        df,
    ) in dfDict.items():
        df = computeBreakoutsAndATRs(df)
        sumMFEs, sumMAEs, E_ratios_sec = computeEdgeRatiosAndSumsForSec(df)
        E_ratios[sec] = E_ratios_sec
        allSecMFEs = [x + y for x, y in zip(allSecMFEs, sumMFEs)]
        allSecMAEs = [x + y for x, y in zip(allSecMAEs, sumMAEs)]

    if len(dfDict) != 1:
        E_ratiosForAllSecs = [
            MFE / MAE if MAE != 0 else float("nan")
            for MFE, MAE in zip(allSecMFEs, allSecMAEs)
        ]
        E_ratios["all securities"] = E_ratiosForAllSecs

    if getPlots:
        E_ratios_dfs_figs = {}
        for sec, ratios in E_ratios.items():
            df = pd.DataFrame({"Time Period": timePeriods, "Edge Ratio": ratios})
            fig = px.line(
                df,
                x="Time Period",
                y="Edge Ratio",
                title=f"Edge Ratios Over Time Periods for {sec}",
                markers=True,  # This adds the dots on each line point
            )
            # Customizing hover data
            fig.update_traces(
                mode="markers+lines",  # Ensure both markers and lines are shown
                hoverinfo="all",  # This ensures all relevant data shows on hover
            )
            E_ratios_dfs_figs[sec] = (df, fig)
        return E_ratios_dfs_figs
    else:
        return E_ratios


def dataframe_to_excel(df, file_name=None):
    """
    Converts a DataFrame to an Excel file, formatting columns appropriately.
    If file_name is provided, writes the file locally. If file_name is None,
    returns an in-memory file-like object containing the Excel data.

    Args:
        df (pandas.DataFrame): The DataFrame to convert.
        file_name (str, optional): The file path where the Excel file will be saved.
                                   If None, the function returns a BytesIO object.

    Returns:
        io.BytesIO or None: Returns a BytesIO object if file_name is None,
                            otherwise writes the file locally and returns None.
    """
    output = BytesIO() if file_name is None else file_name

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")

        workbook = writer.book
        worksheet = writer.sheets["Sheet1"]

        # Format for floats to limit to two decimal places
        float_format = workbook.add_format({"num_format": "0.00"})

        # Adjust column widths and apply formatting
        for idx, col in enumerate(df):
            series = df[col]
            if pd.api.types.is_float_dtype(series):
                max_len = (
                    max(
                        series.map(lambda x: len(f"{x:.2f}")).max(),
                        len(str(series.name)),
                    )
                    + 1
                )
                worksheet.set_column(idx, idx, max_len, float_format)
            else:
                max_len = (
                    max(series.astype(str).map(len).max(), len(str(series.name))) + 1
                )
                worksheet.set_column(idx, idx, max_len)

    if file_name is None:
        output.seek(0)
        return output


def add_sheet_from_dict(excel_io, data_dict, sheet_name, col_names):
    # Read the existing content of the BytesIO object
    excel_io.seek(0)  # Ensure we're at the beginning of the BytesIO object
    with pd.ExcelFile(excel_io, engine="openpyxl") as reader:
        existing_sheets = reader.sheet_names

        with pd.ExcelWriter(
            excel_io, engine="openpyxl", mode="a", if_sheet_exists="overlay"
        ) as writer:
            # Write each existing sheet back to the writer
            for sheet in existing_sheets:
                df = reader.parse(sheet)
                if (
                    sheet != sheet_name
                ):  # Skip writing back the sheet if the name clashes
                    df.to_excel(writer, sheet_name=sheet, index=False)

            # Create a DataFrame from the dictionary
            df_dict = pd.DataFrame(list(data_dict.items()), columns=list(col_names))

            # Write the new DataFrame to the new sheet
            if sheet_name in existing_sheets:
                writer.remove(
                    writer.sheets[sheet_name]
                )  # Remove the existing sheet if it exists

            df_dict.to_excel(writer, sheet_name=sheet_name, index=False)

            # Adjust column widths
            worksheet = writer.sheets[sheet_name]
            for idx, col in enumerate(df_dict.columns):
                max_len = max(df_dict[col].astype(str).map(len).max(), len(col)) + 1
                worksheet.column_dimensions[chr(65 + idx)].width = max_len

    # Reset the pointer of the BytesIO object
    excel_io.seek(0)
    return excel_io


def dataframe_to_csv(df):
    """
    Converts a DataFrame to a CSV format stored in memory.

    Args:
    df (pandas.DataFrame): The DataFrame to convert.

    Returns:
    io.StringIO: An in-memory file-like object containing the CSV data.
    """
    # Create a string buffer
    output = StringIO()
    df.to_csv(output, index=False)
    # Rewind the buffer to the beginning after writing
    output.seek(0)
    return output


def appendToDataFrame(df, row, index=None, ignore_index=True):
    """
    Appends a new row to the DataFrame.

    Parameters:
        df (pd.DataFrame): The DataFrame to which the row will be appended.
        row (dict or pd.Series): The new row to append. Can be a dictionary or a pandas Series.
        ignore_index (bool): Whether to ignore the index of the appended row. If True, the index is reset.

    Returns:
        pd.DataFrame: A new DataFrame with the appended row.
    """
    # # Check if the row is a dictionary and convert it to a DataFrame
    # if isinstance(row, dict):
    #     row_df = pd.DataFrame([row])
    # elif isinstance(row, pd.Series):
    #     row_df = pd.DataFrame([row.values], columns=row.index)
    # else:
    #     raise ValueError("Row must be a dict or pd.Series")

    # # Concatenate the original DataFrame with the new row DataFrame
    # return pd.concat([df, row_df], ignore_index=ignore_index)

    if index is None:
        index = len(df.index)

    # Ignore a specific warning by message and category
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=FutureWarning)
        # Only within this block, the specified warning will be ignored
        df.loc[index] = row


def updateRowOfDataFrame(df, index, values, columns):
    # Ignore a specific warning by message and category
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=FutureWarning)
        # Only within this block, the specified warning will be ignored
        df.loc[index, columns] = values


# def retain_largest_continuous_sequence(df, time_column="time"):
#     df[time_column] = pd.to_datetime(
#         df[time_column]
#     )  # Convert to datetime if not already
#     df["time_diff"] = (
#         df[time_column].diff().dt.total_seconds().abs()
#     )  # Calculate time differences in seconds

#     # Group by breaks in the 1-second sequence
#     df["group"] = (df["time_diff"] != 1).cumsum()

#     # Identify the largest group with 1-second intervals
#     group_sizes = df.groupby("group").size()
#     largest_group = group_sizes.idxmax()

#     # Filter the DataFrame to only include the largest continuous 1-second spaced group
#     df_filtered = df[df["group"] == largest_group].copy()

#     # Optionally, drop the helper columns
#     df_filtered.drop(["time_diff", "group"], axis=1, inplace=True)

#     return df_filtered
