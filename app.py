import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime, timedelta
import subprocess
import os
from pathlib import Path
import shutil

# --- 1. CONFIGURATION & GIT SETUP ---
st.set_page_config(layout="wide", page_title="SoF Vehicle Assignments", page_icon="📊")

# GitHub repository details
GITHUB_REPO = "forestryvehicleadmin/Vehicle_Gantt" 
GITHUB_BRANCH = "master"  
FILE_PATH = "Vehicle_Checkout_List.xlsx"  # Using Excel now
GIT_SSH_URL = f"git@github.com:{GITHUB_REPO}.git"

# Set Git author identity
subprocess.run(["git", "config", "--global", "user.name", "Jacob Shelly"], check=True)
subprocess.run(["git", "config", "--global", "user.email", "jcs595@nau.edu"], check=True)

# Path for the SSH private key and git configuration
DEPLOY_KEY_PATH = Path("~/.ssh/github_deploy_key").expanduser()
SSH_CONFIG_PATH = Path("~/.ssh/config").expanduser()

# Ensure private key is available for SSH
if "DEPLOY_KEY" in st.secrets:
    DEPLOY_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DEPLOY_KEY_PATH, "w") as f:
        f.write(st.secrets["DEPLOY_KEY"])
    os.chmod(DEPLOY_KEY_PATH, 0o600) 

    with open(SSH_CONFIG_PATH, "w") as f:
        f.write(f"""
Host github.com
    HostName github.com
    User git
    IdentityFile {DEPLOY_KEY_PATH}
    StrictHostKeyChecking no
        """)
    os.chmod(SSH_CONFIG_PATH, 0o600) 
    
    # Force use of SSH URL to ensure the Deploy Key is used
    subprocess.run(["git", "remote", "set-url", "origin", GIT_SSH_URL], check=False)

def push_changes_to_github():
    """Push changes to GitHub using the SSH Key."""
    try:
        # Check for local changes
        result = subprocess.run(["git", "status", "--porcelain"], stdout=subprocess.PIPE, text=True)
        if result.stdout.strip():
            subprocess.run(["git", "stash", "--include-untracked"], check=True)

        # Pull latest changes to avoid conflicts
        subprocess.run(["git", "pull", "origin", GITHUB_BRANCH, "--rebase"], check=True)

        # Restore stashed changes
        if result.stdout.strip():
            subprocess.run(["git", "stash", "pop"], check=True)

        # Add and Commit
        subprocess.run(["git", "add", "-A"], check=True)
        diff_result = subprocess.run(["git", "diff", "--cached"], stdout=subprocess.PIPE, text=True)
        if not diff_result.stdout.strip():
            st.info("No changes detected to commit.")
            return

        subprocess.run(["git", "commit", "-m", "Update Excel and TXT files from Streamlit app"], check=True)

        # Explicit Push via SSH URL to solve Permission Error 128
        subprocess.run(["git", "push", GIT_SSH_URL, f"HEAD:{GITHUB_BRANCH}"], check=True)
        st.success("Changes successfully pushed to GitHub!")
    except subprocess.CalledProcessError as e:
        st.error(f"Failed to push changes: {e}")
    finally:
        subprocess.run(["git", "stash", "drop"], check=False, stderr=subprocess.DEVNULL)

# --- 2. DATA LOADING ---
if "popup_shown" not in st.session_state:
    st.session_state.popup_shown = False 

if not st.session_state.popup_shown:
    with st.expander("🚀 Welcome to SoF Vehicle Assignments! (Click to Dismiss)"):
        st.markdown("""
        ## Key Tips for Using the App:
        - **Legend Toggle**: Use the "Show Legend" checkbox above the chart.
        - **Navigate chart**: Tools are in the popup at the top right of the graph. 
        - **Phone Use**: Drag finger along numbers on side of chart to scroll. 
        """)
        st.button("Close Tips", on_click=lambda: setattr(st.session_state, "popup_shown", True))

st.title("SoF Vehicle Assignments")

try:
    # Load using Excel engine
    df = pd.read_excel(FILE_PATH, engine="openpyxl")
    df['Checkout Date'] = pd.to_datetime(df['Checkout Date'])
    df['Return Date'] = pd.to_datetime(df['Return Date'])
    df["Unique ID"] = df.index  
    df['Notes'] = df['Notes'].astype(str)
    df = df.sort_values(by="Type", ascending=True)
except Exception as e:
    st.error(f"Error loading Excel file: {e}")
    st.stop()

# --- 3. GANTT CHART RENDERING ---
show_legend = st.checkbox("Show Legend", value=False)

today = datetime.today()
start_range = today - timedelta(weeks=2)  
end_range = today + timedelta(weeks=4)    
week_range = end_range + timedelta(weeks=10)   

fig = px.timeline(
    df,
    x_start="Checkout Date",
    x_end="Return Date",
    y="Type",
    color="Assigned to",
    title="Vehicle Assignments",
    hover_data=["Unique ID", "Assigned to", "Status", "Type", "Checkout Date", "Return Date"]
)

unique_types = df['Type'].unique()
fig.update_yaxes(categoryorder="array", categoryarray=unique_types)

# Add overlays for Reserved status
for _, row in df.iterrows():
    if row['Status'] == 'Reserved':
        fig.add_shape(
            type="rect",
            x0=row['Checkout Date'], x1=row['Return Date'],
            y0=unique_types.tolist().index(row['Type']) - 0.4,
            y1=unique_types.tolist().index(row['Type']) + 0.4,
            xref="x", yref="y",
            fillcolor="rgba(255,0,0,0.1)", 
            line=dict(width=0), layer="below"
        )

# Grid lines and Today marker
fig.add_shape(
    type
