import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime, timedelta
import subprocess
import os
from pathlib import Path
import toml

# --- 1. CONFIGURATION & SECRETS ---
def load_secrets():
    try:
        # Check local file first, then Streamlit Cloud secrets
        if Path("secrets.toml").exists():
            sec = toml.load("secrets.toml")
            return {
                "REPO": sec["git"]["repo"],
                "BRANCH": sec["git"]["branch"],
                "PASS": sec["auth"]["passcode"],
                "KEY": sec["git"]["deploy_key"]
            }
        return {
            "REPO": st.secrets["git"]["repo"],
            "BRANCH": st.secrets["git"]["branch"],
            "PASS": st.secrets["auth"]["passcode"],
            "KEY": st.secrets["git"]["deploy_key"]
        }
    except Exception:
        st.error("Missing Secrets! Ensure GITHUB_REPO, GITHUB_BRANCH, VEM_PASSCODE, and DEPLOY_KEY are set.")
        st.stop()

secrets = load_secrets()
GITHUB_REPO = secrets["REPO"]
GITHUB_BRANCH = secrets["BRANCH"]
VEM_PASSCODE = secrets["PASS"]
DEPLOY_KEY = secrets["KEY"]
GIT_SSH_URL = f"git@github.com:{GITHUB_REPO}.git"

# Path definitions
base_path = Path(".")
EXCEL_FILE_PATH = base_path / "Vehicle_Checkout_List.xlsx"
TYPE_LIST_PATH = base_path / "type_list.txt"
ASSIGNED_TO_LIST_PATH = base_path / "assigned_to_list.txt"
DRIVERS_LIST_PATH = base_path / "authorized_drivers_list.txt"

# --- 2. GIT & SSH SETUP ---
def setup_ssh_and_git():
    ssh_dir = Path("~/.ssh").expanduser()
    ssh_dir.mkdir(exist_ok=True)
    
    key_file = ssh_dir / "github_deploy_key"
    key_file.write_text(DEPLOY_KEY)
    os.chmod(key_file, 0o600)
    
    config_file = ssh_dir / "config"
    config_file.write_text(f"Host github.com\n  HostName github.com\n  User git\n  IdentityFile {key_file}\n  StrictHostKeyChecking no\n")
    
    subprocess.run(["git", "config", "--global", "user.name", "Jacob Shelly"], check=False)
    subprocess.run(["git", "config", "--global", "user.email", "jcs595@nau.edu"], check=False)

def push_changes_to_github(commit_message):
    """Pushes Excel changes back to GitHub using the SSH Deploy Key."""
    try:
        setup_ssh_and_git()
        subprocess.run(["git", "add", "-A"], cwd=base_path, check=True)
        
        # Check if there's actually anything to commit
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if status.stdout.strip():
            subprocess.run(["git", "commit", "-m", commit_message], cwd=base_path, check=True)
            # Explicitly use the SSH URL to bypass permission errors
            subprocess.run(["git", "push", GIT_SSH_URL, f"HEAD:{GITHUB_BRANCH}"], cwd=base_path, check=True)
            st.success("Successfully saved and pushed to GitHub!")
    except Exception as e:
        st.error(f"GitHub Push Error: {e}")

# --- 3. DATA LOADING ---
def set_time_to_2359(dt):
    if pd.isnull(dt): return pd.NaT
    return pd.to_datetime(dt).replace(hour=23, minute=59, second=0)

@st.cache_data
def load_vehicle_data():
    if not EXCEL_FILE_PATH.exists():
        cols = ["Unique ID", "Type", "Vehicle #", "Assigned to", "Status", "Checkout Date", "Return Date", "Authorized Drivers", "Notes"]
        pd.DataFrame(columns=cols).to_excel(EXCEL_FILE_PATH, index=False, engine='openpyxl')
    
    df = pd.read_excel(EXCEL_FILE_PATH, engine='openpyxl')
    df['Checkout Date'] = pd.to_datetime(df['Checkout Date'])
    df['Return Date'] = pd.to_datetime(df['Return Date']).apply(set_time_to_2359)
    df['Unique ID'] = df.index
    return df

def load_list(path):
    if not path.exists(): return []
    with open(path, "r") as f:
        return [line.strip() for line in f if line.strip()]

# --- 4. UI AND CHARTS ---
st.set_page_config(layout="wide", page_title="SoF Vehicle Assignments")
st.title("SoF Vehicle Assignments")

df = load_vehicle_data()

# View Controls
view_col1, view_col2 = st.columns(2)
with view_col1:
    view_mode = st.selectbox("View Mode", ["Desktop", "Mobile"])
with view_col2:
    show_legend = st.checkbox("Show Legend", value=False)

# Gantt Chart
today = datetime.today().replace(hour=0, minute=0, second=0)
fig = px.timeline(df, x_start="Checkout Date", x_end="Return Date", y="Type", 
                  color="Assigned to", text="Vehicle #", hover_data=["Status", "Notes"])

# Reserved Status Shapes
unique_types = df['Type'].unique().tolist()
for _, row in df.iterrows():
    if row['Status'] == 'Reserved':
        try:
            y_val = unique_types.index(row['Type'])
            fig.add_shape(type="rect", x0=row['Checkout Date'], x1=row['Return Date'],
                          y0=y_val-0.4, y1=y_val+0.4, fillcolor="rgba(255,0,0,0.1)", 
                          line=dict(width=0), layer="below")
        except: pass

fig.update_layout(height=800, showlegend=show_legend)
fig.add_vline(x=today, line_width=2, line_dash="dash", line_color="red")
st.plotly_chart(fig, use_container_width=True)

# --- 5. MANAGEMENT INTERFACE ---
with st.expander("🔧 VEM Management Console"):
    auth_input = st.text_input("Passcode", type="password")
    if auth_input == VEM_PASSCODE:
        tabs = st.tabs(["➕ New Entry", "📝 Edit Table", "🗑️ Bulk Delete", "👤 Manage Lists"])
        
        with tabs[0]: # New Entry
            with st.form("new_entry_form"):
                st.write("Add a new assignment")
                n_type = st.selectbox("Vehicle Type", options=load_list(TYPE_LIST_PATH))
                n_assign = st.selectbox("Assigned To", options=load_list(ASSIGNED_TO_LIST_PATH))
                n_check = st.date_input("Checkout")
                n_ret = st.date_input("Return")
                n_status = st.selectbox("Status", ["Confirmed", "Reserved"])
                
                if st.form_submit_button("Submit
