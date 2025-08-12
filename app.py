import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime, timedelta
import subprocess
import os
from pathlib import Path
import shutil

# --- 1. CONFIGURATION & CONSTANTS ---
# Use st.secrets for sensitive information
try:
    # For local development, you can have a secrets.toml file
    # For deployment, set these in the Streamlit Cloud dashboard
    GITHUB_REPO = st.secrets["git"]["repo"]  # e.g., "forestryvehicleadmin/Vehicle_Gantt"
    GITHUB_BRANCH = st.secrets["git"]["branch"]  # e.g., "master"
    VEM_PASSCODE = st.secrets["auth"]["passcode"]  # e.g., "1234"
    DEPLOY_KEY = st.secrets["git"]["deploy_key"]
except (KeyError, FileNotFoundError):
    st.error("Required secrets (repo, branch, passcode, deploy_key) are not set. Please configure them.")
    st.stop()

# Use Path objects for cleaner file paths
# This logic makes the app work both locally (by cloning into 'repo')
# and when deployed on Streamlit Cloud (where files are in the root).
REPO_DIR = Path("repo")
if REPO_DIR.is_dir():
    # We are in an environment where the repo was cloned into a subdirectory.
    base_path = REPO_DIR
else:
    # We are likely in a Streamlit Cloud environment where files are at the root.
    base_path = Path(".")  # Use the current directory

EXCEL_FILE_PATH = base_path / "Vehicle_Checkout_List.xlsx"
TYPE_LIST_PATH = base_path / "type_list.txt"
ASSIGNED_TO_LIST_PATH = base_path / "assigned_to_list.txt"
DRIVERS_LIST_PATH = base_path / "authorized_drivers_list.txt"

# Define the SSH URL for git operations
GIT_SSH_URL = f"git@github.com:{GITHUB_REPO}.git"


# --- 2. GIT & SSH SETUP ---
# This section is cleaner and more robust.
def setup_ssh_and_git():
    """Configures SSH with the deploy key and sets up the Git remote."""
    ssh_dir = Path("~/.ssh").expanduser()
    ssh_dir.mkdir(exist_ok=True)

    deploy_key_path = ssh_dir / "github_deploy_key"
    config_path = ssh_dir / "config"

    # Write the deploy key and set permissions
    deploy_key_path.write_text(DEPLOY_KEY)
    os.chmod(deploy_key_path, 0o600)

    # Write the SSH config and set permissions
    config_text = f"""
Host github.com
    HostName github.com
    User git
    IdentityFile {deploy_key_path}
    StrictHostKeyChecking no
"""
    config_path.write_text(config_text)
    os.chmod(config_path, 0o600)

    # Set Git user details
    subprocess.run(["git", "config", "--global", "user.name", "forestryvehicleadmin"], check=True)
    subprocess.run(["git", "config", "--global", "user.email", "forestryvehicleadmin@nau.edu"], check=True)


def clone_or_pull_repo():
    """Clones the repo if it doesn't exist, otherwise pulls the latest changes."""
    # This function should only run if the 'repo' directory is the intended mode of operation.
    if not REPO_DIR.is_dir():
        return  # In a deployed environment, we don't clone.

    st.write("Pulling latest changes from repository...")
    try:
        # Fetch and reset to ensure we have the latest version, avoiding merge conflicts
        subprocess.run(["git", "fetch", "origin", GITHUB_BRANCH], cwd=REPO_DIR, check=True, capture_output=True,
                       text=True)
        subprocess.run(["git", "reset", "--hard", f"origin/{GITHUB_BRANCH}"], cwd=REPO_DIR, check=True,
                       capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        st.error(f"Failed to pull changes. Git Error: {e.stderr}")
        st.stop()


def push_changes_to_github(commit_message):
    """Commits all changes and pushes them to the GitHub repository."""
    try:
        # Add all changes
        subprocess.run(["git", "add", "-A"], cwd=base_path, check=True)

        # Check if there's anything to commit
        status_result = subprocess.run(["git", "status", "--porcelain"], cwd=base_path, capture_output=True, text=True)
        if not status_result.stdout:
            st.info("No changes to commit.")
            return

        # Commit and Push
        subprocess.run(["git", "commit", "-m", commit_message], cwd=base_path, check=True)

        # --- FIX: Explicitly push to the SSH URL to avoid auth errors ---
        subprocess.run(["git", "push", GIT_SSH_URL, f"HEAD:{GITHUB_BRANCH}"], cwd=base_path, check=True)

        st.success("Changes successfully pushed to GitHub!")

    except subprocess.CalledProcessError as e:
        st.error(f"Failed to push changes. Git Error: {e.stderr}")
        st.warning("Your changes have been saved locally but not pushed to GitHub. Please try again later.")


# --- 3. DATA LOADING & CACHING ---
def initialize_data_files_if_needed():
    """Checks for the main Excel file and creates it if it doesn't exist."""
    if not EXCEL_FILE_PATH.exists():
        st.warning("Data file not found. Initializing a new one...")

        # Define the schema for the new Excel file
        columns = [
            "Unique ID", "Type", "Vehicle #", "Assigned to", "Status",
            "Checkout Date", "Return Date", "Authorized Drivers", "Notes"
        ]
        df = pd.DataFrame(columns=columns)

        # Ensure date columns have the correct dtype, even when empty
        df['Checkout Date'] = pd.to_datetime(df['Checkout Date'])
        df['Return Date'] = pd.to_datetime(df['Return Date'])

        # Create the Excel file and empty text files
        df.to_excel(EXCEL_FILE_PATH, index=False, engine="openpyxl")
        TYPE_LIST_PATH.touch()
        ASSIGNED_TO_LIST_PATH.touch()
        DRIVERS_LIST_PATH.touch()

        # Push the new files to the repo to initialize it
        if REPO_DIR.is_dir():  # Only push if we are in a git repo context
            with st.spinner("Pushing initial data files to GitHub..."):
                push_changes_to_github("Initialize data files")
            st.success("Repository initialized successfully. The app will now reload.")
            st.rerun()


@st.cache_data
def load_lookup_list(file_path):
    """Loads a list from a text file."""
    if not file_path.exists():
        return []
    with open(file_path, "r") as f:
        return sorted([line.strip() for line in f if line.strip()])


@st.cache_data
def load_vehicle_data(file_path):
    """Loads and processes the main vehicle data from the Excel file."""
    try:
        df = pd.read_excel(file_path, engine="openpyxl")

        # Data cleaning and type conversion
        df['Checkout Date'] = pd.to_datetime(df['Checkout Date'])
        df['Return Date'] = pd.to_datetime(df['Return Date'])
        df['Notes'] = df['Notes'].astype(str).fillna('')
        df['Authorized Drivers'] = df['Authorized Drivers'].astype(str).fillna('')

        # Ensure a unique ID for editing
        if "Unique ID" not in df.columns or df["Unique ID"].isnull().any():
            df["Unique ID"] = range(len(df))

        df = df.sort_values(by="Type", ascending=True)
        return df
    except Exception as e:
        st.error(f"Error loading or processing Excel file: {e}")
        return pd.DataFrame()  # Return empty dataframe on error


# --- 4. UI COMPONENTS ---
def display_welcome_message():
    """Shows a one-time welcome message using an expander."""
    if "popup_shown" not in st.session_state:
        st.session_state.popup_shown = False

    if not st.session_state.popup_shown:
        with st.expander("🚀 Welcome to SoF Vehicle Assignments! (Click to Dismiss)", expanded=True):
            st.markdown("""
            - **Legend Toggle**: Use the "Show Legend" checkbox to toggle legend visibility.
            - **Navigate Chart**: Use the tools in the top-right of the chart to pan and zoom.
            - **Phone Use**: Drag your finger along the vehicle types on the left to scroll vertically.
            """)
            if st.button("Close Tips"):
                st.session_state.popup_shown = True
                st.rerun()


@st.cache_data(ttl=3600)  # Cache the chart for an hour or until inputs change
def generate_gantt_chart(_df, view_mode, show_legend):
    """Generates the Plotly Gantt chart. Caching this is a major performance win."""
    if _df.empty:
        st.info("No vehicle assignments to display. Add new entries in the 'Manage Entries' section.")
        fig = go.Figure()
        fig.update_layout(
            title="Vehicle Assignments",
            height=800,
            annotations=[
                dict(
                    text="No data available",
                    showarrow=False,
                    xref="paper",
                    yref="paper",
                    x=0.5,
                    y=0.5,
                )
            ],
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
        )
        return fig

    df = _df.copy()
    today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)

    # Define date ranges for the chart view
    start_range = today - timedelta(weeks=2)
    end_range = today + timedelta(weeks=4)
    week_range = end_range + timedelta(weeks=10)  # For drawing gridlines far out

    xaxis_range = (
        [today - timedelta(days=2), today + timedelta(days=5)]
        if view_mode == "Mobile"
        else [start_range, end_range]
    )

    # --- NEW: Separate data for confirmed and reserved entries ---
    df_confirmed = df[df['Status'] == 'Confirmed'].copy()
    df_reserved = df[df['Status'] == 'Reserved'].copy()

    df_confirmed["Bar Label"] = df_confirmed.apply(
        lambda row: f"{row['Vehicle #']} - {row['Assigned to']}",
        axis=1
    )

    custom_colors = [
        "#353850", "#3A565A", "#3E654C", "#557042", "#7C7246", "#884C49",
        "#944C7F", "#7B4FA1", "#503538", "#5A3A56", "#4C3E65", "#425570",
        "#467C72", "#49884C", "#80944C", "#A1794F", "#395035", "#575A3A",
        "#654B3E", "#704255", "#72467C", "#4C4988", "#4C8094", "#4FA179"
    ]

    assigned_to_names = df["Assigned to"].unique()
    color_map = {name: custom_colors[i % len(custom_colors)] for i, name in enumerate(assigned_to_names)}

    # --- Create the base figure with CONFIRMED entries only ---
    fig = px.timeline(
        df_confirmed,
        x_start="Checkout Date",
        x_end="Return Date",
        y="Type",
        color="Assigned to",
        color_discrete_map=color_map,
        title="Vehicle Assignments",
        hover_data=["Unique ID", "Assigned to", "Status", "Type", "Checkout Date", "Return Date", "Authorized Drivers",
                    "Notes"],
        text="Bar Label"
    )

    # --- Chart Styling for main bars ---
    fig.update_traces(
        textposition="inside",
        insidetextanchor="start",
        textfont=dict(size=12, color="white", family="Arial Black"),
        opacity=0.9,
        width=0.9  # Set a standard width for the main bars
    )

    # --- Manually add RESERVED entries as separate, offset bars ---
    show_reserved_legend = True
    for _, row in df_reserved.iterrows():
        fig.add_trace(
            go.Bar(
                y=[row['Type']],
                x='Return Date',
                base=[row['Checkout Date']],
                orientation='h',
                marker=dict(
                    color='rgba(220, 53, 69, 0.6)',  # Semi-transparent red
                    line=dict(width=1, color='rgba(220, 53, 69, 1.0)')
                ),
                width=0.9,  # Make the reserved bar thinner
                offset=-0.0,  # Shift it down to appear below the main bar
                hovertext=f"<b>Reserved for {row['Assigned to']}</b><br>({row['Checkout Date']:%Y-%m-%d} to {row['Return Date']:%Y-%m-%d})",
                hoverinfo="text",
                name="Reserved",
                showlegend=show_reserved_legend
            )
        )
        show_reserved_legend = False  # Only show the legend item once

    unique_types = df['Type'].unique()
    fig.update_yaxes(categoryorder="array", categoryarray=unique_types, title=None)

    # Add a vertical line for today's date
    today_label = today + pd.Timedelta(hours=12)
    fig.add_vline(x=today_label, line_width=2, line_dash="dash", line_color="red", layer="below")

    # Add an annotation for the "Today" line
    fig.add_annotation(
        x=today_label,
        y=1,
        yref="paper",
        showarrow=False,
        text="Today",
        bgcolor="red",
        font=dict(color="white")
    )

    current_date = start_range
    while current_date <= week_range:
        current_date = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
        if current_date.weekday() == 0:
            fig.add_shape(
                type="line",
                x0=current_date,
                y0=0,
                x1=current_date,
                y1=1,
                xref="x",
                yref="paper",
                line=dict(color="gray", width=1.5, dash="solid"),
                layer="below",
            )
        fig.add_shape(
            type="line",
            x0=current_date,
            y0=0,
            x1=current_date,
            y1=1,
            xref="x",
            yref="paper",
            line=dict(color="lightgray", width=0.5, dash="dot"),
            layer="below",
        )
        current_date += timedelta(days=1)

    for idx, label in enumerate(unique_types):
        fig.add_shape(
            type="line",
            x0=start_range,
            y0=idx - 0.5,
            x1=week_range,
            y1=idx - 0.5,
            xref="x",
            yref="y",
            line=dict(color="lightgray", width=1, dash="dot"),
        )

    fig.update_layout(
        height=800,
        title_font_size=20,
        margin=dict(l=10, r=10, t=50, b=20),
        showlegend=show_legend,
        xaxis_range=xaxis_range
    )

    tick_dates = pd.date_range(start=start_range, end=end_range, freq="D") + pd.Timedelta(hours=12)
    tick_labels = [d.strftime("%a")[0] + "<br>" + d.strftime("%d/%m") for d in tick_dates]
    fig.update_xaxes(
        tickmode="array",
        tickvals=tick_dates,
        ticktext=tick_labels,
        tickangle=0,
        tickfont=dict(size=10),
    )

    return fig


def display_management_interface(df):
    """Renders the password-protected management UI."""
    with st.expander("🔧 Manage Entries (VEM use only)"):
        passcode = st.text_input("Enter Passcode:", type="password", key="passcode_input")

        if passcode != VEM_PASSCODE:
            if passcode:  # Only show error if something was entered
                st.error("Incorrect passcode.")
            return df  # Return original dataframe if auth fails

        st.success("Access Granted!")

        # Use session state to track edits, initializing it from the main df
        if 'edited_df' not in st.session_state:
            st.session_state.edited_df = df.copy()

        # --- UI TABS for better organization ---
        tab1, tab2, tab3 = st.tabs(["📝 Edit Entries", "➕ Create New Entry", "🗑️ Delete Entries"])

        with tab1:
            st.subheader("Filter and Edit Entries Inline")
            st.info(
                "You can directly edit, add, or delete rows in the table below. Click 'Save and Push Changes' when you're done.")

            # Use the powerful st.data_editor
            edited_df = st.data_editor(
                st.session_state.edited_df,
                num_rows="dynamic",  # Allows adding and deleting rows
                use_container_width=True,
                column_config={
                    "Unique ID": st.column_config.NumberColumn(disabled=True),
                    "Type": st.column_config.SelectboxColumn("Type", options=load_lookup_list(TYPE_LIST_PATH),
                                                             required=True),
                    "Assigned to": st.column_config.SelectboxColumn("Assigned to",
                                                                    options=load_lookup_list(ASSIGNED_TO_LIST_PATH),
                                                                    required=True),
                    "Status": st.column_config.SelectboxColumn("Status", options=["Confirmed", "Reserved"],
                                                               required=True),
                    "Checkout Date": st.column_config.DateColumn("Checkout", required=True),
                    "Return Date": st.column_config.DateColumn("Return", required=True),
                    "Authorized Drivers": st.column_config.SelectboxColumn("Authorized Drivers",options=load_lookup_list(DRIVERS_LIST_PATH),required=True)
                },
                key="data_editor"
            )

            if st.button("💾 Save and Push Changes"):
                with st.spinner("Saving changes and pushing to GitHub..."):
                    # Re-assign unique IDs before saving
                    edited_df.reset_index(drop=True, inplace=True)
                    edited_df["Unique ID"] = edited_df.index

                    # Save to Excel file
                    edited_df.to_excel(EXCEL_FILE_PATH, index=False, engine="openpyxl")

                    # Push to Git
                    commit_message = f"Data update from Streamlit app by user at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    push_changes_to_github(commit_message)

                    # Clear caches to force a reload of data from the repo
                    st.cache_data.clear()

                    # Update session state and rerun
                    st.session_state.edited_df = edited_df.copy()
                    st.rerun()

        with tab2:
            st.subheader("Create a Single New Entry")
            with st.form("new_entry_form", clear_on_submit=True):
                new_entry = {}
                new_entry["Type"] = st.selectbox("Type (Vehicle):", options=load_lookup_list(TYPE_LIST_PATH), index=None,
                                                 key="new_type")
                new_entry["Assigned to"] = st.selectbox("Assigned to:", options=load_lookup_list(ASSIGNED_TO_LIST_PATH), index=None,
                                                        key="new_assigned")
                new_entry["Status"] = st.selectbox("Status:", ["Confirmed", "Reserved"], key="new_status")
                new_entry["Checkout Date"] = st.date_input("Checkout Date:", value=datetime.today(), key="new_checkout")
                new_entry["Return Date"] = st.date_input("Return Date:", value=datetime.today() + timedelta(days=1),
                                                         key="new_return")

                # Auto-populate vehicle number from type
                try:
                    new_entry["Vehicle #"] = int(new_entry["Type"].split("-")[0].strip()) if new_entry["Type"] else 0
                except:
                    new_entry["Vehicle #"] = 0

                new_entry["Authorized Drivers"] = st.multiselect("Authorized Drivers:", options=load_lookup_list(DRIVERS_LIST_PATH),
                                                                key="new_drivers")
                new_entry["Notes"] = st.text_area("Notes:", key="new_notes")

                submitted = st.form_submit_button("Add New Entry and Push")
                if submitted:
                    new_entry_df = pd.DataFrame([new_entry])

                    # Ensure consistent datetime format
                    new_entry_df['Checkout Date'] = pd.to_datetime(new_entry_df['Checkout Date'])
                    new_entry_df['Return Date'] = pd.to_datetime(new_entry_df['Return Date'])

                    # Append to the dataframe in session state
                    updated_df = pd.concat([st.session_state.edited_df, new_entry_df], ignore_index=True)
                    updated_df["Unique ID"] = updated_df.index  # Reset IDs

                    # --- FIX: Save the updated dataframe to the excel file before pushing ---
                    updated_df.to_excel(EXCEL_FILE_PATH, index=False, engine="openpyxl")

                    commit_message = f"Added new entry via Streamlit app at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

                    with st.spinner("Adding new entry and pushing to GitHub..."):
                        push_changes_to_github(commit_message)

                    st.success("New entry added and pushed to GitHub!")
                    st.cache_data.clear()
                    st.rerun()

        with tab3:
            st.subheader("Bulk Delete Entries by Date Range")
            st.warning("This action is permanent after you save and push.", icon="⚠️")

            with st.form("bulk_delete_form"):
                start_dt = st.date_input("Delete entries with a 'Return Date' ON or BEFORE:")
                confirm_delete = st.checkbox("Yes, I want to delete these entries.")

                delete_submitted = st.form_submit_button("Delete Entries")
                if delete_submitted:
                    if confirm_delete and start_dt:
                        start_ts = pd.to_datetime(start_dt)

                        # Filter out the rows to be deleted
                        rows_before = len(st.session_state.edited_df)
                        st.session_state.edited_df = st.session_state.edited_df[
                            st.session_state.edited_df['Return Date'] > start_ts].copy()
                        rows_after = len(st.session_state.edited_df)

                        st.success(
                            f"{rows_before - rows_after} entries marked for deletion. Go to the 'Edit Entries' tab and click 'Save and Push' to finalize.")
                        st.rerun()
                    else:
                        st.error("Please confirm the deletion by checking the box.")

        return st.session_state.edited_df


# --- 5. MAIN APP LOGIC ---
def main():
    st.set_page_config(layout="wide", page_title="SoF Vehicle Assignments", page_icon="📊")
    st.title("SoF Vehicle Assignments")

    # --- Setup and Data Loading ---
    # Only setup git and clone if we are in a local/dev environment
    if REPO_DIR.is_dir():
        setup_ssh_and_git()
        clone_or_pull_repo()
    else:  # In deployed environment, still need to setup SSH for pushing
        setup_ssh_and_git()

    # Initialize data files if they don't exist.
    initialize_data_files_if_needed()

    df = load_vehicle_data(EXCEL_FILE_PATH)
    if df.empty and not EXCEL_FILE_PATH.exists():
        st.warning("Could not load vehicle data. The application may not function correctly.")
        st.stop()

    # --- UI Rendering ---
    display_welcome_message()

    view_mode = st.selectbox("View Mode", ["Desktop", "Mobile"], index=0)
    show_legend = st.checkbox("Show Legend", value=False)

    # Generate and display the Gantt chart
    gantt_fig = generate_gantt_chart(df, view_mode, show_legend)
    st.plotly_chart(gantt_fig, use_container_width=True)

    # Display the data table in an expander
    with st.expander("View Full Data Table"):
        st.dataframe(df)

    # Display the management interface
    display_management_interface(df)


if __name__ == "__main__":
    main()
