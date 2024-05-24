import streamlit as st
import pandas as pd
import Trader
import plotly.express as px


def main():
    # st.set_page_config(layout="wide")  # Use a wider layout
    st.title("Trade simulator")

    if not st.session_state.get("use_sample_file", False):
        st.markdown(
            """
        ## Upload your Excel file
        Please upload an Excel file consisting of price data for analysis. Ensure that the time stamps are in ascending order, and that the format and time periods under consideration are consistent across sheets.
        """,
            unsafe_allow_html=True,
        )
        st.session_state.file = st.file_uploader(
            "Upload Excel file", type=["xlsx"], label_visibility="collapsed"
        )
        if st.session_state.file:
            st.session_state.use_uploaded_file = True

    # Download sample file button
    if not st.session_state.get("use_uploaded_file"):
        with open("Sample options data.xlsx", "rb") as file:
            st.download_button(
                label="Download sample options spread data file",
                data=file,
                file_name="Sample options data.xlsx",
                mime="application/octet-stream",
                help="Download the sample Excel file to check, for example, the required format of the time column.",
            )

        if st.button("Use sample options spread data to proceed"):
            st.session_state.file = "Sample options data.xlsx"
            st.session_state.use_sample_file = True
            st.rerun()

        with open("Sample stocks data (5 years).xlsx", "rb") as file:
            st.download_button(
                label="Download sample stocks data file",
                data=file,
                file_name="Sample stocks data (5 years).xlsx",
                mime="application/octet-stream",
                help="Download the sample Excel file to check, for example, the required format of the time column.",
            )

        if st.button("Use sample stocks data to proceed"):
            st.session_state.file = "Sample stocks data (5 years).xlsx"
            st.session_state.use_sample_file = True
            st.rerun()

    if st.session_state.get("file", False):
        xls = pd.ExcelFile(st.session_state.file)
        sheet_names = xls.sheet_names
        st.subheader("Select which sheets to process.")
        st.caption(
            "Note: it is assumed that each sheet corresponds to a different security, please ensure this is the case."
        )
        all_sheets = st.checkbox(
            "Select All Sheets", value=st.session_state.get("all_sheets_value", False)
        )
        selected_sheets = {
            sheet: st.checkbox(sheet, value=all_sheets)
            for sheet in sheet_names
            if "lot" not in sheet.lower()
        }
        lots_element = next(
            (sheet for sheet in sheet_names if "lot" in sheet.lower()),
            None,
        )
        if lots_element:
            sheet_names.remove(lots_element)
            lot_df = pd.read_excel(
                st.session_state.file, sheet_name=lots_element, header=0
            )
            symbol_column = find_column(lot_df, ["symbol", "security", "name"])
            lot_size_column = find_column(lot_df, ["lot"])
            if symbol_column and lot_size_column:
                # Create a dictionary with symbols as keys and lot sizes as values
                st.session_state.lotSizeDict = dict(
                    zip(lot_df[symbol_column], lot_df[lot_size_column])
                )
                st.session_state.lots_provided_in_excel_file = True
            else:
                st.error("Could not find the required columns in the uploaded file.")
                st.stop()
        else:
            st.session_state.lots_provided_in_excel_file = False

        if st.button("Process data"):
            # Determine selected sheets or all sheets
            sheets_to_process = [
                sheet for sheet, checked in selected_sheets.items() if checked
            ] or None
            if all_sheets or not sheets_to_process:
                # Process all sheets if "Select All" or no specific selection
                sheets_to_process = sheet_names

            dataframesDict = Trader.prepareDataFramesFromExcel(
                st.session_state.file, sheets_to_process
            )
            if dataframesDict:
                st.session_state.dataframesDict = dataframesDict
                st.session_state.data_processed = True
            else:
                # This condition could mean empty dataframes were returned
                st.error("No data processed. Check your file and selections.")
                st.stop()

    if st.session_state.get("data_processed", False):
        st.success(
            f"Processed {len(st.session_state.dataframesDict)} sheet(s) {'and lot sizes' if st.session_state.lots_provided_in_excel_file else ''} successfully! Ready for further action."
        )

        with st.expander("See graphs", expanded=False):
            for sec, df in st.session_state.dataframesDict.items():
                fig = px.line(
                    df,
                    x="time",
                    y="price",
                    labels={"time": "Time", "price": "Price"},
                    title=f"{sec}",
                    markers=True,  # This adds the dots on each line point
                )
                # Customizing hover data
                fig.update_traces(
                    # mode=
                    # "markers+lines",  # Ensure both markers and lines are shown
                    hoverinfo="all",  # This ensures all relevant data shows on hover
                )
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.stop()

    st.header("Select trading parameters for portfolio.")

    lotSize = 15
    provide_lots_manually = st.checkbox(
        "Provide lot sizes manually",
        value=(not st.session_state.lots_provided_in_excel_file),
    )
    if provide_lots_manually:
        lot_options = {
            "Uniform lot size across securities": True,
            "Different lot sizes for different securities": False,
        }
        uniform_lot = st.radio(
            "Options for lot sizes", list(lot_options.keys()), index=0
        )
        uniform_lot = lot_options[uniform_lot]
        if uniform_lot:
            lotSize = st.number_input(
                "Enter the lot size for securities being traded",
                min_value=1,
                value=15,
            )
            st.session_state.lotSizeDict = None
        else:
            st.session_state.lotSizeDict = {}
            for secName in st.session_state.dataframesDict.keys():
                st.session_state.lotSizeDict[secName] = st.number_input(
                    f"Enter lot size for {secName}",
                    min_value=1,
                    value=250,
                )

    transCostPerCrore = st.number_input(
        "Enter the transaction cost (in rupees) per crore of value traded",
        min_value=1.0,
        value=10000.0,
    )
    transCost = transCostPerCrore / 10000000.0

    slippagePerContract = st.number_input(
        "Enter the estimated slippage (in rupees) per contract",
        min_value=0.0,
        max_value=100.0,
        value=0.5,
    )

    entryType = st.radio(
        "Entry strategy",
        (
            "Breakout",
            "Breakout + MACD-Signal Condition",
            "Breakout + MACD-Signal Condition + Signal Polarity Condition",
            "Breakout + Signal Polarity Condition",
            "MACD-Signal Crossover",
            "MACD-Signal Crossover + Signal Polarity Condition",
            "MACD Zero Crossover (= EMA Crossover)",
        ),
        index=5,
        help="1. Breakout: enters when highs or lows over a given time frame are exceeded.\n"
        "2. MACD-Signal Condition: further require that MACD > / < Signal for entering long / short.\n"
        "3. Signal Polarity Condition: further require Signal > 0 for entering short and < 0 for entering long.\n"
        "4. MACD-Signal Crossover: enter when MACD crosses the Signal line.\n"
        "5. MACD Zero Crossover: enter when MACD crosses zero line, equivalent to EMA crossover.",
    )

    longAtHigh = True
    longBreakout = 20
    shortBreakout = 20
    if "Breakout" in entryType:
        longAtHigh = st.radio(
            "Action at breakouts",
            ("Long at highs and short at lows", "Short at highs and go long at lows"),
            index=0,
        )
        if "Long at highs" in longAtHigh:
            longAtHigh = True
        elif "Short at highs" in longAtHigh:
            longAtHigh = False

        longBreakout = st.number_input(
            "Enter the number of ticks for long breakout",
            min_value=1,
            value=20,
        )

        shortBreakout = st.number_input(
            "Enter the number of ticks for short breakout",
            min_value=1,
            value=20,
        )

        with st.expander("Compute E-ratios for these breakouts", expanded=False):
            st.text(
                "Select the range of time periods (in ticks) over which you would like to compute E-ratios"
            )
            timePeriodRangeStart = st.number_input(
                "Minimum time period",
                min_value=1,
                max_value=10000000,
                value=1,
            )
            timePeriodRangeEnd = st.number_input(
                "Maximum time period",
                min_value=1,
                max_value=10000000,
                value=50,
            )
            timePeriodStep = st.number_input(
                "Increment in time periods",
                min_value=1,
                max_value=10000000,
                value=1,
            )
            compute_edges_button = st.button(
                "Compute entry edge ratios",
                help="Compute E-ratios for the chosen entry parameters, ATR averaging range, and time periods",
            )
            if compute_edges_button and st.session_state.get("data_processed", False):
                st.session_state.E_ratios = Trader.computeEdgeRatios(
                    st.session_state.dataframesDict,
                    timePeriodRangeStart=timePeriodRangeStart,
                    timePeriodRangeEnd=timePeriodRangeEnd,
                    timePeriodStep=timePeriodStep,
                    longBreakout=longBreakout,
                    shortBreakout=shortBreakout,
                    longAtHigh=longAtHigh,
                    ATRAverageRange=ATRAverageRange,
                    getPlots=True,
                )
                st.session_state.E_ratios_computed = True

            if st.session_state.get("E_ratios_computed"):
                for sec, df_fig in st.session_state.E_ratios.items():
                    df, fig = df_fig
                    st.plotly_chart(fig, use_container_width=True)
                    st.dataframe(df)

    EMA_length_larger = 26
    EMA_length_smaller = 12
    smoothing = 2
    signal_EMA_length = 9
    if "MACD" in entryType or "Signal" in entryType:
        st.markdown(
            """
        <u>Formulae used</u>

        For Exponential Moving Average (EMA):
        """,
            unsafe_allow_html=True,
        )
        st.latex(
            r"""
            \begin{align*}
            EMA_{\text{Current}} &=  
            \text{Value}_{\text{Current Tick}} \cdot \left( \dfrac{ \text{Smoothing} }{ 1 + \text{Length} }\right)\\
            & \hspace{.2in} + EMA_{\text{Previous Tick}} \cdot \left(1 - \left( \dfrac{ \text{Smoothing} }{ 1 + \text{Length} }\right) \right)\\
            \end{align*}
            """
        )
        st.markdown(
            """ 
        Smoothing factor = 2 by default, the larger this is the more the latest observation is weighted

        MACD = (Shorter EMA) - (Longer EMA), default is 12-EMA - 26-EMA.

        Signal = EMA of MACD, default is 9-EMA of MACD.
        """
        )
        EMA_length_smaller = st.number_input(
            "Enter the length for the shorter EMA",
            min_value=1,
            value=12,
        )
        EMA_length_larger = st.number_input(
            "Enter the length for the longer EMA",
            min_value=1,
            value=26,
        )
        if EMA_length_larger <= EMA_length_smaller:
            st.error(
                "The length for the longer EMA must be greater than the length for the shorter EMA. Please adjust the values."
            )
            st.stop()  # Stop execution here if the condition is not met
        smoothing = st.number_input(
            "Enter the smoothing factor",
            min_value=0,
            value=2,
        )
        signal_EMA_length = st.number_input(
            "Enter the length of the EMA used to compute Signal from MACD",
            min_value=1,
            value=9,
        )

    ATRAverageRange = st.number_input(
        "Enter the ATR average range (number in the denominator in the ATR calculation)",
        min_value=2,
        value=20,
    )

    extraUnitATRFactor = 10000
    addExtraUnits = st.checkbox(
        "Add additional units for a security when a position is already entered",
        value=True,
    )
    if addExtraUnits:
        with st.expander("Additional unit settings", expanded=True):
            unit_options = {
                "Using ATR based breakouts": "Using ATR",
                "Same rules as those for new units": "As new unit",
            }
            addExtraUnits = st.radio(
                "What rules would you like to use to add these additional units?",
                list(unit_options.keys()),
            )
            addExtraUnits = unit_options[addExtraUnits]
            if addExtraUnits == "Using ATR":
                extraUnitATRFactor = st.number_input(
                    "Enter the factor by which ATR is multiplied to set extra unit breakouts",
                    value=0.5,
                    help="If this is 0.5, then an additional long unit is entered when price is 0.5 * (entry ATR) higher than the original entry price",
                )
    else:
        addExtraUnits = "No"

    stopLossFactor = 2
    adjustStopATRFactor = 0
    useStops = st.checkbox("Use stop losses", value=True)
    if useStops:
        with st.expander("Stop Loss Settings", expanded=True):
            stopLossFactor = st.number_input(
                "Enter the stop loss factor",
                value=2.0,
                help="If this is 2, then the stop will be set at 2*ATR from the entry price",
            )
            adjustStopsOnMoreUnits = st.checkbox(
                "Adjust stops when more units are added",
                value=True,
                help="To minimize risk, will for example increase stops for previous long positions if more long positions are entered",
            )
            if adjustStopsOnMoreUnits:
                adjustStopATRFactor = st.number_input(
                    "Enter the factor by which ATR is multiplied to adjust previous stops",
                    value=0.5,
                    help="If this is 0.5, then previous stop price for an entered short unit will be decreased by 0.5*(Entry ATR) for every additional short unit entered",
                )

    exitType = st.radio("Select type of exits to use", ("Breakout", "Timed"))
    if exitType == "Timed":
        exitBreakoutMessage = (
            "Enter the number of ticks for exiting {} positions"
            + " (e.g. if 30, positions will be exited 30 ticks after entry)"
        )
    else:
        exitBreakoutMessage = (
            "Enter length of exit breakout for {0} positions"
            + " (e.g. if 20, then {0} positions will be exited at a 20-tick low)"
        )
    exitLongBreakout = st.number_input(
        exitBreakoutMessage.format("long"),
        min_value=1,
        value=10,
    )
    exitShortBreakout = st.number_input(
        exitBreakoutMessage.format("short"),
        min_value=1,
        value=10,
    )

    notionalAccountSize = st.number_input(
        "Enter the notional account size", value=1000000.0
    )
    adjustNotionalAccountSize = st.checkbox(
        "Readjust notional account size using total net profits after every trade",
        value=True,
    )

    riskPercentOfAccount = st.number_input(
        "Enter the risk percent of account",
        value=1.0,
        help="Amount of risk (in percentage points of account size) willing to tolerate per trade per tick; i.e., unit sizes are computed such that 1 ATR movement of price represents (riskPercentOfAccount * accountSize) equity movement.",
    )

    maxPositionLimitEachWay = st.number_input(
        "Enter the maximum long/short position limit",
        min_value=1,
        value=12,
        help="e.g. If 12, then maximum 12 long positions are allowed in the portfolio, and maximum 12 short positions, for a total of 24.",
    )

    maxUnits = st.number_input(
        "Enter the maximum number of units of an individual security in the portfolio",
        min_value=1,
        value=4,
        help="e.g. If 4, then maximum 4 positions can be held in a particular security.",
    )

    simulate_button = st.button(
        "Simulate Trades", disabled=st.session_state.get("simulating", False)
    )

    if not st.session_state.get("data_processed", False) and simulate_button:
        st.error("Please process data above before simulation.")

    if (
        simulate_button or st.session_state.get("simulating", False)
    ) and st.session_state.get("data_processed", False):
        # Immediately set 'simulating' to True to disable the button
        if not st.session_state.get("simulating", False):
            st.session_state["simulating"] = True
            st.rerun()

        sim_message_placeholder = st.empty()
        sim_message_placeholder.text("Simulating...")

        Pf = Trader.Portfolio(
            securities=None,
            lotSize=lotSize,
            transCost=transCost,
            slippagePerContract=slippagePerContract,
            entryType=entryType,
            longAtHigh=longAtHigh,
            longBreakout=longBreakout,
            shortBreakout=shortBreakout,
            EMA_length_larger=EMA_length_larger,
            EMA_length_smaller=EMA_length_smaller,
            smoothing=smoothing,
            signal_EMA_length=signal_EMA_length,
            ATRAverageRange=ATRAverageRange,
            addExtraUnits=addExtraUnits,
            extraUnitATRFactor=extraUnitATRFactor,
            useStops=useStops,
            stopLossFactor=stopLossFactor,
            adjustStopsOnMoreUnits=adjustStopsOnMoreUnits if useStops else None,
            adjustStopATRFactor=adjustStopATRFactor,
            exitType=exitType,
            exitLongBreakout=exitLongBreakout,
            exitShortBreakout=exitShortBreakout,
            notionalAccountSize=notionalAccountSize,
            adjustNotionalAccountSize=adjustNotionalAccountSize,
            riskPercentOfAccount=riskPercentOfAccount,
            maxPositionLimitEachWay=maxPositionLimitEachWay,
            maxUnits=maxUnits,
        )
        # print(vars(Pf))
        # print(st.session_state.get("lotSizeDict", None))
        Pf.preparePortfolioFromDataFrames(
            dataframesDict=st.session_state.dataframesDict,
            lotSizeDict=st.session_state.get("lotSizeDict", None),
        )

        progress_bar = st.progress(0)
        Pf.run_simulation(progress_callback=lambda x: progress_bar.progress(x * 0.9))
        st.session_state.Pf = Pf
        st.session_state.tradeBook_excel = Pf.getTradeBook(
            format="excel", parameter_sheet=True
        )
        st.session_state.tradeBook_csv = Pf.getTradeBook(format="csv")
        progress_bar.progress(1.0)
        st.session_state.run_complete = True
        sim_message_placeholder.empty()
        progress_bar.empty()

        # this ensures the Simulate Trades button is renenabled immediately
        st.session_state["simulating"] = False
        st.rerun()

    if st.session_state.get("run_complete", False) and not st.session_state.get(
        "simulating", False
    ):
        success_message = (
            "Trade simulation completed.  \n"  # Note the two spaces before \n
        )
        for key, value in st.session_state.Pf.getStats().items():
            success_message += f"{key} is {value:,.2f}.  \n"  # Two spaces before \n
        st.markdown(success_message)

        st.download_button(
            label="Download trade book as Excel file",
            data=st.session_state.tradeBook_excel,
            file_name="tradeBook.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.download_button(
            label="Download trade book as CSV file",
            # Get the string value of the StringIO object
            data=st.session_state.tradeBook_csv.getvalue(),
            file_name="data.csv",
            mime="text/csv",
        )
        # st.text("Select performance metrics to see:")
        # metrics = [
        #     "Equity graph",
        #     "CAGR%",
        #     "Maximum drawdown",
        #     "Sharpe Ratio",
        #     "Robust Sharpe Ratio",
        #     "MAR",
        #     "More coming soon...",
        # ]
        # selected_metrics = {
        #     metric: st.checkbox(metric, value=False) for metric in metrics
        # }
        # see_metrics = st.button("Compute performance metrics")
        # if see_metrics:
        #     st.text("Sorry this part of the simulator is not ready yet. Coming soon!")


def find_column(df, keywords):
    for keyword in keywords:
        for column in df.columns:
            if keyword.lower() in column.lower():
                return column
    return None


if __name__ == "__main__":
    main()
