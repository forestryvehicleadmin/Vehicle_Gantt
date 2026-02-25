import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime, timedelta
import subprocess
import os
from pathlib import Path

# --- 1. CONFIGURATION ---
st.set_page_config(layout="wide", page_title="SoF Vehicle Assignments", page_icon="📊")

# Pull details from Secrets
GITHUB_REPO = st.secrets["git"]["repo"]
GITHUB_BRANCH = st.secrets["git"]["branch"]
GIT_SSH_URL = f"git@github.com:{GITHUB_REPO}.git"

# Paths for data files
file_path = "Vehicle_Checkout_List.xlsx"
type_list_path = "type_list.txt"
assigned_to_list_path = "assigned_to_list.txt"
authorized_drivers_list_path = "authorized_drivers_list.txt"

# --- 2. GIT & SSH SETUP ---
def setup_git_ssh():
    """Sets up the identity and SSH tunnel for GitHub pushes."""
    subprocess.run(["git", "config", "--global", "user.name", "Jacob Shelly"], check=False)
    subprocess.run(["git", "config", "--global", "user.email", "jcs595@nau.edu"], check=False)
    
    ssh_dir = Path("~/.ssh").expanduser()
    ssh_dir.mkdir(parents=True, exist_ok=True)
    
    key_file = ssh_dir / "github_deploy_key"
    key_file.write_text(st.secrets["git"]["deploy_key"])
    os.chmod(key_file, 0o600)
    
    config_file = ssh_dir / "config"
    config_file.write_text(f"Host github.com\n  HostName github.com\n  User git\n  IdentityFile {key_file}\n  StrictHostKeyChecking no\n")
    os.chmod(config_file, 0o600)

def push_changes_to_github(commit_message="Update from Streamlit"):
    try:
        setup_git_ssh()
        # Stage all updated files (Excel and .txt lists)
        subprocess.run(["git", "add", "-A"], check=True)
        
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if status.stdout.strip():
            subprocess.run(["git", "commit", "-m", commit_message], check=True)
            subprocess.run(["git", "push", "-f", GIT_SSH_URL, f"HEAD:{GITHUB_BRANCH}"], check=True)
            st.success("Changes successfully pushed to GitHub!")
        else:
            st.info("No changes to push.")
    except Exception as e:
        st.error(f"GitHub Sync Error: {e}")

# --- 3. DATA LOADING & HELPERS ---
def set_time_to_2359(dt):
    if pd.isnull(dt): return pd.NaT
    return pd.to_datetime(dt).replace(hour=23, minute=59, second=0)

def load_list(path):
    if not os.path.exists(path): return []
    with open(path, "r") as f:
        return sorted([line.strip() for line in f if line.strip()])

@st.cache_data
def load_data():
    if not os.path.exists(file_path):
        df = pd.DataFrame(columns=["Unique ID", "Type", "Vehicle #", "Assigned to", "Status", "Checkout Date", "Return Date", "Authorized Drivers", "Notes"])
        df.to_excel(file_path, index=False)
    df = pd.read_excel(file_path)
    df['Checkout Date'] = pd.to_datetime(df['Checkout Date'])
    df['Return Date'] = pd.to_datetime(df['Return Date']).apply(set_time_to_2359)
    df['Unique ID'] = df.index
    return df

# --- 4. MAIN UI & GANTT CHART ---
st.title("SoF Vehicle Assignments")
df = load_data()

view_col1, view_col2 = st.columns(2)
with view_col1:
    view_mode = st.selectbox("View Mode", ["Desktop", "Mobile"])
with view_col2:
    show_legend = st.checkbox("Show Legend", value=False)

today = datetime.today().replace(hour=0, minute=0, second=0)

# Create Gantt
fig = px.timeline(
    df, x_start="Checkout Date", x_end="Return Date", y="Type", 
    color="Assigned to", text="Vehicle #",
    hover_data=["Status", "Notes", "Authorized Drivers"],
    category_orders={"Type": load_list(type_list_path)}
)

# Add Reserved Status Shapes
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

# --- 5. MANAGEMENT CONSOLE ---
with st.expander("🔧 VEM Management Console"):
    auth_input = st.text_input("Passcode", type="password")
    if auth_input == st.secrets["auth"]["passcode"]:
        tabs = st.tabs(["➕ New Entry", "📝 Edit Table", "🗑️ Bulk Delete", "👤 Manage Lists"])
        
        with tabs[0]: # New Entry Form
            with st.form("new_entry_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    n_type = st.selectbox("Vehicle Type", options=load_list(type_list_path))
                    n_assign = st.selectbox("Assigned To", options=load_list(assigned_to_list_path))
                    n_drivers = st.multiselect("Authorized Drivers", options=load_list(authorized_drivers_list_path))
                with col2:
                    n_check = st.date_input("Checkout Date")
                    n_ret = st.date_input("Return Date")
                    n_status = st.selectbox("Status", ["Confirmed", "Reserved"])
                n_notes = st.text_area("Notes")
                
                if st.form_submit_button("Add Assignment"):
                    new_row = pd.DataFrame([{
                        "Type": n_type, "Assigned to": n_assign, "Status": n_status,
                        "Checkout Date": pd.to_datetime(n_check), "Return Date": set_time_to_2359(n_ret),
                        "Authorized Drivers": ", ".join(n_drivers), "Notes": n_notes,
                        "Vehicle #": n_type.split("-")[0] if "-" in n_type else "0"
                    }])
                    df = pd.concat([df, new_row], ignore_index=True)
                    df.drop(columns=["Unique ID"]).to_excel(file_path, index=False)
                    push_changes_to_github(f"Added entry for {n_assign}")
                    st.rerun()

        with tabs[1]: # Edit Table
            edited = st.data_editor(df, num_rows="dynamic", key="main_editor")
            if st.button("Save Changes"):
                edited.drop(columns=["Unique ID"]).to_excel(file_path, index=False)
                push_changes_to_github("Updated data via editor")
                st.rerun()

        with tabs[2]: # Bulk Delete
            st.subheader("Delete Range")
            d_start = st.date_input("Start Date", value=today)
            d_end = st.date_input("End Date", value=today)
            mask = (df["Checkout Date"] >= pd.to_datetime(d_start)) & (df["Return Date"] <= pd.to_datetime(d_end))
            to_delete = df[mask]
            st.write(f"Entries found: {len(to_delete)}")
            st.dataframe(to_delete)
            if st.button("Confirm Bulk Delete"):
                df = df[~mask]
                df.drop(columns=["Unique ID"]).to_excel(file_path, index=False)
                push_changes_to_github("Bulk deletion performed")
                st.rerun()

        with tabs[3]: # List Management
            list_choice = st.selectbox("Select List", ["Names", "Vehicles", "Drivers"])
            paths = {"Names": assigned_to_list_path, "Vehicles": type_list_path, "Drivers": authorized_drivers_list_path}
            new_item = st.text_input(f"Add new {list_choice}")
            if st.button("Add to List"):
                with open(paths[list_choice], "a") as f:
                    f.write(f"\n{new_item}")
                push_changes_to_github(f"Added {new_item} to {list_choice} list")
                st.rerun()
