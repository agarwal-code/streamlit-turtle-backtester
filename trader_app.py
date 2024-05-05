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
        Please upload an Excel file consisting of second-by-second price data for analysis. Ensure that the file format is correct.
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
        with open("sample_data.xlsx", "rb") as file:
            st.download_button(
                label="Download sample file",
                data=file,
                file_name="sample_data.xlsx",
                mime="application/octet-stream",
                help="Download the sample Excel file to check, for example, the required format of the time column.",
            )

        if st.button("Use sample data to proceed instead of uploading your own data"):
            st.session_state.file = "sample_data.xlsx"
            st.session_state.use_sample_file = True
            st.rerun()

    if st.session_state.get("file", False):
        xls = pd.ExcelFile(st.session_state.file)
        sheet_names = xls.sheet_names
        st.subheader("Select which sheets to process.")
        st.caption(
            "Note: it is assumed that each sheet corresponds to a different strategy, please ensure this is the case."
        )
        all_sheets = st.checkbox(
            "Select All Sheets", value=st.session_state.get("all_sheets_value", False)
        )
        selected_sheets = {
            sheet: st.checkbox(sheet, value=all_sheets) for sheet in sheet_names
        }

        if st.button("Process data"):
            # Determine selected sheets or all sheets
            sheets_to_process = [
                sheet for sheet, checked in selected_sheets.items() if checked
            ] or None
            if all_sheets or not sheets_to_process:
                # Process all sheets if "Select All" or no specific selection
                sheets_to_process = sheet_names

            # Attempt to process the selected sheets
            try:
                dataframesDict = Trader.prepareDataFramesFromExcel(
                    st.session_state.file, sheets_to_process
                )
                if dataframesDict:
                    st.session_state.dataframesDict = dataframesDict
                    st.session_state.data_processed = True
                else:
                    # This condition could mean empty dataframes were returned
                    st.error("No data processed. Check your file and selections.")
            except Exception as e:
                # Log the error message or handle it as needed
                st.error(f"Failed to process data due to an error: {e}")
                # Optionally, reset state if needed
                # If you want to clear dataframes in case of error
                st.session_state.dataframes = []

    if st.session_state.get("data_processed", False):
        st.success(
            f"Processed {len(st.session_state.dataframesDict)} sheets successfully! Ready for further action."
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

    st.header("Select trading parameters for portfolio.")

    lotSize = st.number_input(
        "Enter the lot size for securities being traded",
        min_value=1,
        max_value=500,
        value=15,
    )

    transCostPerCrore = st.number_input(
        "Enter the transaction cost (in rupees) per crore of value traded",
        min_value=1.0,
        max_value=10000000.0,
        value=10000.0,
    )
    transCost = transCostPerCrore / 10000000.0

    slippagePerContract = st.number_input(
        "Enter the estimated slippage (in rupees) per contract",
        min_value=0.0,
        max_value=100.0,
        value=0.5,
    )

    longAtHigh = st.radio(
        "Trend following or Countertrend?",
        ("Trend (Long at High)", "Countertrend (Long at Low)"),
        index=1,
    )
    if longAtHigh == "Trend (Long at High)":
        longAtHigh = True
    elif longAtHigh == "Countertrend (Long at Low)":
        longAtHigh = False

    longBreakout = st.number_input(
        "Enter the number of seconds for long breakout",
        min_value=1,
        max_value=10000000,
        value=20,
    )

    shortBreakout = st.number_input(
        "Enter the number of seconds for short breakout",
        min_value=1,
        max_value=10000000,
        value=20,
    )

    ATRAverageRange = st.number_input(
        "Enter the ATR average range", min_value=10, max_value=30, value=20
    )

    with st.expander("Compute E-ratios", expanded=False):
        st.text(
            "Select the range of time periods over which you would like to compute E-ratios"
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

    addExtraUnits = st.checkbox(
        "Add additional units for a security when a position is already entered",
        value=False,
    )
    if addExtraUnits:
        with st.expander("Additional unit settings", expanded=True):
            unit_options = {
                "Same rules as those for new units (breakout)": "As new unit",
                "Using 1/2 ATR based stops": "Using ATR",
            }
            addExtraUnits = st.radio(
                "What rules would you like to use to add these additional units?",
                list(unit_options.keys()),
            )
            addExtraUnits = unit_options[addExtraUnits]
    else:
        addExtraUnits = "No"

    useStops = st.checkbox("Use stop losses", value=False)
    if useStops:
        with st.expander("Stop Loss Settings", expanded=True):
            stopLossFactor = st.number_input(
                "Enter the stop loss factor",
                value=2.0,
                help="e.g. if this is 2, then the stop will be set at 2*ATR from the entry price",
            )
            adjustStopsOnMoreUnits = st.checkbox(
                "Adjust stops when more units are added",
                value=True,
                help="To minimize risk, will for example increase stops for previous long positions if more long positions are entered",
            )

    exitType = st.radio("Select type of exits to use", ("Timed", "Breakout"))
    if exitType == "Timed":
        exitBreakoutMessage = (
            "Enter the number of seconds for exiting {} positions"
            + "(e.g. if 30, positions will be exited 30 seconds after entry)"
        )
    else:
        exitBreakoutMessage = (
            "Enter length of exit breakout for {0} positions"
            + " (e.g. if 20, then {0} positions will be exited at a 20-second low)"
        )
    exitLongBreakout = st.number_input(
        exitBreakoutMessage.format("long"),
        min_value=1,
        max_value=10000000,
        value=5,
    )
    exitShortBreakout = st.number_input(
        exitBreakoutMessage.format("short"),
        min_value=1,
        max_value=10000000,
        value=5,
    )

    notionalAccountSize = st.number_input(
        "Enter the notional account size", value=1000000.0
    )

    riskPercentOfAccount = st.number_input(
        "Enter the risk percent of account",
        value=1.0,
        help="Amount of risk (in percentage points of account size) willing to tolerate per trade per second; i.e., unit sizes are computed such that 1 ATR movement of price represents (riskPercentOfAccount * accountSize) equity movement.",
    )

    maxPositionLimitEachWay = st.number_input(
        "Enter the maximum long/short position limit",
        min_value=1,
        max_value=500,
        value=12,
        help="e.g. If 12, then maximum 12 long positions are allowed in the portfolio, and maximum 12 short positions, for a total of 24.",
    )

    maxUnits = st.number_input(
        "Enter the maximum number of units of an individual security in the portfolio",
        min_value=1,
        max_value=500,
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
            longAtHigh=longAtHigh,
            longBreakout=longBreakout,
            shortBreakout=shortBreakout,
            ATRAverageRange=ATRAverageRange,
            addExtraUnits=addExtraUnits,
            extraUnitATRFactor=(0.5 if addExtraUnits == "Using ATR" else 0),
            useStops=useStops,
            stopLossFactor=stopLossFactor if useStops else 2,
            adjustStopsOnMoreUnits=adjustStopsOnMoreUnits if useStops else None,
            exitType=exitType,
            exitLongBreakout=exitLongBreakout,
            exitShortBreakout=exitShortBreakout,
            notionalAccountSize=notionalAccountSize,
            riskPercentOfAccount=riskPercentOfAccount,
            maxPositionLimitEachWay=maxPositionLimitEachWay,
            maxUnits=maxUnits,
        )

        Pf.preparePortfolioFromDataFrames(st.session_state.dataframesDict)

        try:
            progress_bar = st.progress(0)
            Pf.run_simulation(
                progress_callback=lambda x: progress_bar.progress(x * 0.9)
            )
            st.session_state.Pf = Pf
            st.session_state.tradeBook_excel = Trader.dataframe_to_excel(Pf.tradeBook)
            st.session_state.tradeBook_csv = Trader.dataframe_to_csv(Pf.tradeBook)
            progress_bar.progress(1.0)
            st.session_state.run_complete = True
        # except Exception as e:
        #     # Log the error message or handle it as needed
        #     print(f"Failed to process data due to an error: {e}")
        finally:
            sim_message_placeholder.empty()
            # progress_bar.empty()  # Optionally clear the progress bar after completion

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
            success_message += f"Total {key} is {value:,}.  \n"  # Two spaces before \n
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


if __name__ == "__main__":
    main()
