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
    # Attempt to load from st.secrets (Streamlit Cloud standard)
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
except Exception as e:
    st.error(f"Secret Error: {e}. Please check your Secrets formatting.")
    st.stop()

# CHANGE HERE: Pointing back to the Excel file
EXCEL_FILE_NAME = "Vehicle_Checkout_List.xlsx" 
base_path = Path(__file__).parent
EXCEL_FILE_PATH = base_path / EXCEL_FILE_NAME
ASSIGNED_TO_LIST_PATH = base_path / "assigned_to_list.txt"
DRIVERS_LIST_PATH = base_path / "authorized_drivers.txt"
REPO_DIR = base_path 

# --- 2. GIT & SSH SETUP ---
def setup_ssh_and_git():
    ssh_dir = Path.home() / ".ssh"
    ssh_dir.mkdir(parents=True, exist_ok=True)
    deploy_key_file = ssh_dir / "id_rsa"
    
    with open(deploy_key_file, "w") as f:
        f.write(DEPLOY_KEY.strip())
    os.chmod(deploy_key_file, 0o600)

    ssh_config = ssh_dir / "config"
    with open(ssh_config, "w") as f:
        f.write("Host github.com\n  StrictHostKeyChecking no\n  IdentityFile ~/.ssh/id_rsa\n")
    
    subprocess.run(["git", "config", "--global", "user.email", "jcs595@nau.edu"], check=True)
    subprocess.run(["git", "config", "--global", "user.name", "Jacob Shelly"], check=True)

def push_changes_to_github():
    try:
        setup_ssh_and_git()
        # Add all relevant files
        subprocess.run(["git", "add", EXCEL_FILE_NAME, "assigned_to_list.txt", "authorized_drivers.txt"], check=True)
        subprocess.run(["git", "commit", "-m", "Update data from Streamlit app"], check=True)
        
        # Push using SSH URL
        remote_url = f"git@github.com:{GITHUB_REPO}.git"
        subprocess.run(["git", "push", remote_url, GITHUB_BRANCH], check=True)
        st.success("Changes successfully pushed to GitHub!")
    except Exception as e:
        st.error(f"Git Push Failed: {e}")

# --- 3. DATA LOADING ---
def load_vehicle_data(file_path):
    if file_path.exists():
        # Changed from read_csv to read_excel
        return pd.read_excel(file_path)
    return pd.DataFrame(columns=["Vehicle", "Assigned To", "Authorized Driver", "Checkout Date", "Return Date"])

# --- 4. MAIN APP LOGIC ---
def main():
    st.title("SoF Vehicle Assignments")
    
    # Check if data exists
    df = load_vehicle_data(EXCEL_FILE_PATH)
    
    # ... (Rest of your UI logic for Gantt chart and Tabs) ...
    # Note: Ensure you use df.to_excel(EXCEL_FILE_PATH, index=False) 
    # when saving inside your management functions!

    st.write("App is now configured for Excel!")

if __name__ == "__main__":
    main()
