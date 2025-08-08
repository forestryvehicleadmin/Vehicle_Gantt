import pandas as pd
import plotly.express as px
import streamlit as st
from datetime import datetime, timedelta
import time
import subprocess
import os
from pathlib import Path
import hashlib

# Set the app to wide mode
st.set_page_config(layout="wide", page_title="SoF Vehicle Assignments", page_icon="📊")

# GitHub repository details
GITHUB_REPO = "forestryvehicleadmin/Vehicle_Gantt"
GITHUB_BRANCH = "master"
FILE_PATH = "Vehicle_Checkout_List.csv"    # <-- switched to CSV
REPO_DIR = Path("repo")

# Set Git author identity
subprocess.run(["git", "config", "--global", "user.name", "forestryvehicleadmin"], check=True)
subprocess.run(["git", "config", "--global", "user.email", "forestryvehicleadmin@nau.edu"], check=True)

# Path for the SSH private key and git configuration
DEPLOY_KEY_PATH = Path("~/.ssh/github_deploy_key").expanduser()
SSH_CONFIG_PATH = Path("~/.ssh/config").expanduser()

# Ensure private key is available for SSH
if "DEPLOY_KEY" in st.secrets:
    DEPLOY_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DEPLOY_KEY_PATH, "w") as f:
        f.write(st.secrets["DEPLOY_KEY"])
    os.chmod(DEPLOY_KEY_PATH, 0o600)  # Restrict permissions

    # Configure SSH for GitHub
    with open(SSH_CONFIG_PATH, "w") as f:
        f.write(f"""
        Host github.com
            HostName github.com
            User git
            IdentityFile {DEPLOY_KEY_PATH}
            StrictHostKeyChecking no
        """)
    os.chmod(SSH_CONFIG_PATH, 0o600)  # Restrict permissions

# Define repository details
REPO_DIR = Path("repo")  # Replace with your repository directory
SSH_REMOTE_NAME = "ssh-origin"
SSH_REMOTE_URL = "git@github.com:forestryvehicleadmin/Vehicle_Gantt.git"
# Check if the SSH remote already exists
try:
    existing_remotes = subprocess.run(
        ["git", "remote", "-v"],
        cwd=REPO_DIR,
        stdout=subprocess.PIPE,
        text=True,
        check=True
    ).stdout

    # Add the SSH remote only if it doesn't exist
    if SSH_REMOTE_NAME not in existing_remotes:
        subprocess.run(
            ["git", "remote", "add", SSH_REMOTE_NAME, SSH_REMOTE_URL],
            cwd=REPO_DIR,
            check=True
        )
    else:
        print(f"Remote '{SSH_REMOTE_NAME}' already exists. Skipping addition.")
except subprocess.CalledProcessError as e:
    print(f"Error checking or adding remote: {e}")


def clone_repo_if_needed():
    """Clone the repository if it doesn't already exist."""
    if not REPO_DIR.exists():
        st.write("Cloning the repository...")
        try:
            subprocess.run(["git", "clone", f"git@github.com:{GITHUB_REPO}.git", REPO_DIR.name], check=True)
        except subprocess.CalledProcessError as e:
            st.error(f"Failed to clone repository: {e}")
            st.stop()
    else:
        st.write("Repository already exists locally.")

def push_changes_to_github():
    """Push changes to GitHub."""
    #st.write("Pushing changes to GitHub...")
    try:
        # Check for unstaged changes
        result = subprocess.run(["git", "status", "--porcelain"], stdout=subprocess.PIPE)
        if result.stdout.strip():
            #st.warning("Unstaged changes detected. Stashing them temporarily.")
            # Stash unstaged changes
            subprocess.run(["git", "stash", "--include-untracked"], check=True)

        # Pull latest changes to avoid conflicts
        subprocess.run(["git", "pull", "ssh-origin", GITHUB_BRANCH, "--rebase"], check=True)

        # Restore stashed changes
        if result.stdout.strip():
            #st.info("Restoring stashed changes...")
            subprocess.run(["git", "stash", "pop"], check=True)

        # Add all changes to the Git index
        subprocess.run(["git", "add", "-A"], check=True)

        # Check for changes in the index
        diff_result = subprocess.run(["git", "diff", "--cached"], stdout=subprocess.PIPE)
        if not diff_result.stdout.strip():
            st.info("No changes detected. Nothing to commit.")
            return
        subprocess.run(["git", "commit", "-m", "Update CSV and TXT files from Streamlit app"], check=True)
        subprocess.run(["git", "push", "ssh-origin", GITHUB_BRANCH], check=True)

        st.success("Changes successfully pushed to GitHub!")
    except subprocess.CalledProcessError as e:
        st.error(f"Failed to push changes: {e}")
    finally:
        # Optional cleanup of stash in case of errors
        subprocess.run(["git", "stash", "drop"], check=False, stderr=subprocess.DEVNULL)
# Path to the Excel file
file_path = r"Vehicle_Checkout_List.xlsx"

def hash_file_contents(file_path):
    """Returns a hash of the file contents to detect changes."""
    with open(file_path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()

# Check if the popup has been displayed already
if "popup_shown" not in st.session_state:
    st.session_state.popup_shown = False  # Initialize the state

# Display the popup if it hasn't been shown yet
if not st.session_state.popup_shown:
    with st.expander("🚀 Welcome to SoF Vehicle Assignments! (Click to Dismiss)"):
        st.markdown("""
        ## Key Tips for Using the App:
        - **Legend Toggle**: Use the "Show Legend" checkbox above the chart to toggle the legend visibility.
        - **Navigate chart**: Tools for navigating schedule are in pop up to top right of graph. 
        - **Phone Use**: Drag finger along numbers on side of chart to scroll. 
                
        """)
        st.button("Close Tips", on_click=lambda: setattr(st.session_state, "popup_shown", True))

# Streamlit app
st.title("SoF Vehicle Assignments")

view_mode = st.selectbox("View Mode", ["Desktop", "Mobile"], index=0)

# Load the data
try:
    df = pd.read_csv(
        FILE_PATH,
        encoding="utf-8",
        parse_dates=["Checkout Date", "Return Date"]
    )
    df["Checkout Date"] = df["Checkout Date"].dt.normalize()
    df["Return Date"]   = df["Return Date"].dt.normalize()
    df = df.sort_values(by="Type").reset_index(drop=True)
    df["Unique ID"] = df.index
    df["Notes"]     = df["Notes"].astype(str)
except Exception as e:
    st.error(f"Error loading CSV file: {e}")
    st.stop()

# Full-screen Gantt chart
#st.title("Interactive Vehicle Assignment Gantt Chart")
st.markdown("###")

# Add a button to toggle the legend
show_legend = st.checkbox("Show Legend", value=False)

#@st.cache_data(show_spinner="Generating Gantt chart...")
def generate_gantt_chart(df, view_mode, show_legend):
    time.sleep(1)
    dfc = df.copy()
    today = datetime.today()
    start_range = today - timedelta(weeks=2)
    end_range = today + timedelta(weeks=4)
    week_range = end_range + timedelta(weeks=10)

    xaxis_range = (
        [today - timedelta(days=2), today + timedelta(days=5)]
        if view_mode == "Mobile"
        else [start_range, end_range]
    )
    dfc["Bar Label"] = dfc["Vehicle #"].astype(str) + " - " + dfc["Assigned to"]
    colors = px.colors.qualitative.Safe
    assigned = dfc["Assigned to"].unique()
    cmap = {a: colors[i % len(colors)] for i, a in enumerate(assigned)}
    fig = px.timeline(
        dfc,
        x_start="Checkout Date",
        x_end="Return Date",
        y="Type",
        color="Assigned to",
        color_discrete_map=cmap,
        title="Vehicle Assignments",
        hover_data=["Unique ID", "Assigned to", "Status", "Type", "Checkout Date", "Return Date", "Authorized Drivers"],
        text="Bar Label"
    )
    fig.update_traces(textposition="inside", insidetextanchor="start")
    types = dfc["Type"].unique()
    fig.update_yaxes(categoryorder="array", categoryarray=types)
    for _, row in dfc.iterrows():
        if row["Status"] == "Reserved":
            idx = list(types).index(row["Type"])
            fig.add_shape(
                type="rect",
                x0=row["Checkout Date"], x1=row["Return Date"],
                y0=idx-0.4, y1=idx+0.4,
                fillcolor="rgba(255,0,0,0.1)", line_width=0, layer="below"
            )
    # Highlight today
    fig.add_shape(
        type="rect",
        x0=today.replace(hour=0,minute=0,second=0),
        x1=today.replace(hour=23,minute=59,second=59),
        y0=0, y1=1,
        xref="x", yref="paper",
        fillcolor="rgba(255, 0, 0, 0.1)", line_width=0, layer="below"
    )
    fig.update_layout(
        height=800, margin=dict(l=0,r=0,t=40,b=0),
        showlegend=show_legend, xaxis_range=xaxis_range
    )

    tick_dates = pd.date_range(start=start_range, end=end_range, freq="D")
    tick_labels = [d.strftime("%a")[0] + "<br>" + d.strftime("%d/%m") for d in tick_dates]
    fig.update_xaxes(
        tickmode="array",
        tickvals=tick_dates,
        ticktext=tick_labels,
        tickangle=0,
        tickfont=dict(size=10),
    )

    return fig

file_hash = hash_file_contents(file_path)

# Display the Gantt chart full screen
fig = generate_gantt_chart(df, view_mode, show_legend)
st.plotly_chart(fig, use_container_width=True)

def load_type_list(path):
    try:
        with open(path) as f:
            return "\n".join(l.strip() for l in f if l.strip())
    except FileNotFoundError:
        return "File not found."

# Display the vehicle type list in a readable format
st.subheader("Vehicle Type List")
st.markdown(f"```\n{load_type_list('type_list.txt')}\n```")


# Add a dropdown to display the DataFrame
with st.expander("View and Filter Data Table"):
    cols = st.multiselect("Select Columns:", df.columns.tolist(), default=df.columns.tolist())
    st.dataframe(df[cols])

# Lookup lists
def _load_list(path):
    try:
        return [l.strip() for l in open(path) if l.strip()]
    except FileNotFoundError:
        return []

@st.cache_data
def get_type_list():
    return _load_list("type_list.txt")
@st.cache_data
def get_assigned_to_list():
    return _load_list("assigned_to_list.txt")
@st.cache_data
def get_drivers_list():
    return _load_list("authorized_drivers_list.txt")

# Rewrite assigned_to_list if changed
with open("assigned_to_list.txt","w") as f:
    for name in sorted(df["Assigned to"].unique()):
        f.write(f"{name}\n")
# invalidate that cache so next call re-reads the file
get_assigned_to_list.clear()

# Manage entries
with st.expander("🔧 Manage Entries (VEM use only)"):
    pwd = st.text_input("Enter the 4-digit passcode:", type="password")
    if pwd != "1234":
        st.error("Incorrect passcode. Access denied.")
    else:
        st.success("Access granted!")

        # Initialize pending actions if not present
        if "pending_actions" not in st.session_state:
            st.session_state.pending_actions = []

        # Begin batched form
        with st.form("manage_entries"):
            # 1) Create New Entry
            types = get_type_list()
            assigned = get_assigned_to_list()
            drivers = get_drivers_list()
            new = {
                "Assigned to": st.selectbox("Assigned to:", [""]+assigned),
                "Type": st.selectbox("Type (Vehicle):", [""]+types),
                "Status": st.selectbox("Status:", ["Confirmed","Reserved"]),
                "Authorized Drivers": st.multiselect("Authorized Drivers:", drivers)
            }
            # Vehicle # and dates/others
            try:
                new["Vehicle #"] = int(new["Type"].split("-")[0].strip()) if new["Type"] else None
            except:
                st.error("Type must start with a numeric code.")
            for col in [c for c in df.columns if c not in ["Unique ID","Assigned to","Type","Vehicle #","Status","Authorized Drivers"]]:
                if pd.api.types.is_datetime64_any_dtype(df[col]):
                    d = st.date_input(col+":", value=datetime.today())
                    new[col] = datetime.combine(d, datetime.max.time() if "return" in col.lower() else datetime.min.time())
                elif pd.api.types.is_numeric_dtype(df[col]):
                    new[col] = st.number_input(col+":", value=0)
                else:
                    new[col] = st.text_input(col+":")

            st.markdown("---")
            # 2) Edit Existing Entry
            selected = st.selectbox(
                "Select entry to edit:",
                options=[None]+df["Unique ID"].tolist(),
                format_func=lambda x: "Select…" if x is None else
                    f"{df.loc[df['Unique ID']==x,'Vehicle #'].iloc[0]}, "
                    f"{df.loc[df['Unique ID']==x,'Assigned to'].iloc[0]}, "
                    f"({df.loc[df['Unique ID']==x,'Checkout Date'].iloc[0].date()}→"
                    f"{df.loc[df['Unique ID']==x,'Return Date'].iloc[0].date()})"
            )
            edits = {}
            if selected is not None:
                row = df.loc[df["Unique ID"]==selected].iloc[0]
                st.write(row)

                for col in df.columns:
                    key = f"edit_{col}_{selected}"
                    val = row[col]
                    if col == "Assigned to":
                        edits[col] = st.selectbox(col+":", assigned, index=assigned.index(val), key=key)
                    elif col == "Type":
                        edits[col] = st.selectbox(col+":", types, index=types.index(val), key=key)
                    elif col == "Status":
                        edits[col] = st.selectbox(col+":", ["Confirmed","Reserved"], index=["Confirmed","Reserved"].index(val), key=key)
                    elif col == "Authorized Drivers":
                        edits[col] = st.multiselect(col+":", drivers, default=(val or "").split(", "), key=key)
                    elif pd.api.types.is_datetime64_any_dtype(df[col]):
                        d = st.date_input(col+":", value=val.date(), key=key)
                        edits[col] = datetime.combine(d, datetime.max.time() if "return" in col.lower() else datetime.min.time())
                    elif pd.api.types.is_numeric_dtype(df[col]):
                        edits[col] = st.number_input(col+":", value=val or 0, key=key)
                    else:
                        edits[col] = st.text_input(col+":", value=val or "", key=key)

            st.markdown("---")
            # 3) Delete Entry
            delete_id = st.selectbox(
                "Select entry to delete:",
                options=[None]+df["Unique ID"].tolist(),
                format_func=lambda x: "Select..." if x is None else
                    f"{df.loc[df['Unique ID']==x,'Vehicle #'].iloc[0]}, "
                    f"{df.loc[df['Unique ID']==x,'Assigned to'].iloc[0]}, "
                    f"({df.loc[df['Unique ID']==x,'Checkout Date'].iloc[0].date()}→"
                    f"{df.loc[df['Unique ID']==x,'Return Date'].iloc[0].date()})"
            )

            # Confirm checkbox
            confirm_delete = st.checkbox("Confirm deletion of selected entry")

            st.markdown("---")
            st.subheader("4. Bulk Delete by Date Range")
            start_dt = st.date_input("Start Date for bulk delete:", value=None)
            end_dt   = st.date_input("End Date for bulk delete:", value=None)
            confirm_bulk = st.checkbox("Confirm bulk deletion")

            # FINAL SUBMIT
            submitted = st.form_submit_button("Submit Changes")

        # ─────────────────────────────────────────────────────────────────────────────
        # INLINE EDITOR WITH FILTERS (outside any st.form)
        # ─────────────────────────────────────────────────────────────────────────────
        with st.expander("🔄 Inline Table Editor"):
            st.subheader("Filter & Edit Entries Inline")

            # 1) FILTER CONTROLS
            type_opts = get_type_list()
            assigned_opts = get_assigned_to_list()
            status_opts = ["Confirmed","Reserved"]
            cols = st.columns(3)
            with cols[0]:
                filt_t = st.multiselect("Filter by Type", options=type_opts, default=type_opts)
            with cols[1]:
                filt_a = st.multiselect("Filter by Assigned to", options=assigned_opts, default=assigned_opts)
            with cols[2]:
                filt_s = st.multiselect("Filter by Status", options=status_opts, default=status_opts)
            mask = df["Type"].isin(filt_t) & df["Assigned to"].isin(filt_a) & df["Status"].isin(filt_s)
            df_f = df[mask].copy()
            st.markdown(f"Showing {len(df_f)}/{len(df)} rows.")
            edited = st.data_editor(df_f, key="edit_table", use_container_width=True)
            if st.button("Save Inline Edits"):
                for _, r in edited.iterrows():
                    uid = r["Unique ID"]
                    if uid in df.index:
                        df.loc[uid, :] = r
                df.reset_index(drop=True, inplace=True)
                df["Unique ID"] = df.index
                df.to_csv(FILE_PATH, index=False)
                st.success("Inline edits written to CSV.")
                with st.spinner("Pushing inline edits to GitHub..."):
                    push_changes_to_github()

        # AFTER form submit: process all pending actions
        if submitted:
            with st.spinner("Applying your changes…"):
                # 1) Create
                if new["Assigned to"] and new["Type"] and new["Vehicle #"] is not None:
                    nr = new.copy()
                    nr["Authorized Drivers"] = ", ".join(nr["Authorized Drivers"])
                    df.loc[len(df)] = nr
                    st.success("New entry added.")
                # 2) Edit
                if selected is not None:
                    for k, v in edits.items():
                        if k != "Unique ID":
                            val = ", ".join(v) if k == "Authorized Drivers" else v
                            df.loc[df["Unique ID"]==selected, k] = val
                    st.success("Entry edited successfully.")
                # 3) Delete
                if delete_id is not None and confirm_delete:
                    df.drop(index=delete_id, inplace=True)
                    st.success(f"Entry {delete_id} deleted.")
                # 4) Bulk delete
                if start_dt and end_dt and confirm_bulk:
                    mask = (df["Checkout Date"]>=pd.Timestamp(start_dt)) & \
                           (df["Return Date"]  <=pd.Timestamp(end_dt))
                    df.drop(index=df[mask].index, inplace=True)
                    st.success("Bulk deletion complete.")

                # Finalize & write CSV
                df.reset_index(drop=True, inplace=True)
                df["Unique ID"] = df.index
                df.to_csv(FILE_PATH, index=False)

                # Refresh lookup lists
                current_assigned = get_assigned_to_list()
                if set(df["Assigned to"].unique()) != set(current_assigned):
                    with open("assigned_to_list.txt","w") as f:
                        for x in sorted(df["Assigned to"].unique()):
                            f.write(f"{x}\n")
                    get_assigned_to_list.clear()

                # 7. GIT PUSH
                push_changes_to_github()

            st.success("All changes committed and pushed to GitHub.")