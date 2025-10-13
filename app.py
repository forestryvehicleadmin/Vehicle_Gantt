import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime, timedelta
import subprocess
import os
from pathlib import Path
import toml  # <-- Add this import

# --- 1. CONFIGURATION & CONSTANTS ---
# Prefer secrets.toml if present, else fallback to st.secrets
def load_secrets():
    secrets_path = Path("secrets.toml")
    if secrets_path.exists():
        secrets = toml.load(secrets_path)
        return {
            "GITHUB_REPO": secrets["git"]["repo"],
            "GITHUB_BRANCH": secrets["git"]["branch"],
            "VEM_PASSCODE": secrets["auth"]["passcode"],
            "DEPLOY_KEY": secrets["git"]["deploy_key"],
        }
    else:
        return {
            "GITHUB_REPO": st.secrets["git"]["repo"],
            "GITHUB_BRANCH": st.secrets["git"]["branch"],
            "VEM_PASSCODE": st.secrets["auth"]["passcode"],
            "DEPLOY_KEY": st.secrets["git"]["deploy_key"],
        }

try:
    secrets = load_secrets()
    GITHUB_REPO = secrets["GITHUB_REPO"]
    GITHUB_BRANCH = secrets["GITHUB_BRANCH"]
    VEM_PASSCODE = secrets["VEM_PASSCODE"]
    DEPLOY_KEY = secrets["DEPLOY_KEY"]
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


def set_time_to_2359(dt):
    """Sets the time of a datetime or date object to 23:59."""
    if pd.isnull(dt):
        return pd.NaT
    if isinstance(dt, pd.Timestamp):
        return dt.replace(hour=23, minute=59, second=0, microsecond=0)
    if isinstance(dt, datetime):
        return dt.replace(hour=23, minute=59, second=0, microsecond=0)
    if isinstance(dt, str):
        try:
            dt = pd.to_datetime(dt)
            return dt.replace(hour=23, minute=59, second=0, microsecond=0)
        except Exception:
            return pd.NaT
    return pd.to_datetime(dt).replace(hour=23, minute=59, second=0, microsecond=0)

@st.cache_data
def load_vehicle_data(file_path):
    """Loads and processes the main vehicle data from the Excel file."""
    try:
        df = pd.read_excel(file_path, engine="openpyxl")

        # Data cleaning and type conversion
        df['Checkout Date'] = pd.to_datetime(df['Checkout Date'])
        df['Return Date'] = pd.to_datetime(df['Return Date'])
        # --- Ensure all Return Dates are at 23:59 ---
        df['Return Date'] = df['Return Date'].apply(set_time_to_2359)
        df['Notes'] = df['Notes'].astype(str).fillna('')
        df['Authorized Drivers'] = df['Authorized Drivers'].astype(str).fillna('')

        # Ensure a unique ID for editing
        if "Unique ID" not in df.columns or df["Unique ID"].isnull().any():
            df["Unique ID"] = range(len(df))

        df = df.sort_values(by="Unique ID", ascending=True)
        return df
    except Exception as e:
        st.error(f"Error loading or processing Excel file: {e}")
        return pd.DataFrame()  # Return empty dataframe on error

# Function to read contents of type_list.txt and display line by line
def load_type_list(file_path):
    try:
        with open(file_path, "r") as file:
            lines = file.readlines()  # Read each line into a list
            return "\n".join(line.strip() for line in lines if line.strip())  # Join with new lines
    except FileNotFoundError:
        return "File not found."

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

    # Conditionally create the bar label. If status is 'Reserved', the label is empty.
    df["Bar Label"] = df.apply(
        lambda row: f"{row['Vehicle #']} - {row['Assigned to']}" if row['Status'] != 'Reserved' else "",
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

    fig = px.timeline(
        df,
        x_start="Checkout Date",
        x_end="Return Date",
        y="Type",
        color="Assigned to",
        color_discrete_map=color_map,
        title="Vehicle Assignments",
        hover_data=["Unique ID", "Assigned to", "Status", "Type", "Checkout Date", "Return Date", "Authorized Drivers",
                    "Notes"],
        text="Bar Label",
        pattern_shape="Status",
    )

    # --- Force "Reserved" traces below "Confirmed" ---
    # Sort fig.data so Reserved comes before Confirmed
    fig.data = tuple(sorted(fig.data, key=lambda t: 0 if "Reserved" in t.name else 1))

    # --- Chart Styling ---
    fig.update_traces(
        textposition="inside",
        insidetextanchor="start",
        textfont=dict(size=12, color="white", family="Arial Black"),
        opacity=0.9,

    )

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
        xaxis_range=xaxis_range,
        yaxis_fixedrange=True,
        dragmode="pan",
    )

    tick_dates = pd.date_range(start=start_range, end=week_range, freq="D") + pd.Timedelta(hours=12)
    tick_labels = [d.strftime("%a")[0] + "<br>" + d.strftime("%m/%d") for d in tick_dates]
    fig.update_xaxes(
        tickmode="array",
        tickvals=tick_dates,
        ticktext=tick_labels,
        tickangle=0,
        tickfont=dict(size=10),
    )
    ycats = fig.layout.yaxis.categoryarray
    ylabs = [str(c)[:3] for c in ycats]
    fig.update_yaxes(
        tickmode="array",
        tickvals=ycats,
        ticktext=ylabs,
    )

    return fig

def vehicles():
    with st.expander('Vehicle list'):
        st.subheader("Vehicle Type List")
        type_list_content = load_type_list("type_list.txt")

        # Use st.markdown() to display line-separated vehicle types
        st.markdown(f"```\n{type_list_content}\n```")


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
        tab1, tab_bulk, tab2, tab3, tab4 = st.tabs([
            "➕ Create New Entry",
            "📅 Bulk Create Entries",
            "🗑️ Delete Entries",
            "📝 Edit Entries",
            "👤 Manage Lists"
        ])

        with tab1:
            st.subheader("Create a Single New Entry")
            with st.form("new_entry_form", clear_on_submit=True):
                new_entry = {}
                new_entry["Type"] = st.selectbox("Type (Vehicle):", options=load_lookup_list(TYPE_LIST_PATH),
                                                 index=None,
                                                 key="new_type")
                new_entry["Assigned to"] = st.selectbox("Assigned to:", options=load_lookup_list(ASSIGNED_TO_LIST_PATH),
                                                        index=None,
                                                        key="new_assigned")
                new_entry["Status"] = st.selectbox("Status:", ["Confirmed", "Reserved"], key="new_status")
                new_entry["Checkout Date"] = st.date_input("Checkout Date:", value=datetime.today(), key="new_checkout")
                new_entry["Return Date"] = st.date_input("Return Date:", value=datetime.today() + timedelta(days=1),
                                                     key="new_return")
                # --- Set Return Date to 23:59 ---
                new_entry["Return Date"] = set_time_to_2359(new_entry["Return Date"])

                # Auto-populate vehicle number from type
                try:
                    new_entry["Vehicle #"] = int(new_entry["Type"].split("-")[0].strip()) if new_entry["Type"] else 0
                except:
                    new_entry["Vehicle #"] = 0

                new_entry["Authorized Drivers"] = st.multiselect("Authorized Drivers:",
                                                                 options=load_lookup_list(DRIVERS_LIST_PATH),
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
                    st.session_state.edited_df = load_vehicle_data(EXCEL_FILE_PATH)
                    st.rerun()

        with tab_bulk:
            st.subheader("Bulk Create Entries (Select Weekdays or Multiple Date Ranges)")
            bulk_mode = st.radio(
                "Bulk Entry Mode:",
                options=["By Weekdays in Date Range", "By Selecting Multiple Date Ranges"],
                index=0,
                key="bulk_mode"
            )
            with st.form("bulk_create_form", clear_on_submit=True):
                bulk_type = st.selectbox("Type (Vehicle):", options=load_lookup_list(TYPE_LIST_PATH), key="bulk_type")
                bulk_assigned = st.selectbox("Assigned to:", options=load_lookup_list(ASSIGNED_TO_LIST_PATH), key="bulk_assigned")
                bulk_status = st.selectbox("Status:", ["Confirmed", "Reserved"], key="bulk_status")
                bulk_drivers = st.multiselect("Authorized Drivers:", options=load_lookup_list(DRIVERS_LIST_PATH), key="bulk_drivers")
                bulk_notes = st.text_area("Notes:", key="bulk_notes")

                if bulk_mode == "By Weekdays in Date Range":
                    bulk_start = st.date_input("Start Date:", value=datetime.today(), key="bulk_start")
                    bulk_end = st.date_input("End Date:", value=datetime.today() + timedelta(days=7), key="bulk_end")
                    weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                    weekday_indices = list(range(7))
                    bulk_weekdays = st.multiselect(
                        "Select Weekdays:",
                        options=weekday_indices,
                        format_func=lambda i: weekday_names[i],
                        default=[3, 4],
                        key="bulk_weekdays"
                    )
                else:
                    # --- Multi date range picker using session state ---
                    if "bulk_date_ranges" not in st.session_state:
                        st.session_state.bulk_date_ranges = []
                    st.write("Add one or more date ranges below:")
                    col1, col2, col3 = st.columns([1, 1, 1])
                    with col1:
                        range_start = st.date_input("Range Start", value=datetime.today(), key="range_start")
                    with col2:
                        range_end = st.date_input("Range End", value=datetime.today() + timedelta(days=1), key="range_end")
                    with col3:
                        if st.form_submit_button("Add Range"):
                            if range_end < range_start:
                                st.warning("End date must be after start date.")
                            else:
                                st.session_state.bulk_date_ranges.append((range_start, range_end))
                    for idx, (start, end) in enumerate(st.session_state.bulk_date_ranges):
                        st.write(f"Range {idx+1}: {start} to {end}")
                        if st.form_submit_button(f"Remove Range {idx+1}"):
                            st.session_state.bulk_date_ranges.pop(idx)
                            st.experimental_rerun()

                submitted_bulk = st.form_submit_button("Add Bulk Entries and Push")
                if submitted_bulk:
                    if not bulk_type or not bulk_assigned:
                        st.error("Please fill in all required fields.")
                    elif bulk_mode == "By Weekdays in Date Range":
                        if not bulk_start or not bulk_end or not bulk_weekdays:
                            st.error("Please select a start date, end date, and at least one weekday.")
                        elif bulk_end < bulk_start:
                            st.error("End date must be after start date.")
                        else:
                            start_dt = pd.to_datetime(bulk_start)
                            end_dt = pd.to_datetime(bulk_end)
                            all_dates = pd.date_range(start=start_dt, end=end_dt, freq="D")
                            # Only keep dates matching selected weekdays
                            filtered_dates = [d for d in all_dates if d.weekday() in bulk_weekdays]
                            if not filtered_dates:
                                st.warning("No selected weekdays in the chosen range.")
                            else:
                                # --- Group consecutive dates into ranges ---
                                grouped_ranges = []
                                if filtered_dates:
                                    current_start = filtered_dates[0]
                                    current_end = filtered_dates[0]
                                    for d in filtered_dates[1:]:
                                        if (d - current_end).days == 1:
                                            current_end = d
                                        else:
                                            grouped_ranges.append((current_start, current_end))
                                            current_start = d
                                            current_end = d
                                    grouped_ranges.append((current_start, current_end))
                                # --- Create one entry per consecutive range ---
                                new_entries = []
                                for start, end in grouped_ranges:
                                    entry = {
                                        "Type": bulk_type,
                                        "Assigned to": bulk_assigned,
                                        "Status": bulk_status,
                                        "Checkout Date": start,
                                        "Return Date": set_time_to_2359(end),
                                        "Vehicle #": int(bulk_type.split("-")[0].strip()) if bulk_type and "-" in bulk_type else 0,
                                        "Authorized Drivers": ", ".join(bulk_drivers),
                                        "Notes": bulk_notes,
                                    }
                                    new_entries.append(entry)
                                new_entries_df = pd.DataFrame(new_entries)
                                new_entries_df['Checkout Date'] = pd.to_datetime(new_entries_df['Checkout Date'])
                                new_entries_df['Return Date'] = new_entries_df['Return Date'].apply(set_time_to_2359)

                                updated_df = pd.concat([st.session_state.edited_df, new_entries_df], ignore_index=True)
                                updated_df["Unique ID"] = updated_df.index

                                updated_df.to_excel(EXCEL_FILE_PATH, index=False, engine="openpyxl")

                                commit_message = f"Bulk added {len(new_entries)} entries (grouped weekdays) via Streamlit app at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

                                with st.spinner("Adding bulk entries and pushing to GitHub..."):
                                    push_changes_to_github(commit_message)

                                st.success(f"{len(new_entries)} entries added and pushed to GitHub!")
                                st.cache_data.clear()
                                st.session_state.edited_df = load_vehicle_data(EXCEL_FILE_PATH)
                                st.session_state.bulk_date_ranges = []
                                st.rerun()
                    else:
                        # Multiple date ranges mode
                        if not st.session_state.bulk_date_ranges:
                            st.error("Please add at least one date range.")
                        else:
                            all_dates = []
                            for start, end in st.session_state.bulk_date_ranges:
                                dr = pd.date_range(start=start, end=end, freq="D")
                                all_dates.extend(dr)
                            selected_dates = sorted(set(all_dates))
                            if not selected_dates:
                                st.warning("No dates in the selected ranges.")
                            else:
                                new_entries = []
                                for d in selected_dates:
                                    entry = {
                                        "Type": bulk_type,
                                        "Assigned to": bulk_assigned,
                                        "Status": bulk_status,
                                        "Checkout Date": d,
                                        "Return Date": set_time_to_2359(d),
                                        "Vehicle #": int(bulk_type.split("-")[0].strip()) if bulk_type and "-" in bulk_type else 0,
                                        "Authorized Drivers": ", ".join(bulk_drivers),
                                        "Notes": bulk_notes,
                                    }
                                    new_entries.append(entry)
                                new_entries_df = pd.DataFrame(new_entries)
                                new_entries_df['Checkout Date'] = pd.to_datetime(new_entries_df['Checkout Date'])
                                new_entries_df['Return Date'] = new_entries_df['Return Date'].apply(set_time_to_2359)

                                updated_df = pd.concat([st.session_state.edited_df, new_entries_df], ignore_index=True)
                                updated_df["Unique ID"] = updated_df.index

                                updated_df.to_excel(EXCEL_FILE_PATH, index=False, engine="openpyxl")

                                commit_message = f"Bulk added {len(new_entries)} entries (multiple date ranges) via Streamlit app at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

                                with st.spinner("Adding bulk entries and pushing to GitHub..."):
                                    push_changes_to_github(commit_message)

                                st.success(f"{len(new_entries)} entries added and pushed to GitHub!")
                                st.cache_data.clear()
                                st.session_state.edited_df = load_vehicle_data(EXCEL_FILE_PATH)
                                st.session_state.bulk_date_ranges = []
                                st.rerun()

        with tab2:
            # --- NEW: Single Delete Section ---
            st.subheader("Delete a Single Entry")
            with st.form("single_delete_form"):
                def format_entry_for_selection(uid):
                    if uid is None:
                        return "Select an entry..."
                    try:
                        entry_row = st.session_state.edited_df.loc[uid]
                        return f"{entry_row['Vehicle #']} - {entry_row['Assigned to']} ({entry_row['Checkout Date'].strftime('%m-%d-%Y')} -> {entry_row['Return Date'].strftime('%m-%d-%Y')})"
                    except KeyError:
                        return "Invalid entry selected"

                options_list = [None] + st.session_state.edited_df['Unique ID'].tolist()

                entry_to_delete = st.selectbox(
                    "Select an entry to delete",
                    options=options_list,
                    format_func=format_entry_for_selection,
                    index=0
                )

                confirm_single_delete = st.checkbox("Yes, I want to delete this specific entry.")

                single_delete_submitted = st.form_submit_button("Delete Selected Entry and Push")
                if single_delete_submitted:
                    if confirm_single_delete and entry_to_delete is not None:
                        df_to_edit = st.session_state.edited_df.copy()
                        entry_info = format_entry_for_selection(entry_to_delete)

                        df_to_edit.drop(index=entry_to_delete, inplace=True)
                        df_to_edit.reset_index(drop=True, inplace=True)
                        df_to_edit["Unique ID"] = df_to_edit.index

                        df_to_edit.to_excel(EXCEL_FILE_PATH, index=False, engine="openpyxl")

                        commit_message = f"Deleted single entry: {entry_info}"
                        with st.spinner("Deleting entry and pushing to GitHub..."):
                            push_changes_to_github(commit_message)

                        st.success(f"Entry '{entry_info}' deleted successfully.")
                        st.cache_data.clear()
                        st.session_state.edited_df = load_vehicle_data(EXCEL_FILE_PATH)
                        st.rerun()
                    else:
                        st.error("Please select an entry and confirm the deletion by checking the box.")

            st.markdown("---")

            # --- Existing Bulk Delete Section ---
            st.subheader("Bulk Delete Entries by Date Range")
            st.warning("This action is permanent after you save and push.", icon="⚠️")

            with st.form("bulk_delete_form"):
                start_dt = st.date_input("Delete entries with a 'Return Date' ON or BEFORE:")
                # --- Set start_dt to 23:59 for comparison ---
                if start_dt:
                    start_ts = set_time_to_2359(start_dt)
                else:
                    start_ts = None
                confirm_delete = st.checkbox("Yes, I want to delete these entries.", key="bulk_confirm")

                delete_submitted = st.form_submit_button("Delete Entries and Push")
                if delete_submitted:
                    if confirm_delete and start_dt:
                        start_ts = pd.to_datetime(start_dt)

                        df_to_edit = st.session_state.edited_df.copy()
                        rows_before = len(df_to_edit)
                        # --- Compare using 23:59 time ---
                        df_to_edit = df_to_edit[df_to_edit['Return Date'] > start_ts]
                        rows_after = len(df_to_edit)

                        df_to_edit.reset_index(drop=True, inplace=True)
                        df_to_edit["Unique ID"] = df_to_edit.index

                        df_to_edit.to_excel(EXCEL_FILE_PATH, index=False, engine="openpyxl")

                        commit_message = f"Bulk deleted {rows_before - rows_after} entries before {start_dt.strftime('%m-%d-%Y')}"
                        with st.spinner("Deleting entries and pushing to GitHub..."):
                            push_changes_to_github(commit_message)

                        st.success(f"{rows_before - rows_after} entries deleted successfully.")
                        st.cache_data.clear()
                        st.session_state.edited_df = load_vehicle_data(EXCEL_FILE_PATH)
                        st.rerun()
                    else:
                        st.error("Please confirm the deletion by checking the box and selecting a date.")


        with tab3:
            st.subheader("Filter and Edit Entries Inline")

            # --- FIX: Filtering and merging logic ---
            # Create a copy to filter for display
            df_to_display = st.session_state.edited_df.copy()

            # --- Filtering controls ---
            type_options = ["All"] + sorted(df_to_display['Type'].unique())
            assigned_options = ["All"] + sorted(df_to_display['Assigned to'].unique())
            status_options = ["All", "Confirmed", "Reserved"]

            col1, col2, col3 = st.columns(3)
            with col1:
                filter_type = st.multiselect("Filter by Type", options=type_options, default=["All"])
            with col2:
                filter_assigned = st.multiselect("Filter by Assigned to", options=assigned_options, default=["All"])
            with col3:
                filter_status = st.selectbox("Filter by Status", options=status_options, index=0)

            # Apply filters if 'All' is not selected
            if "All" not in filter_type:
                df_to_display = df_to_display[df_to_display['Type'].isin(filter_type)]
            if "All" not in filter_assigned:
                df_to_display = df_to_display[df_to_display['Assigned to'].isin(filter_assigned)]
            if filter_status != "All":
                df_to_display = df_to_display[df_to_display['Status'] == filter_status]

            st.info(f"Showing {len(df_to_display)} of {len(st.session_state.edited_df)} total entries.")

            # Use the powerful st.data_editor on the filtered dataframe
            edited_filtered_df = st.data_editor(
                df_to_display,
                num_rows="dynamic",
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
                    
                },
                key="data_editor"
            )

            if st.button("💾 Save and Push Changes"):
                with st.spinner("Saving changes and pushing to GitHub..."):

                    # Create a copy of the original full dataframe to merge changes into
                    updated_full_df = st.session_state.edited_df.copy()

                    # Update the original dataframe with the edited rows from the filtered view
                    # This correctly handles modifications to existing rows
                    updated_full_df.set_index('Unique ID', inplace=True)
                    edited_filtered_df.set_index('Unique ID', inplace=True)
                    updated_full_df.update(edited_filtered_df)
                    updated_full_df.reset_index(inplace=True)

                    # Identify and handle deleted rows
                    original_ids = set(df_to_display['Unique ID'])
                    edited_ids = set(edited_filtered_df.index)
                    deleted_ids = original_ids - edited_ids
                    if deleted_ids:
                        updated_full_df = updated_full_df[~updated_full_df['Unique ID'].isin(deleted_ids)]

                    # Identify and handle added rows (they won't have an index in edited_filtered_df)
                    added_rows = edited_filtered_df[edited_filtered_df.index.isna()]
                    if not added_rows.empty:
                        added_rows.reset_index(drop=True, inplace=True)
                        updated_full_df = pd.concat([updated_full_df, added_rows], ignore_index=True)

                    # Final cleanup: sort and re-assign all unique IDs to ensure integrity
                    updated_full_df = updated_full_df.sort_values(by="Unique ID").reset_index(drop=True)
                    updated_full_df["Unique ID"] = updated_full_df.index

                    # --- Ensure Return Date is 23:59 for all rows ---
                    updated_full_df['Return Date'] = updated_full_df['Return Date'].apply(set_time_to_2359)

                    # Save the fully merged and cleaned dataframe to Excel
                    updated_full_df.to_excel(EXCEL_FILE_PATH, index=False, engine="openpyxl")

                    # Push to Git
                    commit_message = f"Data update from Streamlit app by user at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    push_changes_to_github(commit_message)

                    # Clear caches to force a reload of data from the repo
                    st.cache_data.clear()

                    # Update session state with the newly saved data and rerun
                    st.session_state.edited_df = updated_full_df.copy()
                    st.rerun()

        with tab4:
            st.subheader("Manage Dropdown Lists")

            def add_to_list_file(file_path, new_name):
                if not new_name:
                    st.warning("Please enter a name.")
                    return

                current_list = load_lookup_list(file_path)
                if new_name.lower() in [name.lower() for name in current_list]:
                    st.error(f"'{new_name}' already exists in the list.")
                    return

                with open(file_path, "a") as f:
                    f.write(f"\n{new_name}")

                commit_message = f"Added '{new_name}' to {file_path.name}"
                with st.spinner(f"Adding '{new_name}' and pushing to GitHub..."):
                    push_changes_to_github(commit_message)

                st.success(f"'{new_name}' added successfully.")
                st.cache_data.clear()
                st.session_state.edited_df = load_vehicle_data(EXCEL_FILE_PATH)
                st.rerun()

            with st.form("add_assigned_to_form"):
                st.write("Add a new person to the **'Assigned to'** list:")
                new_assigned_to = st.text_input("New Name:")
                submitted_assigned = st.form_submit_button("Add to 'Assigned To' List")
                if submitted_assigned:
                    add_to_list_file(ASSIGNED_TO_LIST_PATH, new_assigned_to)

            st.markdown("---")

            with st.form("add_driver_form"):
                st.write("Add a new person to the **'Authorized Drivers'** list:")
                new_driver = st.text_input("New Driver Name:")
                submitted_driver = st.form_submit_button("Add to 'Drivers' List")
                if submitted_driver:
                    add_to_list_file(DRIVERS_LIST_PATH, new_driver)

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

    vehicles()
    # Display the data table in an expander
    with st.expander("View Full Data Table"):
        st.dataframe(df)

    # Display the management interface
    display_management_interface(df)

if __name__ == "__main__":
    main()
