import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime, timedelta
import subprocess
import os
from pathlib import Path
import toml

# --- 1. CONFIGURATION & SETUP ---
st.set_page_config(layout="wide", page_title="SoF Vehicle Assignments", page_icon="📊")

# Load Secrets (Handle both local toml and Streamlit Cloud)
def load_config():
    # Attempt to load local secrets first
    secrets_path = Path(".streamlit/secrets.toml")
    try:
        if secrets_path.exists():
            data = toml.load(secrets_path)
            # Check if keys exist in local file
            if "git" in data and "auth" in data:
                return data["git"], data["auth"]
        
        # Fallback to Streamlit Cloud Secrets
        if "git" in st.secrets and "auth" in st.secrets:
            return st.secrets["git"], st.secrets["auth"]
            
        st.error("Secrets not found! Please check .streamlit/secrets.toml or Streamlit Cloud Secrets.")
        st.stop()
    except Exception as e:
        st.error(f"Configuration Error: {e}")
        st.stop()

git_conf, auth_conf = load_config()

# Constants
GITHUB_REPO = git_conf["repo"]
GITHUB_BRANCH = git_conf["branch"]
DEPLOY_KEY = git_conf["deploy_key"]
VEM_PASSCODE = auth_conf["passcode"]
GIT_SSH_URL = f"git@github.com:{GITHUB_REPO}.git"

# Paths
REPO_DIR = Path("repo")
# Check if we are in a cloned repo sub-folder or root
BASE_PATH = REPO_DIR if REPO_DIR.is_dir() else Path(".")
DATA_FILE = BASE_PATH / "Vehicle_Checkout_List.csv"
TYPE_FILE = BASE_PATH / "type_list.txt"
ASSIGNED_FILE = BASE_PATH / "assigned_to_list.txt"
DRIVERS_FILE = BASE_PATH / "authorized_drivers_list.txt"

# --- 2. GIT & SSH OPERATIONS ---
def setup_ssh():
    """Sets up SSH key for GitHub authentication."""
    ssh_dir = Path.home() / ".ssh"
    ssh_dir.mkdir(parents=True, exist_ok=True)
    
    key_path = ssh_dir / "id_rsa_deploy"
    config_path = ssh_dir / "config"
    
    # Write private key
    if not key_path.exists():
        with open(key_path, "w") as f:
            f.write(DEPLOY_KEY.strip() + "\n")
        os.chmod(key_path, 0o600)

    # Configure SSH to use this key for github.com
    ssh_config = f"""
    Host github.com
        HostName github.com
        User git
        IdentityFile {key_path}
        StrictHostKeyChecking no
    """
    with open(config_path, "w") as f:
        f.write(ssh_config)
    os.chmod(config_path, 0o600)

def git_push(message):
    """Commits and pushes changes to GitHub."""
    try:
        # Configure User
        subprocess.run(["git", "config", "--global", "user.name", "VehicleAdmin"], check=True)
        subprocess.run(["git", "config", "--global", "user.email", "admin@example.com"], check=True)
        
        # Add, Commit, Push
        subprocess.run(["git", "add", "."], cwd=BASE_PATH, check=True)
        # Check if there are changes
        status = subprocess.run(["git", "status", "--porcelain"], cwd=BASE_PATH, capture_output=True, text=True)
        if not status.stdout:
            return # No changes
            
        subprocess.run(["git", "commit", "-m", message], cwd=BASE_PATH, check=True)
        subprocess.run(["git", "push", GIT_SSH_URL, f"HEAD:{GITHUB_BRANCH}"], cwd=BASE_PATH, check=True)
        st.toast(f"✅ Success: {message}", icon="🚀")
    except subprocess.CalledProcessError as e:
        st.error(f"Git Operation Failed: {e}")

# --- 3. DATA HANDLING ---
def init_files():
    """Creates necessary files if they don't exist."""
    if not DATA_FILE.exists():
        # Create empty CSV with correct headers
        df = pd.DataFrame(columns=[
            "Unique ID", "Type", "Vehicle #", "Assigned to", "Status", 
            "Checkout Date", "Return Date", "Authorized Drivers", "Notes"
        ])
        df.to_csv(DATA_FILE, index=False)
    
    # Create empty text lists if they don't exist
    for f in [TYPE_FILE, ASSIGNED_FILE, DRIVERS_FILE]:
        if not f.exists():
            f.touch()

@st.cache_data(ttl=60)
def load_data():
    """Loads CSV data."""
    if not DATA_FILE.exists():
        init_files()
    
    try:
        df = pd.read_csv(DATA_FILE)
        # Fix Dates
        df['Checkout Date'] = pd.to_datetime(df['Checkout Date'])
        df['Return Date'] = pd.to_datetime(df['Return Date']).apply(
            lambda x: x.replace(hour=23, minute=59) if pd.notnull(x) else x
        )
        # Fix Missing Values
        df['Notes'] = df['Notes'].fillna('')
        df['Authorized Drivers'] = df['Authorized Drivers'].fillna('')
        
        # Ensure Unique ID exists
        if "Unique ID" not in df.columns:
            df["Unique ID"] = df.index
            
        return df.sort_values("Checkout Date")
    except Exception as e:
        st.error(f"Data Load Error: {e}")
        return pd.DataFrame()

def load_list_file(filepath):
    """Reads a text file into a list of strings."""
    if filepath.exists():
        with open(filepath, "r") as f:
            return sorted([line.strip() for line in f.readlines() if line.strip()])
    return []

def save_list_file(filepath, content_str):
    """Saves a string (from text area) to a file."""
    # Split by newline, clean, remove duplicates, sort
    lines = sorted(list(set([l.strip() for l in content_str.split('\n') if l.strip()])))
    with open(filepath, "w") as f:
        f.write("\n".join(lines))

# --- 4. UI: GANTT CHART ---
def plot_gantt(df):
    if df.empty:
        st.info("No data available. Go to 'Manage Entries' to add one.")
        return

    # Dynamic Zoom
    today = datetime.now()
    start_view = today - timedelta(days=7)
    end_view = today + timedelta(weeks=4)

    fig = px.timeline(
        df, 
        x_start="Checkout Date", 
        x_end="Return Date", 
        y="Type", 
        color="Assigned to",
        title="Vehicle Assignments",
        hover_data=["Vehicle #", "Status", "Notes", "Authorized Drivers"]
    )

    # Styling
    fig.update_yaxes(categoryorder="category ascending", title=None)
    fig.update_layout(
        xaxis_range=[start_view, end_view],
        height=700,
        margin=dict(l=10, r=10, t=40, b=10),
        legend_title_text="User"
    )
    
    # "Today" Line
    fig.add_vline(x=today, line_width=2, line_dash="dash", line_color="red")
    fig.add_annotation(x=today, y=1.02, yref="paper", text="Today", showarrow=False, font=dict(color="red"))

    st.plotly_chart(fig, use_container_width=True)

# --- 5. MAIN APP ---
def main():
    st.title("SoF Vehicle Scheduler")
    
    # Initialize SSH on first run
    if "ssh_setup" not in st.session_state:
        setup_ssh()
        st.session_state.ssh_setup = True

    df = load_data()
    
    # Display Chart
    with st.expander("📊 View Schedule", expanded=True):
        plot_gantt(df)
        if not df.empty:
            st.dataframe(df, hide_index=True)

    # --- MANAGEMENT SECTION ---
    st.divider()
    st.header("Manage Entries")
    
    # Simple Authentication
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        pwd = st.text_input("Enter Admin Passcode", type="password")
        if pwd == VEM_PASSCODE:
            st.session_state.authenticated = True
            st.rerun()
        elif pwd:
            st.error("Invalid Passcode")
    
    if st.session_state.authenticated:
        if st.button("🔒 Logout"):
            st.session_state.authenticated = False
            st.rerun()

        # Load reference lists
        type_list = load_list_file(TYPE_FILE)
        assigned_list = load_list_file(ASSIGNED_FILE)
        drivers_list = load_list_file(DRIVERS_FILE)

        tab1, tab2, tab3, tab4, tab5 = st.tabs(["➕ New Entry", "📅 Bulk Add", "✏️ Edit", "🗑️ Delete", "📝 Manage Lists"])

        # --- TAB 1: NEW ENTRY ---
        with tab1:
            with st.form("new_entry"):
                c1, c2 = st.columns(2)
                veh_type = c1.selectbox("Vehicle Type", type_list)
                assignee = c2.selectbox("Assigned To", assigned_list)
                
                c3, c4 = st.columns(2)
                start = c3.date_input("Checkout", datetime.today())
                end = c4.date_input("Return", datetime.today() + timedelta(days=1))
                
                status = st.selectbox("Status", ["Confirmed", "Reserved"])
                drivers = st.multiselect("Drivers", drivers_list)
                notes = st.text_area("Notes")

                if st.form_submit_button("Submit"):
                    new_row = {
                        "Unique ID": int(datetime.now().timestamp()), # Simple Unique ID
                        "Type": veh_type,
                        "Vehicle #": veh_type.split('-')[0].strip() if '-' in veh_type else "N/A",
                        "Assigned to": assignee,
                        "Status": status,
                        "Checkout Date": pd.Timestamp(start),
                        "Return Date": pd.Timestamp(end).replace(hour=23, minute=59),
                        "Authorized Drivers": ", ".join(drivers),
                        "Notes": notes
                    }
                    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                    df.to_csv(DATA_FILE, index=False)
                    git_push(f"Added entry for {assignee}")
                    st.cache_data.clear()
                    st.rerun()

        # --- TAB 2: BULK ADD ---
        with tab2:
            st.write("Add recurring entries (e.g., every Monday and Wednesday).")
            with st.form("bulk_entry"):
                b_type = st.selectbox("Vehicle", type_list, key="b_type")
                b_user = st.selectbox("User", assigned_list, key="b_user")
                b_start = st.date_input("Range Start", datetime.today())
                b_end = st.date_input("Range End", datetime.today() + timedelta(days=30))
                weekdays = st.multiselect("Days of Week", ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
                
                if st.form_submit_button("Generate Bulk Entries"):
                    mapping = {"Mon":0, "Tue":1, "Wed":2, "Thu":3, "Fri":4, "Sat":5, "Sun":6}
                    target_days = [mapping[d] for d in weekdays]
                    
                    dates = pd.date_range(b_start, b_end)
                    new_rows = []
                    
                    for d in dates:
                        if d.weekday() in target_days:
                            new_rows.append({
                                "Unique ID": int(d.timestamp()),
                                "Type": b_type,
                                "Vehicle #": b_type.split('-')[0].strip() if '-' in b_type else "N/A",
                                "Assigned to": b_user,
                                "Status": "Confirmed",
                                "Checkout Date": d,
                                "Return Date": d.replace(hour=23, minute=59),
                                "Authorized Drivers": "",
                                "Notes": "Bulk Entry"
                            })
                    
                    if new_rows:
                        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
                        df.to_csv(DATA_FILE, index=False)
                        git_push(f"Bulk added {len(new_rows)} entries")
                        st.cache_data.clear()
                        st.rerun()

        # --- TAB 3: EDIT ---
        with tab3:
            # Create a label for the dropdown
            def fmt(x):
                r = df[df["Unique ID"] == x].iloc[0]
                return f"{r['Checkout Date'].strftime('%m/%d')} | {r['Assigned to']} | {r['Type']}"
            
            # Safe Selectbox
            unique_ids = df["Unique ID"].tolist() if not df.empty else []
            edit_id = st.selectbox("Select Entry", unique_ids, format_func=fmt if unique_ids else str)
            
            if edit_id:
                row = df[df["Unique ID"] == edit_id].iloc[0]
                with st.form("edit_form"):
                    e_user = st.selectbox("Assigned To", assigned_list, index=assigned_list.index(row["Assigned to"]) if row["Assigned to"] in assigned_list else 0)
                    e_notes = st.text_area("Notes", value=row["Notes"])
                    
                    if st.form_submit_button("Update Entry"):
                        df.loc[df["Unique ID"] == edit_id, "Assigned to"] = e_user
                        df.loc[df["Unique ID"] == edit_id, "Notes"] = e_notes
                        df.to_csv(DATA_FILE, index=False)
                        git_push(f"Edited ID {edit_id}")
                        st.cache_data.clear()
                        st.rerun()
            else:
                st.info("No entries to edit.")

        # --- TAB 4: DELETE ---
        with tab4:
            # Safe Selectbox
            unique_ids = df["Unique ID"].tolist() if not df.empty else []
            del_id = st.selectbox("Select Entry to Delete", unique_ids, format_func=fmt if unique_ids else str, key="del_sel")
            
            if del_id:
                if st.button("❌ Confirm Delete", type="primary"):
                    df = df[df["Unique ID"] != del_id]
                    df.to_csv(DATA_FILE, index=False)
                    git_push(f"Deleted ID {del_id}")
                    st.cache_data.clear()
                    st.rerun()
            else:
                st.info("No entries to delete.")

        # --- TAB 5: MANAGE LISTS ---
        with tab5:
            col_a, col_b, col_c = st.columns(3)
            
            with col_a:
                st.subheader("Types")
                curr_types = "\n".join(type_list)
                new_types = st.text_area("Edit Types", curr_types, height=300)
                if st.button("Save Types"):
                    save_list_file(TYPE_FILE, new_types)
                    git_push("Updated Type List")
                    st.rerun()
            
            with col_b:
                st.subheader("People")
                curr_ppl = "\n".join(assigned_list)
                new_ppl = st.text_area("Edit People", curr_ppl, height=300)
                if st.button("Save People"):
                    save_list_file(ASSIGNED_FILE, new_ppl)
                    git_push("Updated People List")
                    st.rerun()

            with col_c:
                st.subheader("Drivers")
                curr_drv = "\n".join(drivers_list)
                new_drv = st.text_area("Edit Drivers", curr_drv, height=300)
                if st.button("Save Drivers"):
                    save_list_file(DRIVERS_FILE, new_drv)
                    git_push("Updated Drivers List")
                    st.rerun()

if __name__ == "__main__":
    main()
