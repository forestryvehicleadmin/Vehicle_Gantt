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

REPO_DIR = Path("repo")
if REPO_DIR.is_dir():
    base_path = REPO_DIR
else:
    base_path = Path(".") 

# --- CHANGED: Now looking for .xlsx ---
EXCEL_FILE_PATH = base_path / "Vehicle_Checkout_List.xlsx" 
TYPE_LIST_PATH = base_path / "type_list.txt"
ASSIGNED_TO_LIST_PATH = base_path / "assigned_to_list.txt"
DRIVERS_LIST_PATH = base_path / "authorized_drivers_list.txt"

GIT_SSH_URL = f"git@github.com:{GITHUB_REPO}.git"

# --- 2. GIT & SSH SETUP ---
def setup_ssh_and_git():
    ssh_dir = Path("~/.ssh").expanduser()
    ssh_dir.mkdir(exist_ok=True)
    deploy_key_path = ssh_dir / "github_deploy_key"
    config_path = ssh_dir / "config"
    deploy_key_path.write_text(DEPLOY_KEY)
    os.chmod(deploy_key_path, 0o600)
    config_text = f"Host github.com\n    HostName github.com\n    User git\n    IdentityFile {deploy_key_path}\n    StrictHostKeyChecking no\n"
    config_path.write_text(config_text)
    os.chmod(config_path, 0o600)
    subprocess.run(["git", "config", "--global", "user.name", "forestryvehicleadmin"], check=True)
    subprocess.run(["git", "config", "--global", "user.email", "forestryvehicleadmin@nau.edu"], check=True)

def clone_or_pull_repo():
    if not REPO_DIR.is_dir(): return
    try:
        subprocess.run(["git", "fetch", "origin", GITHUB_BRANCH], cwd=REPO_DIR, check=True, capture_output=True, text=True)
        subprocess.run(["git", "reset", "--hard", f"origin/{GITHUB_BRANCH}"], cwd=REPO_DIR, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        st.error(f"Git Error: {e.stderr}")
        st.stop()

def push_changes_to_github(commit_message):
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
        st.error(f"Git Error: {e.stderr}")

# --- 3. DATA LOADING & CACHING ---
def initialize_data_files_if_needed():
    if not EXCEL_FILE_PATH.exists():
        st.warning("Excel file not found. Initializing...")
        columns = ["Unique ID", "Type", "Vehicle #", "Assigned to", "Status", "Checkout Date", "Return Date", "Authorized Drivers", "Notes"]
        df = pd.DataFrame(columns=columns)
        # --- CHANGED: to_excel ---
        df.to_excel(EXCEL_FILE_PATH, index=False, engine='openpyxl')
        TYPE_LIST_PATH.touch()
        ASSIGNED_TO_LIST_PATH.touch()
        DRIVERS_LIST_PATH.touch()
        if REPO_DIR.is_dir():
            push_changes_to_github("Initialize Excel data file")
            st.rerun()

@st.cache_data
def load_lookup_list(file_path):
    if not file_path.exists(): return []
    with open(file_path, "r") as f:
        return sorted([line.strip() for line in f if line.strip()])

def set_time_to_2359(dt):
    if pd.isnull(dt): return pd.NaT
    dt = pd.to_datetime(dt)
    return dt.replace(hour=23, minute=59, second=0, microsecond=0)

@st.cache_data
def load_vehicle_data(file_path):
    try:
        # --- CHANGED: Now using read_excel ---
        df = pd.read_excel(file_path, engine='openpyxl')
        df['Checkout Date'] = pd.to_datetime(df['Checkout Date'])
        df['Return Date'] = pd.to_datetime(df['Return Date']).apply(set_time_to_2359)
        df['Notes'] = df['Notes'].astype(str).fillna('')
        df['Authorized Drivers'] = df['Authorized Drivers'].astype(str).fillna('')
        if "Unique ID" not in df.columns or df["Unique ID"].isnull().any():
            df["Unique ID"] = range(len(df))
        return df.sort_values(by="Unique ID")
    except Exception as e:
        st.error(f"Error loading Excel file: {e}")
        return pd.DataFrame()

def load_type_list(file_path):
    try:
        with open(file_path, "r") as file:
            return "\n".join(line.strip() for line in file if line.strip())
    except FileNotFoundError: return "File not found."

# --- 4. UI COMPONENTS ---
def display_welcome_message():
    if "popup_shown" not in st.session_state: st.session_state.popup_shown = False
    if not st.session_state.popup_shown:
        with st.expander("🚀 Welcome Tips", expanded=True):
            st.markdown("- **Legend Toggle** below chart\n- **Navigate** using Plotly tools")
            if st.button("Close Tips"):
                st.session_state.popup_shown = True
                st.rerun()

@st.cache_data(ttl=3600)
def generate_gantt_chart(_df, view_mode, show_legend):
    if _df.empty: return go.Figure()
    df = _df.copy()
    today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    xaxis_range = [today - timedelta(days=2), today + timedelta(days=5)] if view_mode == "Mobile" else [today - timedelta(weeks=2), today + timedelta(weeks=4)]
    df["Bar Label"] = df.apply(lambda row: f"{row['Vehicle #']} - {row['Assigned to']}" if row['Status'] != 'Reserved' else "", axis=1)
    fig = px.timeline(df, x_start="Checkout Date", x_end="Return Date", y="Type", color="Assigned to", text="Bar Label", pattern_shape="Status")
    fig.update_layout(height=800, showlegend=show_legend, xaxis_range=xaxis_range, dragmode="pan")
    fig.add_vline(x=today + pd.Timedelta(hours=12), line_width=2, line_dash="dash", line_color="red")
    return fig

def vehicles():
    with st.expander('Vehicle list'):
        st.markdown(f"```\n{load_type_list(TYPE_LIST_PATH)}\n```")

def display_management_interface(df):
    if "manage_expanded" not in st.session_state: st.session_state.manage_expanded = False
    if st.session_state.get("passcode_input") == VEM_PASSCODE: st.session_state.manage_expanded = True
    
    with st.expander("🔧 Manage Entries", expanded=st.session_state.manage_expanded):
        passcode = st.text_input("Passcode:", type="password", key="passcode_input")
        if passcode != VEM_PASSCODE: return df
        
        if 'edited_df' not in st.session_state: st.session_state.edited_df = df.copy()
        tabs = st.tabs(["➕ New", "📅 Bulk", "🗑️ Delete", "📝 Edit", "👤 Lists"])

        with tabs[0]: # New Entry
            with st.form("new_entry"):
                # (Inputs for v_type, v_assign, etc.)
                v_type = st.selectbox("Type:", options=load_lookup_list(TYPE_LIST_PATH))
                v_assign = st.selectbox("Assigned to:", options=load_lookup_list(ASSIGNED_TO_LIST_PATH))
                v_status = st.selectbox("Status:", ["Confirmed", "Reserved"])
                v_check = st.date_input("Checkout:")
                v_ret = st.date_input("Return:")
                if st.form_submit_button("Add Entry"):
                    # Add row logic...
                    new_row = pd.DataFrame([{"Type": v_type, "Assigned to": v_assign, "Status": v_status, "Checkout Date": pd.to_datetime(v_check), "Return Date": set_time_to_2359(v_ret), "Vehicle #": int(v_type.split("-")[0]) if v_type else 0}])
                    updated = pd.concat([st.session_state.edited_df, new_row], ignore_index=True)
                    updated["Unique ID"] = updated.index
                    # --- CHANGED: to_excel ---
                    updated.to_excel(EXCEL_FILE_PATH, index=False, engine='openpyxl')
                    push_changes_to_github("Added entry")
                    st.cache_data.clear()
                    st.rerun()

        with tabs[3]: # Edit Entries
            edited_df = st.data_editor(st.session_state.edited_df, num_rows="dynamic")
            if st.button("💾 Save All"):
                edited_df['Return Date'] = edited_df['Return Date'].apply(set_time_to_2359)
                # --- CHANGED: to_excel ---
                edited_df.to_excel(EXCEL_FILE_PATH, index=False, engine='openpyxl')
                push_changes_to_github("Updated spreadsheet")
                st.cache_data.clear()
                st.rerun()
    return st.session_state.edited_df

def main():
    st.set_page_config(layout="wide", page_title="Vehicle Assignments")
    setup_ssh_and_git()
    if REPO_DIR.is_dir(): clone_or_pull_repo()
    initialize_data_files_if_needed()
    df = load_vehicle_data(EXCEL_FILE_PATH)
    st.title("SoF Vehicle Assignments")
    view_mode = st.selectbox("View", ["Desktop", "Mobile"])
    st.plotly_chart(generate_gantt_chart(df, view_mode, False), use_container_width=True)
    vehicles()
    display_management_interface(df)

if __name__ == "__main__": main()
