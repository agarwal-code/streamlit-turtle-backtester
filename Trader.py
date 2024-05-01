import pandas as pd
import numpy as np
import warnings


class Unit:
    def __init__(
        self, long, price, time, ATR, stopLossFactor, unitSize=1, secName="test"
    ):
        self.long = long
        self.price = price
        self.time = time
        self.ATR = ATR
        self.stopLossFactor = stopLossFactor
        self.stopPrice = (
            (price - self.stopLossFactor * ATR)
            if long
            else (price + self.stopLossFactor * ATR)
        )
        self.unitSize = unitSize
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
        lotSize=None,
        name="test",
        maxUnits=4,
        ATRAverageRange=None,
        stopLossFactor=None,
    ):

        self.Pf = Pf
        self.histData = initialData
        self.lotSize = self.Pf.lotSize if lotSize is None else lotSize
        self.name = name
        self.longPositions = []
        self.shortPositions = []
        self.maxUnits = self.Pf.maxUnits if maxUnits is None else maxUnits
        self.profit = 0

        self.ATRAverageRange = (
            self.Pf.ATRAverageRange if ATRAverageRange is None else ATRAverageRange
        )
        self.ATR = self.computeInitialATRs()
        self.unitSize = 0
        self.updateUnitSize()

        self.longEntryATR = 0
        self.shortEntryATR = 0

        self.stopLossFactor = (
            self.Pf.stopLossFactor if stopLossFactor is None else stopLossFactor
        )

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

    def updateHistData(self, currPrice, timeStamp):
        self.histData.loc[len(self.histData)] = [timeStamp, currPrice]

    def updateUnitSize(self):
        # compute Unit Sizes (i.e., number of contracts in one unit); truncate to ensure integer number
        self.unitSize = int(
            (self.Pf.riskPercentOfAccount / 100 * self.Pf.notionalAccountSize)
            / (self.ATR * self.lotSize)
        )

    def priceToRupees(self, price, unitSize=None):
        unitSize = self.unitSize if unitSize is None else unitSize
        return price * unitSize * self.lotSize

    def goLong(self, price, time):
        self.profit -= self.priceToRupees(price)
        newLongUnit = Unit(
            long=True,
            price=price,
            time=time,
            ATR=self.longEntryATR,
            unitSize=self.unitSize,
            secName=self.name,
            stopLossFactor=self.stopLossFactor,
        )
        self.longPositions.append(newLongUnit)

    def goShort(self, price, time):
        self.profit += self.priceToRupees(price)
        newShortUnit = Unit(
            long=False,
            price=price,
            time=time,
            ATR=self.shortEntryATR,
            unitSize=self.unitSize,
            secName=self.name,
            stopLossFactor=self.stopLossFactor,
        )
        self.shortPositions.append(newShortUnit)

    def popLongUnit(self, currPrice, index):
        unit = self.longPositions.pop(index)
        sellAmount = self.priceToRupees(currPrice, unit.unitSize)
        self.profit += sellAmount
        buyAmount = self.priceToRupees(unit.price, unit.unitSize)
        netProfitFromUnit = sellAmount - buyAmount
        return netProfitFromUnit, sellAmount, unit.time

    def popShortUnit(self, currPrice, index):
        unit = self.shortPositions.pop(index)
        buyAmount = self.priceToRupees(currPrice, unit.unitSize)
        self.profit -= buyAmount
        sellAmount = self.priceToRupees(unit.price, unit.unitSize)
        netProfitFromUnit = sellAmount - buyAmount
        return netProfitFromUnit, buyAmount, unit.time

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
        longBreakout=20,
        shortBreakout=20,
        longAtHigh=True,
        addExtraUnits="New",
        extraUnitATRFactor=0.5,
        useStops=True,
        stopLossFactor=2,
        adjustStopsOnMoreUnits=True,
        exitType="Timed",
        exitLongBreakout=80,
        exitShortBreakout=80,
        notionalAccountSize=100000,
        riskPercentOfAccount=1,
        maxPositionLimitEachWay=12,
        ATRAverageRange=20,
        maxUnits=4,
        lotSize=15,
    ):

        # list of securities in this portfolio
        self.securities = [] if securities is None else securities

        self.lotSize = lotSize

        # size of notional account in rupees
        self.notionalAccountSize = notionalAccountSize

        # amount of risk (in percentage points of account size) willing to tolerate per trade per "day"
        # i.e. when using units, 1 ATR movement of price should
        # represent riskPercentOfAccount * accountSize equity movement
        self.riskPercentOfAccount = riskPercentOfAccount

        # total number of long / short positions (each) allowed
        self.maxPositionLimitEachWay = maxPositionLimitEachWay

        # max number of units allowed per security
        self.maxUnits = maxUnits

        # how long should the averaging period for ATR be
        self.ATRAverageRange = ATRAverageRange

        # parameters for entry strategy
        self.longBreakout = longBreakout
        self.shortBreakout = shortBreakout
        self.longAtHigh = longAtHigh

        # minimum length of initial data
        self.minLengthOfInitialData = (
            max(ATRAverageRange, longBreakout, shortBreakout) + 1
        )

        # parameters for adding more units after already entered
        self.addExtraUnits = addExtraUnits
        self.extraUnitATRFactor = extraUnitATRFactor

        # parameters for setting stops
        self.useStops = useStops
        self.stopLossFactor = stopLossFactor
        self.adjustStopsOnMoreUnits = adjustStopsOnMoreUnits

        # parameters for exit strategy
        self.exitType = exitType
        self.exitLongBreakout = exitLongBreakout
        self.exitShortBreakout = exitShortBreakout
        self.exit_long_breakout_timedelta = pd.Timedelta(seconds=self.exitLongBreakout)
        self.exit_short_breakout_timedelta = pd.Timedelta(
            seconds=self.exitShortBreakout
        )

        # counter variables to keep track of number of active long and short positions
        self.numLongPositions = 0
        self.numShortPositions = 0

        # start with zero equity
        self.equity = 0

        self.totalLong = 0
        self.totalShort = 0

        columns = [
            "Time",
            "Action",
            "Long / Short",
            "Security",
            "Price",
            "Equity",
            "Equity change",
            "Status of sec",
            "Entered at",
            "Profit from trade",
            "Unit Size",
            "Lot Size",
        ]

        self.tradeHistory = pd.DataFrame(columns=columns)

    # def addSecurity(self, sec): # this is clashing with the function below TBD
    #     self.securities.append(sec)

    def addSecurity(
        self,
        initialData,
        name="test",
        lotSize=None,
        maxUnits=None,
        ATRAverageRange=None,
        stopLossFactor=None,
    ):
        sec = Security(
            Pf=self,
            initialData=initialData,
            lotSize=lotSize,
            name=name,
            maxUnits=maxUnits,
            ATRAverageRange=ATRAverageRange,
            stopLossFactor=stopLossFactor,
        )
        self.securities.append(sec)

    def adjustAccountSize(self):
        # TBD
        pass

    def goLong(self, sec, price, time):
        sec.goLong(price, time)
        self.numLongPositions += 1
        self.equity -= sec.priceToRupees(price)

        # Create a new DataFrame row with NA entries
        newRow = {
            "Time": time,
            "Action": "Enter",
            "Long / Short": "Long",
            "Security": sec.name,
            "Price": price,
            "Unit Size": sec.unitSize,
            "Lot Size": sec.lotSize,
            "Equity change": -sec.priceToRupees(price),
            "Equity": self.equity,
            "Status of sec": sec.getQuickSummary(),
        }

        # Suppress the warning
        warnings.filterwarnings(
            "ignore",
            message="The behavior of DataFrame concatenation with empty or all-NA entries is deprecated.",
        )
        self.tradeHistory.loc[len(self.tradeHistory.index)] = newRow

    def goShort(self, sec, price, time):
        sec.goShort(price, time)
        self.numShortPositions += 1
        self.equity += sec.priceToRupees(price)

        newRow = {
            "Time": time,
            "Action": "Enter",
            "Long / Short": "Short",
            "Security": sec.name,
            "Price": price,
            "Unit Size": sec.unitSize,
            "Lot Size": sec.lotSize,
            "Equity change": sec.priceToRupees(price),
            "Equity": self.equity,
            "Status of sec": sec.getQuickSummary(),
        }

        # Suppress the warning
        warnings.filterwarnings(
            "ignore",
            message="The behavior of DataFrame concatenation with empty or all-NA entries is deprecated.",
        )
        self.tradeHistory.loc[len(self.tradeHistory.index)] = newRow

    def popLong(self, sec, price, time, index):
        profit, sellAmount, entryTime = sec.popLongUnit(price, index)
        self.numLongPositions -= 1
        self.equity += sellAmount
        newRow = {
            "Time": time,
            "Action": "Exit",
            "Long / Short": "Long",
            "Security": sec.name,
            "Price": price,
            "Unit Size": sec.unitSize,
            "Lot Size": sec.lotSize,
            "Equity change": sellAmount,
            "Entered at": entryTime,
            "Profit from trade": profit,
            "Equity": self.equity,
            "Status of sec": sec.getQuickSummary(),
        }
        self.tradeHistory.loc[len(self.tradeHistory)] = newRow

    def popShort(self, sec, price, time, index):
        profit, buyAmount, entryTime = sec.popShortUnit(price, index)
        self.numShortPositions -= 1
        self.equity -= buyAmount
        newRow = {
            "Time": time,
            "Action": "Exit",
            "Long / Short": "Short",
            "Security": sec.name,
            "Price": price,
            "Unit Size": sec.unitSize,
            "Lot Size": sec.lotSize,
            "Equity change": -buyAmount,
            "Entered at": entryTime,
            "Profit from trade": profit,
            "Equity": self.equity,
            "Status of sec": sec.getQuickSummary(),
        }
        self.tradeHistory.loc[len(self.tradeHistory)] = newRow

    def exitAllLong(self, sec, currPrice, time):
        while sec.longPositions:
            self.popLong(sec, currPrice, time, -1)

    def exitAllShort(self, sec, currPrice, time):
        while sec.shortPositions:
            self.popShort(sec, currPrice, time, -1)

    def isLongLoaded(self):
        return self.numLongPositions >= self.maxPositionLimitEachWay

    def isShortLoaded(self):
        return self.numShortPositions >= self.maxPositionLimitEachWay

    def updateATRs(self, currPriceList):
        for sec, currPrice in zip(self.securities, currPriceList):
            sec.updateATR(currPrice)

    def updateUnitSizes(self):
        for sec in self.securities:
            sec.updateUnitSize()

    def updateHistData(self, currPriceList, timeStamp):
        for sec, currPrice in zip(self.securities, currPriceList):
            sec.histData.loc[len(sec.histData)] = [timeStamp, currPrice]

    def checkToAddNewUnit(self, sec, currPrice, time, mode):
        histPriceData = sec.histData["price"]
        if mode == "long":
            breakout = self.longBreakout
            priceCondition = (
                "currPrice > prevHigh" if self.longAtHigh else "currPrice < prevLow"
            )
            entryATR = "longEntryATR"
            tradingFunction = self.goLong
        elif mode == "short":
            breakout = self.shortBreakout
            priceCondition = (
                "currPrice < prevLow" if self.longAtHigh else "currPrice > prevHigh"
            )
            entryATR = "shortEntryATR"
            tradingFunction = self.goShort
        else:
            raise RuntimeError("Invalid mode in tryToAddNewUnit.")

        prevHigh = histPriceData[-breakout:].max()
        prevLow = histPriceData[-breakout:].min()

        if eval(priceCondition):
            sec.updateUnitSize()
            setattr(sec, entryATR, sec.ATR)
            tradingFunction(sec, currPrice, time)
            return True
        return False

    def checkToAddMoreUnits(self, sec, currPrice, time, mode):
        if mode == "long":
            latestUnit = sec.longPositions[-1]
            priceDifference = currPrice - latestUnit.price
            entryATR = sec.longEntryATR
            positions = sec.longPositions
            stopPriceAdjustment = 0.5 * sec.longEntryATR
            tradingFunction = self.goLong
        elif mode == "short":
            latestUnit = sec.shortPositions[-1]
            priceDifference = latestUnit.price - currPrice
            entryATR = sec.shortEntryATR
            positions = sec.shortPositions
            stopPriceAdjustment = -0.5 * sec.shortEntryATR
            tradingFunction = self.goShort
        else:
            raise RuntimeError("Invalid mode in tryToAddMoreUnits.")

        if priceDifference >= self.extraUnitATRFactor * entryATR:
            if self.adjustStopsOnMoreUnits:
                for unit in positions:
                    unit.stopPrice += 0.5 + stopPriceAdjustment
            tradingFunction(sec, currPrice, time)
            return True

        return False

    def addUnits(self, currPriceList, time, position_type):
        unitsAdded = 0
        Position_type = position_type.capitalize()
        if not getattr(self, f"is{Position_type}Loaded")():
            for secNo, sec in enumerate(self.securities):
                if not sec.isLoaded():
                    currPrice = currPriceList[secNo]
                    if not getattr(sec, f"is{Position_type}Entered")():
                        unitsAdded += self.checkToAddNewUnit(
                            sec, currPrice, time, position_type
                        )
                    else:
                        if self.addExtraUnits == "As new unit":
                            unitsAdded += self.checkToAddNewUnit(
                                sec, currPrice, time, position_type
                            )
                        elif self.addExtraUnits == "Using ATR":
                            unitsAdded += self.checkToAddMoreUnits(
                                sec, currPrice, time, position_type
                            )
                        elif self.addExtraUnits == "No":
                            pass
                        else:
                            raise RuntimeError(
                                "Invalid type for Portfolio attribute addExtraUnits"
                            )
        return unitsAdded

    def checkEntries(self, currPriceList, time):
        unitsAdded = 0
        unitsAdded += self.addUnits(currPriceList, time, "long")
        unitsAdded += self.addUnits(currPriceList, time, "short")
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
            for unitNo, unit in enumerate(positions):
                currPrice = currPriceList[secNo]
                if eval(stopCondition):
                    popFunction(sec, currPrice, time, unitNo)
                    self.tradeHistory.loc[self.tradeHistory.index[-1], "Action"] = (
                        "Stop out"
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

    def checkExits(self, currPriceList, time):

        numExits = 0

        if self.exitType == "Timed":
            for sec, currPrice in zip(self.securities, currPriceList):
                # can only check the first position each time because positions are stored
                # in ascending order w.r.t. time
                while sec.longPositions and (
                    time - sec.longPositions[0].time
                    >= self.exit_long_breakout_timedelta
                ):
                    self.popLong(sec, currPrice, time, 0)
                    numExits += 1
                while sec.shortPositions and (
                    time - sec.shortPositions[0].time
                    >= self.exit_short_breakout_timedelta
                ):
                    self.popShort(sec, currPrice, time, 0)
                    numExits += 1
        elif self.exitType == "Breakout":
            for sec, currPrice in zip(self.securities, currPriceList):
                histPriceData = sec.histData["price"]
                if sec.isLongEntered():
                    prevLow = histPriceData[-self.exitLongBreakout :].min()
                    if currPrice < prevLow:
                        numExits = sec.getNumTotalPositions()
                        self.exitAllLong(sec, currPrice, time)
                if sec.isShortEntered():
                    prevHigh = histPriceData[-self.exitLongBreakout :].max()
                    if currPrice > prevHigh:
                        numExits = sec.getNumTotalPositions()
                        self.exitAllShort(sec, currPrice, time)
        else:
            raise RuntimeError(
                "Portfolio attribute exitType is neither Timed nor Breakout."
            )

        return numExits

    def run_simulation(self, priceData, progress_callback=None):
        Pf = self

        price_column_numbers = [
            priceData.columns.get_loc(col)
            for col in priceData.columns
            if col.startswith("price_")
        ]

        total_rows = len(priceData.index)
        for rowNo in range(total_rows):
            row = priceData.iloc[rowNo]
            time = row["time"]
            prices = [row.iloc[colNo] for colNo in price_column_numbers]
            Pf.updateATRs(prices)
            Pf.updateUnitSizes()
            Pf.checkStops(prices, time)
            Pf.checkExits(prices, time)
            Pf.checkEntries(prices, time)
            Pf.updateHistData(prices, time)

            # Update progress bar
            if progress_callback:
                progress_percentage = (rowNo + 1) / total_rows
                progress_callback(progress_percentage)


def prepareDataFramesFromExcel(excel_file, *sheet_names):
    # Determine which sheets to read based on the provided sheet names
    if sheet_names:  # If specific sheet names are provided
        all_sheets = pd.read_excel(excel_file, sheet_name=list(sheet_names), header=1)
    else:  # If no sheet names are provided, read all sheets
        all_sheets = pd.read_excel(excel_file, sheet_name=None, header=1)

    # List to store DataFrames
    dataframes = []

    # Process each sheet
    for df in all_sheets.values():
        # Drop the 'strategyName' column
        df.drop("strategyName", axis=1, inplace=True)

        # Rename columns
        df.rename(columns={"tradeTime": "time", "netAmount": "price"}, inplace=True)

        # Convert 'time' to datetime
        df["time"] = pd.to_datetime(df["time"], format="%d/%m/%Y, %I:%M:%S %p")

        df["price"] = abs(df["price"])

        # Store the processed DataFrame in the list
        dataframes.append(df)

    return dataframes


def preparePortfolioFromDataFrames(Pf, dataframes):

    # Function to merge DataFrames on 'time'
    def merge_dfs_on_time(df_list):
        # Use functools.reduce to perform cumulative inner merge
        from functools import reduce

        merged_df = reduce(
            lambda left, right: pd.merge(left, right, on="time", how="inner"), df_list
        )
        merged_df.reset_index(drop=True, inplace=True)
        return merged_df

    # Preparing each DataFrame by renaming the 'price' column to a unique name
    for i, df in enumerate(dataframes):
        df.rename(columns={"price": f"price_{i + 1}"}, inplace=True)

    # Merge all DataFrames
    df = merge_dfs_on_time(dataframes)

    # Retain only the longest continuous sequence of data points
    df = retain_largest_continuous_sequence(df)
    df.reset_index(inplace=True, drop=True)

    # Get a list of all columns that start with 'price_'
    price_columns = [col for col in df.columns if col.startswith("price_")]

    for i, col in enumerate(price_columns):
        initialData = df.loc[: Pf.minLengthOfInitialData, ["time", col]].copy()
        initialData.rename(columns={col: "price"}, inplace=True)
        Pf.addSecurity(initialData=initialData, name=f"sec_{i}", lotSize=15)

    df = df.loc[Pf.minLengthOfInitialData :].copy()
    df.reset_index(inplace=True, drop=True)

    return df


def retain_largest_continuous_sequence(df, time_column="time"):
    df[time_column] = pd.to_datetime(
        df[time_column]
    )  # Convert to datetime if not already
    df["time_diff"] = (
        df[time_column].diff().dt.total_seconds().abs()
    )  # Calculate time differences in seconds

    # Group by breaks in the 1-second sequence
    df["group"] = (df["time_diff"] != 1).cumsum()

    # Identify the largest group with 1-second intervals
    group_sizes = df.groupby("group").size()
    largest_group = group_sizes.idxmax()

    # Filter the DataFrame to only include the largest continuous 1-second spaced group
    df_filtered = df[(df["group"] == largest_group) & (df["time_diff"] == 1)].copy()

    # Optionally, drop the helper columns
    df_filtered.drop(["time_diff", "group"], axis=1, inplace=True)

    return df_filtered
