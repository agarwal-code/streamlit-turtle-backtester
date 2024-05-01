import streamlit as st
import pandas as pd
import Trader


def main():
    st.title("Trade simulator")

    uploaded_file = st.file_uploader("Upload your Excel file", type=["xlsx"])

    if uploaded_file:
        xls = pd.ExcelFile(uploaded_file)
        sheet_names = xls.sheet_names

        all_sheets = st.checkbox("Select All Sheets")
        selected_sheets = {
            sheet: st.checkbox(sheet, value=all_sheets) for sheet in sheet_names
        }

        if st.button("Process data"):
            # Determine selected sheets or all sheets
            sheets_to_process = [
                sheet for sheet, checked in selected_sheets.items() if checked

            ] or None
            if all_sheets or not sheets_to_process:
                sheets_to_process = sheet_names  # Process all sheets if "Select All" or no specific selection

            # Attempt to process the selected sheets
            try:
                dataframes = Trader.prepareDataFramesFromExcel(
                    uploaded_file, *sheets_to_process
                )
                if dataframes:
                    st.session_state.dataframes = dataframes
                    st.session_state.data_processed = True
                    st.success(
                        f"Processed {len(st.session_state.dataframes)} sheets successfully! Ready for further action."
                    )
                else:
                    # This condition could mean empty dataframes were returned
                    st.error("No data processed. Check your file and selections.")
            except Exception as e:
                # Log the error message or handle it as needed
                st.error(f"Failed to process data due to an error: {e}")
                # Optionally, reset state if needed
                # If you want to clear dataframes in case of error
                st.session_state.dataframes = []

    st.write("Select trading parameters for portfolio.")

    longBreakout = st.number_input(
        "Enter the number of days for long breakout",
        min_value=1,
        max_value=50,
        value=20,
    )

    shortBreakout = st.number_input(
        "Enter the number of days for short breakout",
        min_value=1,
        max_value=50,
        value=20,
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

    useStops = st.checkbox("Use stop losses", value=False)
    if useStops:
        with st.expander("Stop Loss Settings", expanded=True):
            stopLossFactor = st.number_input("Enter the stop loss factor", value=2.0)
            adjustStopsOnMoreUnits = st.checkbox(
                "Adjust stops when more units are added", value=True
            )

    addExtraUnits = st.checkbox(
        "Add additional units for a security when a position is already entered",
        value=False,
    )
    if addExtraUnits:
        with st.expander("Additional unit settings", expanded=True):
            addExtraUnits = st.radio(
                "What rules would you like to add these additional units?",
                (
                    "Same rules as those for new units (breakout)",
                    "Using 1/2 ATR based stops",
                ),
            )
            if addExtraUnits == "Same rules as those for new units (breakout)":
                addExtraUnits = "As new unit"
            else:
                addExtraUnits = "Using ATR"
    else:
        addExtraUnits = "No"

    exitType = st.radio("Select type of exits to use", ("Timed", "Breakout"))
    if exitType == "Timed":
        exitBreakoutMessage = (
            "Enter the number of days for exiting {} positions"
            + "(e.g. if 30, positions will be exited 30 days after entry)"
        )
    else:
        exitBreakoutMessage = (
            "Enter length of exit breakout for {0} positions"
            + " (e.g. if 20, then {0} positions will be exited at a 20-day low)"
        )
    exitLongBreakout = st.number_input(
        exitBreakoutMessage.format("long"),
        min_value=1,
        max_value=20,
        value=5,
    )
    exitShortBreakout = st.number_input(
        exitBreakoutMessage.format("short"),
        min_value=1,
        max_value=20,
        value=5,
    )

    notionalAccountSize = st.number_input(
        "Enter the notional account size", value=1000000.0
    )

    riskPercentOfAccount = st.number_input(
        "Enter the risk percent of account", value=1.0
    )

    maxPositionLimitEachWay = st.number_input(
        "Enter the maximum position limit each way",
        min_value=1,
        max_value=24,
        value=12,
    )

    ATRAverageRange = st.number_input(
        "Enter the ATR average range", min_value=10, max_value=30, value=20
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

        message_placeholder = st.empty()
        message_placeholder.text("Simulating...")

        Pf = Trader.Portfolio(
            securities=None,
            longBreakout=longBreakout,
            shortBreakout=shortBreakout,
            longAtHigh=longAtHigh,
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
            ATRAverageRange=ATRAverageRange,
        )
        priceData = Trader.preparePortfolioFromDataFrames(
            Pf, st.session_state.dataframes
        )

        try:
            progress_bar = st.progress(0)
            Pf.run_simulation(priceData, progress_callback=lambda x: progress_bar.progress(x))
            st.session_state.Pf = Pf
            st.session_state.run_complete = True
            st.rerun()
        finally:
            message_placeholder.empty()
            progress_bar.empty()  # Optionally clear the progress bar after completion
            st.session_state["simulating"] = False


    if st.session_state.get("run_complete", False) and not st.session_state.get(
        "simulating", False
    ):
        st.success("Trade simulation completed.")
        st.text(f"Final equity is {st.session_state.Pf.equity}.")
        st.text("Select performance metrics to see:")
        metrics = [
            "Equity graph",
            "CAGR%",
            "Maximum drawdown",
            "Sharpe Ratio",
            "Robust Sharpe Ratio",
            "MAR",
            "More coming soon...",
        ]
        selected_metrics = {
            metric: st.checkbox(metric, value=False) for metric in metrics
        }
        see_metrics = st.button("Compute performance metrics")
        if see_metrics:
            st.text("Sorry this part of the simulator is not ready yet. Coming soon!")


if __name__ == "__main__":
    main()
