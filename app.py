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
        if Path("secrets.toml").exists():
            secrets = toml.load("secrets.toml")
            return {
                "REPO": secrets["git"]["repo"],
                "BRANCH": secrets["git"]["branch"],
                "PASSCODE": secrets["auth"]["passcode"],
                "KEY": secrets["git"]["deploy_key"],
            }
        return {
            "REPO": st.secrets["git"]["repo"],
            "BRANCH": st.secrets["git"]["branch"],
            "PASSCODE": st.secrets["auth"]["passcode"],
            "KEY": st.secrets["git"]["deploy_key"],
        }
    except Exception:
        st.error("Secrets not found. Please check your Streamlit Cloud secrets.")
        st.stop()

secrets = load_secrets()
GITHUB_REPO = secrets["REPO"]
GITHUB_BRANCH = secrets["BRANCH"]
VEM_PASSCODE = secrets["PASSCODE"]
DEPLOY_KEY = secrets["KEY"]
GIT_SSH_URL = f"git@github.com:{GITHUB_REPO}.git"

# Paths
base_path = Path(".")
EXCEL_FILE_PATH = base_path / "Vehicle_Checkout_List.xlsx"
TYPE_LIST_PATH = base_path / "type_list.txt"
ASSIGNED_TO_LIST_PATH = base_path / "assigned_to_list.txt"
DRIVERS_LIST_PATH = base_path / "authorized_drivers_list.txt"

# --- 2. GIT & SSH AUTHENTICATION ---
def setup_ssh_and_git():
    ssh_dir = Path("~/.ssh").expanduser()
    ssh_dir.mkdir(exist_ok=True)
    (ssh_dir / "github_deploy_key").write_text(DEPLOY_KEY)
    os.chmod(ssh_dir / "github_deploy_key", 0o600)
    
    config_text = f"Host github.com\n  HostName github.com\n  User git\n  IdentityFile {ssh_dir}/github_deploy_key\n  StrictHostKeyChecking no\n"
    (ssh_dir / "config").write_text(config_text)
    
    subprocess.run(["git", "config", "--global", "user.name", "Jacob Shelly"], check=False)
    subprocess.run(["git", "config", "--global", "user.email", "jcs595@nau.edu"], check=False)

def push_changes(commit_message):
    try:
        setup_ssh_and_git()
        subprocess.run(["git", "add", "-A"], check=True)
        # Check if there are changes to commit
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if status.stdout.strip():
            subprocess.run(["git", "commit", "-m", commit_message], check=True)
            # Use SSH URL explicitly to avoid Error 128
            subprocess.run(["git", "push", GIT_SSH_URL, f"HEAD:{GITHUB_BRANCH}"], check=True)
            st.success("Successfully pushed to GitHub!")
    except Exception as e:
        st.error(f"Push failed: {e}")

# --- 3. DATA PROCESSING ---
def set_time_to_2359(dt):
    if pd.isnull(dt): return pd.NaT
    return pd.to_datetime(dt).replace(hour=23, minute=59, second=0)

@st.cache_data
def load_data():
    if not EXCEL_FILE_PATH.exists():
        df = pd.DataFrame(columns=["Unique ID", "Type", "Vehicle #", "Assigned to", "Status", "Checkout Date", "Return Date", "Authorized Drivers", "Notes"])
        df.to_excel(EXCEL_FILE_PATH, index=False, engine='openpyxl')
    
    df = pd.read_excel(EXCEL_FILE_PATH, engine='openpyxl')
    df['Checkout Date'] = pd.to_datetime(df['Checkout Date'])
    df['Return Date'] = pd.to_datetime(df['Return Date']).apply(set_time_to_2359)
    df['Unique ID'] = df.index
    return df

# --- 4. UI & CHARTS ---
st.set_page_config(layout="wide", page_title="SoF Vehicle Assignments")
st.title("SoF Vehicle Assignments")

df = load_data()

# Toggle for Legend
show_legend = st.checkbox("Show Legend", value=False)
view_mode = st.selectbox("View Mode", ["Desktop", "Mobile"])

# Gantt Chart Logic
today = datetime.today().replace(hour=0, minute=0, second=0)
fig = px.timeline(df, x_start="Checkout Date", x_end="Return Date", y="Type", 
                  color="Assigned to", hover_data=["Status", "Notes"])

# Fixing the Syntax error here
unique_types = df['Type'].unique().tolist()
for _, row in df.iterrows():
    if row['Status'] == 'Reserved':
        try:
            y_idx = unique_types.index(row['Type'])
            fig.add_shape(
                type="rect", x0=row['Checkout Date'], x1=row['Return Date'],
                y0=y_idx - 0.4, y1=y_idx + 0.4,
                fillcolor="rgba(255,0,0,0.1)", line=dict(width=0), layer="below"
            )
        except ValueError:
            pass

fig.update_layout(height=800, showlegend=show_legend, xaxis_range=[today - timedelta(days=7), today + timedelta(days=21)])
fig.add_vline(x=today, line_width=2, line_dash="dash", line_color="red")
st.plotly_chart(fig, use_container_width=True)

# --- 5. MANAGEMENT (600-line style) ---
with st.expander("🔧 Manage Entries (VEM Only)"):
    passcode = st.text_input("Passcode", type="password")
    if passcode == VEM_PASSCODE:
        tabs = st.tabs(["➕ Add New", "📝 Edit/Table", "🗑️ Bulk Delete", "👤 Manage Lists"])
        
        with tabs[0]: # ADD NEW
            with st.form("
