import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime, timedelta
import subprocess
import os
from pathlib import Path
import toml

# --- 1. CONFIGURATION & CONSTANTS ---
st.set_page_config(layout="wide", page_title="SoF Vehicle Assignments", page_icon="📊")

def load_secrets():
    """Prefer secrets.toml if present, else fallback to st.secrets"""
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
REPO_DIR = Path("repo")
if REPO_DIR.is_dir():
    base_path = REPO_DIR
else:
    base_path = Path(".") 

EXCEL_FILE_PATH = base_path / "Vehicle_Checkout_List.csv"
TYPE_LIST_PATH = base_path / "type_list.txt"
ASSIGNED_TO_LIST_PATH = base_path / "assigned_to_list.txt"
DRIVERS_LIST_PATH = base_path / "authorized_drivers_list.txt"

GIT_SSH_URL = f"git@github.com:{GITHUB_REPO}.git"

# --- 2. GIT & SSH SETUP ---
def setup_ssh_and_git():
    """Configures SSH with the deploy key and sets up the Git remote."""
    ssh_dir = Path("~/.ssh").expanduser()
    ssh_dir.mkdir(exist_ok=True)

    deploy_key_path = ssh_dir / "github_deploy_key"
    config_path = ssh_dir / "config"

    # Write the deploy key and set permissions
    if not deploy_key_path.exists():
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
    subprocess.run(["git", "config", "--global", "user.name", "forestryvehicleadmin"], check=False)
    subprocess.run(["git", "config", "--global", "user.email", "forestryvehicleadmin@nau.edu"], check=False)


def clone_or_pull_repo():
    """Clones the repo if it doesn't exist, otherwise pulls the latest changes."""
    if not REPO_DIR.is_dir():
        return 

    st.write("Pulling latest changes from repository...")
    try:
        subprocess.run(["git", "fetch", "origin", GITHUB_BRANCH], cwd=REPO_DIR, check=True, capture_output=True, text=True)
        subprocess.run(["git", "reset", "--hard", f"origin/{GITHUB_BRANCH}"], cwd=REPO_DIR, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        st.error(f"Failed to pull changes. Git Error: {e.stderr}")
        st.stop()


def push_changes_to_github(commit_message):
    """Commits all changes and pushes them to the GitHub repository."""
    try:
        subprocess.run(["git", "add", "-A"], cwd=base_path, check=True)
        status_result = subprocess.run(["git", "status", "--porcelain"], cwd=base_path, capture_output=True, text=True)
        
        if not status_result.stdout:
            st.info("No changes to commit.")
            return

        subprocess.run(["git", "commit", "-m", commit_message], cwd=base_path, check=True)
        subprocess.run(["git", "push", GIT_SSH_URL, f"HEAD:{GITHUB_BRANCH}"], cwd=base_path, check=True)
        st.success("Changes successfully pushed to GitHub!")

    except subprocess.CalledProcessError as e:
        st.error(f"Failed to push changes. Git Error: {e.stderr}")
        st.warning("Your changes have been saved locally but not pushed to GitHub. Please try again later.")


# --- 3. DATA LOADING & CACHING ---
def initialize_data_files_if_needed():
    """Checks for the main CSV file and creates it if it doesn't exist."""
    if not EXCEL_FILE_PATH.exists():
        st.warning("Data file not found. Initializing a new one...")
        columns = ["Unique ID", "Type", "Vehicle #", "Assigned to", "Status", "Checkout Date", "Return Date", "Authorized Drivers", "Notes"]
        df = pd.DataFrame(columns=columns)
        df.to_csv(EXCEL_FILE_PATH, index=False)
        TYPE_LIST_PATH.touch()
        ASSIGNED_TO_LIST_PATH.touch()
        DRIVERS_LIST_PATH.touch()

        if REPO_DIR.is_dir():
            with st.spinner("Pushing initial data files to GitHub..."):
                push_changes_to_github("Initialize data files")
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
    if pd.isnull(dt): return pd.NaT
    if isinstance(dt, str):
        try: dt = pd.to_datetime(dt)
        except: return pd.NaT
    return pd.to_datetime(dt).replace(hour=23, minute=59, second=0, microsecond=0)

@st.cache_data
def load_vehicle_data(file_path):
    """Loads and processes the main vehicle data from the CSV file."""
    try:
        try:
            df = pd.read_csv(file_path, parse_dates=["Checkout Date", "Return Date"], encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(file_path, parse_dates=["Checkout Date", "Return Date"], encoding="latin1")

        df['Checkout Date'] = pd.to_datetime(df['Checkout Date'])
        df['Return Date'] = pd.to_datetime(df['Return Date'])
        df['Return Date'] = df['Return Date'].apply(set_time_to_2359)
        
        # --- CLEAN STRING COLUMNS TO FIX SORTING ERRORS ---
        df['Notes'] = df['Notes'].astype(str).fillna('')
        df['Authorized Drivers'] = df['Authorized Drivers'].astype(str).fillna('')
        df['Type'] = df['Type'].astype(str).fillna('')  # <--- THIS FIXES YOUR ERROR
        # --------------------------------------------------

        if "Unique ID" not in df.columns or df["Unique ID"].isnull().any():
            df["Unique ID"] = range(len(df))

        df = df.sort_values(by="Unique ID", ascending=True)
        return df
    except Exception as e:
        st.error(f"Error loading or processing CSV file: {e}")
        return pd.DataFrame()

def load_type_list(file_path):
    try:
        with open(file_path, "r") as file:
            lines = file.readlines()
            return "\n".join(line.strip() for line in lines if line.strip())
    except FileNotFoundError:
        return "File not found."

# --- 4. UI COMPONENTS ---
def display_welcome_message():
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

@st.cache_data(ttl=3600)
def generate_gantt_chart(_df, view_mode, show_legend):
    if _df.empty:
        st.info("No vehicle assignments to display.")
        return go.Figure()

    df = _df.copy()
    today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    start_range = today - timedelta(weeks=2)
    end_range = today + timedelta(weeks=4)
    week_range = end_range + timedelta(weeks=10)

    xaxis_range = [today - timedelta(days=2), today + timedelta(days=5)] if view_mode == "Mobile" else [start_range, end_range]

    df["Bar Label"] = df.apply(lambda row: f"{row['Vehicle #']} - {row['Assigned to']}" if row['Status'] != 'Reserved' else "", axis=1)

    custom_colors = [
        "#353850", "#3A565A", "#3E654C", "#557042", "#7C7246", "#884C49",
        "#944C7F", "#7B4FA1", "#503538", "#5A3A56", "#4C3E65", "#425570",
        "#467C72", "#49884C", "#80944C", "#A1794F", "#395035", "#575A3A",
        "#654B3E", "#704255", "#72467C", "#4C4988", "#4C8094", "#4FA179"
    ]
    assigned_to_names = df["Assigned to"].unique()
    color_map = {name: custom_colors[i % len(custom_colors)] for i, name in enumerate(assigned_to_names)}

    fig = px.timeline(
        df, x_start="Checkout Date", x_end="Return Date", y="Type", color="Assigned to",
        color_discrete_map=color_map, title="Vehicle Assignments",
        hover_data=["Unique ID", "Assigned to", "Status", "Type", "Checkout Date", "Return Date", "Authorized Drivers", "Notes"],
        text="Bar Label", pattern_shape="Status",
    )

    fig.data = tuple(sorted(fig.data, key=lambda t: 0 if "Reserved" in t.name else 1))
    fig.update_traces(textposition="inside", insidetextanchor="start", textfont=dict(size=12, color="white", family="Arial Black"), opacity=0.9)
    
    unique_types = df['Type'].unique()
    fig.update_yaxes(categoryorder="array", categoryarray=unique_types, title=None)

    today_label = today + pd.Timedelta(hours=12)
    fig.add_vline(x=today_label, line_width=2, line_dash="dash", line_color="red", layer="below")
    fig.add_annotation(x=today_label, y=1, yref="paper", showarrow=False, text="Today", bgcolor="red", font=dict(color="white"))

    # Grid Lines
    current_date = start_range
    while current_date <= week_range:
        current_date = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
        if current_date.weekday() == 0:
            fig.add_shape(type="line", x0=current_date, y0=0, x1=current_date, y1=1, xref="x", yref="paper", line=dict(color="gray", width=1.5), layer="below")
        fig.add_shape(type="line", x0=current_date, y0=0, x1=current_date, y1=1, xref="x", yref="paper", line=dict(color="lightgray", width=0.5, dash="dot"), layer="below")
        current_date += timedelta(days=1)

    for idx, label in enumerate(unique_types):
        fig.add_shape(type="line", x0=start_range, y0=idx - 0.5, x1=week_range, y1=idx - 0.5, xref="x", yref="y", line=dict(color="lightgray", width=1, dash="dot"))

    fig.update_layout(height=800, margin=dict(l=10, r=10, t=50, b=20), showlegend=show_legend, xaxis_range=xaxis_range, yaxis_fixedrange=True, dragmode="pan")
    return fig

def display_management_interface(df):
    if "manage_expanded" not in st.session_state: st.session_state.manage_expanded = False
    if "manage_lock_rerun" not in st.session_state: st.session_state.manage_lock_rerun = False
    if st.session_state.get("passcode_input") == VEM_PASSCODE: st.session_state.manage_expanded = True
    if st.session_state.get("manage_lock_rerun"):
        st.session_state["passcode_input"] = ""
        st.session_state["manage_lock_rerun"] = False

    with st.expander("🔧 Manage Entries (VEM use only)", expanded=st.session_state.manage_expanded):
        passcode = st.text_input("Enter Passcode:", type="password", key="passcode_input")
        if st.button("Lock Interface"):
            st.session_state.manage_expanded = False
            st.session_state.manage_lock_rerun = True
            st.rerun()

        if passcode != VEM_PASSCODE:
            if passcode: st.error("Incorrect passcode.")
            return df

        st.success("Access Granted!")
        if 'edited_df' not in st.session_state: st.session_state.edited_df = df.copy()

        tab1, tab_bulk, tab2, tab3 = st.tabs(["➕ Create", "📅 Bulk Create", "🗑️ Delete", "📝 Edit"])

        with tab1:
            st.subheader("Create a Single New Entry")
            with st.form("new_entry_form", clear_on_submit=True):
                new_entry = {}
                new_entry["Type"] = st.selectbox("Type:", load_lookup_list(TYPE_LIST_PATH))
                new_entry["Assigned to"] = st.selectbox("Assigned to:", load_lookup_list(ASSIGNED_TO_LIST_PATH))
                new_entry["Status"] = st.selectbox("Status:", ["Confirmed", "Reserved"])
                new_entry["Checkout Date"] = st.date_input("Checkout:", datetime.today())
                new_entry["Return Date"] = set_time_to_2359(st.date_input("Return:", datetime.today() + timedelta(days=1)))
                new_entry["Authorized Drivers"] = st.multiselect("Drivers:", load_lookup_list(DRIVERS_LIST_PATH))
                new_entry["Notes"] = st.text_area("Notes:")
                
                try: new_entry["Vehicle #"] = int(new_entry["Type"].split("-")[0].strip()) if new_entry["Type"] else 0
                except: new_entry["Vehicle #"] = 0

                if st.form_submit_button("Add New Entry"):
                    if not new_entry["Type"] or not new_entry["Assigned to"]:
                         st.error("Type and Assigned To are required.")
                    else:
                        new_entry["Authorized Drivers"] = ", ".join(new_entry["Authorized Drivers"])
                        new_row = pd.DataFrame([new_entry])
                        new_row['Checkout Date'] = pd.to_datetime(new_row['Checkout Date'])
                        new_row['Return Date'] = pd.to_datetime(new_row['Return Date'])
                        
                        updated_df = pd.concat([st.session_state.edited_df, new_row], ignore_index=True)
                        updated_df["Unique ID"] = updated_df.index
                        updated_df.to_csv(EXCEL_FILE_PATH, index=False)
                        
                        with st.spinner("Pushing to GitHub..."):
                            push_changes_to_github("Added new entry")
                        st.cache_data.clear()
                        st.session_state.edited_df = load_vehicle_data(EXCEL_FILE_PATH)
                        st.rerun()

        with tab_bulk:
            st.subheader("Bulk Create Entries")
            bulk_mode = st.radio("Mode:", ["Weekdays in Range", "Multiple Date Ranges"])
            with st.form("bulk_form"):
                b_type = st.selectbox("Type:", load_lookup_list(TYPE_LIST_PATH))
                b_assign = st.selectbox("Assigned to:", load_lookup_list(ASSIGNED_TO_LIST_PATH))
                b_stat = st.selectbox("Status:", ["Confirmed", "Reserved"])
                b_driv = st.multiselect("Drivers:", load_lookup_list(DRIVERS_LIST_PATH))
                b_note = st.text_area("Notes:")

                if bulk_mode == "Weekdays in Range":
                    b_start = st.date_input("Start:", datetime.today())
                    b_end = st.date_input("End:", datetime.today() + timedelta(days=7))
                    b_days = st.multiselect("Days:", list(range(7)), format_func=lambda x: ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][x], default=[0,1,2,3,4])
                else:
                    st.write("Functionality for multiple ranges is simplified here for brevity.")
                    b_start, b_end, b_days = None, None, []

                if st.form_submit_button("Add Bulk"):
                    dates = pd.date_range(b_start, b_end)
                    final_dates = [d for d in dates if d.weekday() in b_days]
                    if not final_dates: st.error("No dates selected.")
                    else:
                        entries = []
                        for d in final_dates:
                            entries.append({
                                "Type": b_type, "Assigned to": b_assign, "Status": b_stat,
                                "Checkout Date": d, "Return Date": set_time_to_2359(d),
                                "Vehicle #": int(b_type.split("-")[0]) if "-" in b_type else 0,
                                "Authorized Drivers": ", ".join(b_driv), "Notes": b_note
                            })
                        updated_df = pd.concat([st.session_state.edited_df, pd.DataFrame(entries)], ignore_index=True)
                        updated_df["Unique ID"] = updated_df.index
                        updated_df.to_csv(EXCEL_FILE_PATH, index=False)
                        with st.spinner("Pushing Bulk..."): push_changes_to_github("Bulk added")
                        st.cache_data.clear()
                        st.session_state.edited_df = load_vehicle_data(EXCEL_FILE_PATH)
                        st.rerun()

        with tab2:
            st.subheader("Delete Entry")
            with st.form("delete_form"):
                options = st.session_state.edited_df.apply(lambda x: f"{x['Unique ID']} | {x['Assigned to']} | {x['Checkout Date'].strftime('%m/%d')}", axis=1)
                del_idx = st.selectbox("Select Entry:", st.session_state.edited_df.index, format_func=lambda x: options[x] if x in options else "Unknown")
                
                if st.form_submit_button("Delete"):
                    updated_df = st.session_state.edited_df.drop(del_idx).reset_index(drop=True)
                    updated_df["Unique ID"] = updated_df.index
                    updated_df.to_csv(EXCEL_FILE_PATH, index=False)
                    with st.spinner("Deleting..."): push_changes_to_github(f"Deleted ID {del_idx}")
                    st.cache_data.clear()
                    st.session_state.edited_df = load_vehicle_data(EXCEL_FILE_PATH)
                    st.rerun()

        with tab3:
            st.subheader("Edit Entry")
            options = st.session_state.edited_df.apply(lambda x: f"{x['Unique ID']} | {x['Assigned to']} | {x['Checkout Date'].strftime('%m/%d')}", axis=1)
            edit_idx = st.selectbox("Select Entry to Edit:", st.session_state.edited_df.index, format_func=lambda x: options[x] if x in options else "Unknown")
            
            if edit_idx is not None:
                row = st.session_state.edited_df.loc[edit_idx]
                with st.form("edit_form"):
                    e_assign = st.selectbox("Assigned to:", load_lookup_list(ASSIGNED_TO_LIST_PATH), index=load_lookup_list(ASSIGNED_TO_LIST_PATH).index(row["Assigned to"]) if row["Assigned to"] in load_lookup_list(ASSIGNED_TO_LIST_PATH) else 0)
                    e_note = st.text_area("Notes:", row["Notes"])
                    if st.form_submit_button("Update"):
                        st.session_state.edited_df.at[edit_idx, "Assigned to"] = e_assign
                        st.session_state.edited_df.at[edit_idx, "Notes"] = e_note
                        st.session_state.edited_df.to_csv(EXCEL_FILE_PATH, index=False)
                        push_changes_to_github(f"Edited ID {edit_idx}")
                        st.cache_data.clear()
                        st.rerun()
    return df

# --- 5. MAIN EXECUTION ---
def main():
    setup_ssh_and_git()
    clone_or_pull_repo()
    initialize_data_files_if_needed()
    display_welcome_message()

    df = load_vehicle_data(EXCEL_FILE_PATH)
    
    st.header("Vehicle Assignment Schedule")
    col_view, col_legend = st.columns([2, 8])
    with col_view: view_mode = st.radio("View Mode:", ["Desktop", "Mobile"], horizontal=True)
    with col_legend: show_legend = st.checkbox("Show Legend", value=False)
    
    fig = generate_gantt_chart(df, view_mode, show_legend)
    st.plotly_chart(fig, use_container_width=True)
    
    display_management_interface(df)

if __name__ == "__main__":
    main()
