import pandas as pd
import plotly.express as px
import streamlit as st
from datetime import datetime
import subprocess
import os
from pathlib import Path
import toml

# --- 1. CONFIGURATION & SECRETS ---
st.set_page_config(layout="wide", page_title="SoF Vehicle Assignments", page_icon="📊")

def load_secrets():
    """Robust secret loading to prevent crashes"""
    secrets_path = Path("secrets.toml")
    if secrets_path.exists():
        secrets = toml.load(secrets_path)
        return secrets["git"]["repo"], secrets["git"]["branch"], secrets["auth"]["passcode"], secrets["git"]["deploy_key"]
    else:
        return st.secrets["git"]["repo"], st.secrets["git"]["branch"], st.secrets["auth"]["passcode"], st.secrets["git"]["deploy_key"]

try:
    GITHUB_REPO, GITHUB_BRANCH, VEM_PASSCODE, DEPLOY_KEY = load_secrets()
except Exception as e:
    st.error("Missing Secrets! Please check your Streamlit Cloud secrets configuration.")
    st.stop()

FILE_PATH = "Vehicle_Checkout_List.xlsx"
GIT_SSH_URL = f"git@github.com:{GITHUB_REPO}.git"

# --- 2. SSH & GIT SETUP ---
def setup_git_ssh():
    subprocess.run(["git", "config", "--global", "user.name", "Jacob Shelly"], check=False)
    subprocess.run(["git", "config", "--global", "user.email", "jcs595@nau.edu"], check=False)
    
    ssh_dir = Path("~/.ssh").expanduser()
    ssh_dir.mkdir(parents=True, exist_ok=True)
    
    key_file = ssh_dir / "github_deploy_key"
    key_file.write_text(DEPLOY_KEY)
    os.chmod(key_file, 0o600)
    
    config_file = ssh_dir / "config"
    config_file.write_text(f"Host github.com\n  HostName github.com\n  User git\n  IdentityFile {key_file}\n  StrictHostKeyChecking no\n")
    os.chmod(config_file, 0o600)

def push_changes_to_github(commit_message="Update vehicle data via Streamlit"):
    """Upgraded X-Ray Push Function to catch silent errors"""
    try:
        setup_git_ssh()
        subprocess.run(["git", "add", "-A"], capture_output=True, text=True)
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        
        if status.stdout.strip():
            commit_res = subprocess.run(["git", "commit", "-m", commit_message], capture_output=True, text=True)
            if commit_res.returncode != 0:
                st.error(f"Commit Failed: {commit_res.stderr}")
                return

            push_res = subprocess.run(["git", "push", "-f", GIT_SSH_URL, f"HEAD:{GITHUB_BRANCH}"], capture_output=True, text=True)
            if push_res.returncode != 0:
                st.error(f"Push Failed! GitHub says:\n{push_res.stderr}")
            else:
                st.success("Successfully pushed changes to GitHub!")
        else:
            st.info("No changes detected to push. (The Excel file might not have saved correctly).")
            
    except Exception as e:
        st.error(f"System Error during push: {e}")

# --- 3. DATA LOADING & HELPERS ---
def load_list(path, default_options=None):
    if default_options is None: default_options = []
    if not os.path.exists(path): return default_options
    with open(path, "r") as f:
        items = [line.strip() for line in f if line.strip()]
        return items if items else default_options

def set_time_to_2359(dt):
    if pd.isnull(dt): return pd.NaT
    return pd.to_datetime(dt).replace(hour=23, minute=59, second=0)

@st.cache_data
def load_data():
    if not os.path.exists(FILE_PATH):
        df = pd.DataFrame(columns=["Unique ID", "Type", "Vehicle #", "Assigned to", "Status", "Checkout Date", "Return Date", "Authorized Drivers", "Notes"])
        df.to_excel(FILE_PATH, index=False, engine="openpyxl")
    df = pd.read_excel(FILE_PATH, engine="openpyxl")
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

if not df.empty:
    fig = px.timeline(
        df, x_start="Checkout Date", x_end="Return Date", y="Type", 
        color="Assigned to", text="Vehicle #",
        hover_data=["Status", "Notes", "Authorized Drivers"],
        category_orders={"Type": load_list("type_list.txt")}
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

    # --- CUSTOM X-AXIS TICK GENERATOR ---
    min_date = df['Checkout Date'].min() - pd.Timedelta(days=30)
    max_date = df['Return Date'].max() + pd.Timedelta(days=90)
    
    tick_vals = []
    tick_text = []
    
    for d in pd.date_range(start=min_date, end=max_date):
        if d.day in [1, 5, 10, 15, 20, 25]:
            tick_vals.append(d)
            # Linux (Streamlit Cloud) uses %-d to remove leading zero from days
            tick_text.append(d.strftime("%b %-d") if d.day == 1 else str(d.day))

    # --- CHART LAYOUT SETTINGS ---
    fig.update_layout(
        height=800, 
        showlegend=show_legend,
        dragmode="pan"
    )
    
    fig.update_yaxes(fixedrange=True) 
    
    fig.update_xaxes(
        tickmode="array",
        tickvals=tick_vals,
        ticktext=tick_text,
        tickangle=0,            # Keeps the text perfectly horizontal
        ticks="outside",        # Shows the major tick marks under the numbers
        minor=dict(
            dtick=86400000.0,   # Exactly 1 day for minor ticks
            ticklen=4,          # Length of the little vertical marks
            tickcolor="gray"
        )
    )
    
    fig.add_vline(x=today, line_width=2, line_dash="dash", line_color="red")
    
    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})
else:
    st.info("No vehicle data found. Please add an entry below.")

# --- 5. MANAGEMENT CONSOLE ---
with st.expander("🔧 VEM Management Console"):
    passcode = st.text_input("Enter Passcode", type="password")
    if passcode == VEM_PASSCODE:
        
        type_list = load_list("type_list.txt", ["Example Truck 1"])
        assigned_list = load_list("assigned_to_list.txt", ["Example Crew A"])
        driver_list = load_list("authorized_drivers_list.txt", ["Example Driver 1"])
        
        tabs = st.tabs(["➕ New Entry", "📝 Edit Table", "🗑️ Bulk Delete", "👤 Manage Lists"])
        
        with tabs[0]: 
            with st.form("new_entry_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    n_type = st.selectbox("Vehicle Type", options=type_list)
                    n_assign = st.selectbox("Assigned To", options=assigned_list)
                    n_drivers = st.multiselect("Authorized Drivers", options=driver_list)
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
                    updated_df = pd.concat([df, new_row], ignore_index=True)
                    updated_df.drop(columns=["Unique ID"], errors='ignore').to_excel(FILE_PATH, index=False, engine="openpyxl")
                    push_changes_to_github(f"Added entry for {n_assign}")
                    st.cache_data.clear()
                    st.rerun()

        with tabs[1]: 
            st.info("💡 Double-click a cell to edit. Use the '+' at the bottom to add new rows quickly.")
            edited_df = st.data_editor(
                df, 
                num_rows="dynamic", 
                key="main_editor",
                column_config={
                    "Type": st.column_config.SelectboxColumn("Type", options=type_list, required=True),
                    "Assigned to": st.column_config.SelectboxColumn("Assigned to", options=assigned_list, required=True),
                    "Status": st.column_config.SelectboxColumn("Status", options=["Confirmed", "Reserved"]),
                    "Checkout Date": st.column_config.DateColumn("Checkout Date"),
                    "Return Date": st.column_config.DateColumn("Return Date")
                }
            )
            if st.button("Save Table Changes"):
                edited_df.drop(columns=["Unique ID"], errors='ignore').to_excel(FILE_PATH, index=False, engine="openpyxl")
                push_changes_to_github("Updated data via interactive editor")
                st.cache_data.clear()
                st.rerun()

        with tabs[2]: 
            st.subheader("Delete Range")
            d_start = st.date_input("Start Date", value=today)
            d_end = st.date_input("End Date", value=today)
            mask = (df["Checkout Date"] >= pd.to_datetime(d_start)) & (df["Return Date"] <= pd.to_datetime(d_end))
            to_delete = df[mask]
            st.write(f"Entries found: {len(to_delete)}")
            st.dataframe(to_delete)
            if st.button("Confirm Bulk Delete"):
                df = df[~mask]
                df.drop(columns=["Unique ID"], errors='ignore').to_excel(FILE_PATH, index=False, engine="openpyxl")
                push_changes_to_github("Bulk deletion performed")
                st.cache_data.clear()
                st.rerun()

        with tabs[3]: 
            list_choice = st.selectbox("Select List", ["Names", "Vehicles", "Drivers"])
            paths = {"Names": "assigned_to_list.txt", "Vehicles": "type_list.txt", "Drivers": "authorized_drivers_list.txt"}
            
            current_items = load_list(paths[list_choice], ["(List is empty)"])
            st.write(f"**Current items in {list_choice}:** {', '.join(current_items)}")
            
            new_item = st.text_input(f"Add new {list_choice}")
            if st.button("Add to List"):
                with open(paths[list_choice], "a") as f:
                    f.write(f"\n{new_item}")
                push_changes_to_github(f"Added {new_item} to {list_choice} list")
                st.cache_data.clear()
                st.rerun()
