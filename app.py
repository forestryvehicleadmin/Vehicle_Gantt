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
GITHUB_REPO = "forestryvehicleadmin/Vehicle_Gantt"  # Repo name without .git
GITHUB_BRANCH = "master"  # Replace with your branch name
FILE_PATH = "Vehicle_Checkout_List.xlsx"  # Relative path to the Excel file in the repo
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

        # Commit changes
        subprocess.run(["git", "commit", "-m", "Update Excel and TXT files from Streamlit app"], check=True)

        # Push changes to GitHub
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
    df = pd.read_excel(file_path, engine="openpyxl")
    df['Checkout Date'] = pd.to_datetime(df['Checkout Date'])
    df['Return Date'] = pd.to_datetime(df['Return Date'])
    df["Unique ID"] = df.index  # Add a unique identifier for each row
    df['Notes'] = df['Notes'].astype(str)

    # Sort the DataFrame by the 'Type' column (ascending order)
    df = df.sort_values(by="Type", ascending=True)
except Exception as e:
    st.error(f"Error loading Excel file: {e}")
    st.stop()

# Full-screen Gantt chart
#st.title("Interactive Vehicle Assignment Gantt Chart")
st.markdown("###")

# Add a button to toggle the legend
show_legend = st.checkbox("Show Legend", value=False)

#@st.cache_data(show_spinner="Generating Gantt chart...")
def generate_gantt_chart(df, view_mode, show_legend):
    time.sleep(1)
    df = df.copy()
    today = datetime.today()
    start_range = today - timedelta(weeks=2)
    end_range = today + timedelta(weeks=4)
    week_range = end_range + timedelta(weeks=10)

    xaxis_range = (
        [today - timedelta(days=2), today + timedelta(days=5)]
        if view_mode == "Mobile"
        else [start_range, end_range]
    )

    df["Bar Label"] = df["Vehicle #"].astype(str) + " - " + df["Assigned to"]

    custom_colors = [
        "#353850", "#3A565A", "#3E654C", "#557042", "#7C7246", "#884C49",
        "#944C7F", "#7B4FA1", "#503538", "#5A3A56", "#4C3E65", "#425570",
        "#467C72", "#49884C", "#80944C", "#A1794F", "#395035", "#575A3A",
        "#654B3E", "#704255", "#72467C", "#4C4988", "#4C8094", "#4FA179"
    ]

    assigned_to_names = df["Assigned to"].unique()
    color_map = {name: custom_colors[i % len(custom_colors)] for i, name in enumerate(assigned_to_names)}

    fig = px.timeline(
        df,
        x_start="Checkout Date",
        x_end="Return Date",
        y="Type",
        color="Assigned to",
        color_discrete_map=color_map,
        title="Vehicle Assignments",
        hover_data=["Unique ID", "Assigned to", "Status", "Type", "Checkout Date", "Return Date", "Authorized Drivers"],
        text="Bar Label"
    )
    fig.update_traces(
        textposition="inside",
        insidetextanchor="start",
        textfont=dict(size=10, color="white", family="Arial Black")
    )

    unique_types = df['Type'].unique()
    fig.update_yaxes(categoryorder="array", categoryarray=unique_types)

    for _, row in df.iterrows():
        if row['Status'] == 'Reserved':
            fig.add_shape(
                type="rect",
                x0=row['Checkout Date'],
                x1=row['Return Date'],
                y0=unique_types.tolist().index(row['Type']) - 0.4,
                y1=unique_types.tolist().index(row['Type']) + 0.4,
                xref="x",
                yref="y",
                fillcolor="rgba(255,0,0,0.1)",
                line=dict(width=0),
                layer="below"
            )

    for trace in fig.data:
        trace.opacity = 0.9

    fig.update_yaxes(
        categoryorder="array",
        categoryarray=df["Type"].unique(),
        ticktext=[label[:3] for label in df["Type"]],
        tickvals=df["Type"],
        title=None,
    )

    fig.add_shape(
        type="rect",
        x0=today.replace(hour=0, minute=0, second=0, microsecond=0),
        x1=today.replace(hour=23, minute=59, second=59, microsecond=999999),
        y0=0,
        y1=1,
        xref="x",
        yref="paper",
        fillcolor="rgba(255, 0, 0, 0.1)",
        line=dict(color="red", width=0),
        layer="below"
    )

    current_date = start_range
    while current_date <= week_range:
        current_date = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
        if current_date.weekday() == 0:
            fig.add_shape(
                type="line",
                x0=current_date,
                y0=0,
                x1=current_date,
                y1=1,
                xref="x",
                yref="paper",
                line=dict(color="gray", width=1.5, dash="solid"),
                layer="below",
            )
        fig.add_shape(
            type="line",
            x0=current_date,
            y0=0,
            x1=current_date,
            y1=1,
            xref="x",
            yref="paper",
            line=dict(color="lightgray", width=0.5, dash="dot"),
            layer="below",
        )
        current_date += timedelta(days=1)

    for idx, label in enumerate(unique_types):
        fig.add_shape(
            type="line",
            x0=start_range,
            y0=idx - 0.5,
            x1=week_range,
            y1=idx - 0.5,
            xref="x",
            yref="y",
            line=dict(color="lightgray", width=1, dash="dot"),
        )

    fig.update_layout(
        height=800,
        title_font_size=20,
        margin=dict(l=0, r=0, t=40, b=0),
        showlegend=show_legend,
        xaxis_range=xaxis_range
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


# Function to read contents of type_list.txt and display line by line
def load_type_list(file_path):
    try:
        with open(file_path, "r") as file:
            lines = file.readlines()  # Read each line into a list
            return "\n".join(line.strip() for line in lines if line.strip())  # Join with new lines
    except FileNotFoundError:
        return "File not found."

# Display the vehicle type list in a readable format
st.subheader("Vehicle Type List")
type_list_content = load_type_list("type_list.txt")

# Use st.markdown() to display line-separated vehicle types
st.markdown(f"```\n{type_list_content}\n```")


# Add a dropdown to display the DataFrame
with st.expander("View and Filter Data Table"):
    st.subheader("Filter and View Data Table")
    columns = st.multiselect("Select Columns to Display:", df.columns, default=df.columns.tolist())
    st.dataframe(df[columns])  # Display the selected columns


# 1. CACHE LOOKUP LISTS WITH st.cache_data INSTEAD OF experimental_singleton
def _load_list(path: str) -> list[str]:
    try:
        with open(path, "r") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []

@st.cache_data
def get_type_list() -> list[str]:
    return _load_list("type_list.txt")

@st.cache_data
def get_assigned_to_list() -> list[str]:
    return _load_list("assigned_to_list.txt")

@st.cache_data
def get_drivers_list() -> list[str]:
    return _load_list("authorized_drivers_list.txt")

# … later, when you detect list‐changes and rewrite a file …
# e.g. after updating assigned_to_list.txt:
with open("assigned_to_list.txt", "w") as f:
    for name in sorted(df["Assigned to"].unique()):
        f.write(f"{name}\n")
# invalidate that cache so next call re-reads the file
get_assigned_to_list.clear()

# 2. MANAGE ENTRIES SECTION
with st.expander("🔧 Manage Entries (VEM use only)"):
    passcode = st.text_input("Enter the 4-digit passcode:", type="password")
    if passcode != "1234":
        st.error("Incorrect passcode. Access denied.")
    else:
        st.success("Access granted!")

        # Initialize pending actions if not present
        if "pending_actions" not in st.session_state:
            st.session_state.pending_actions = []

        # Begin batched form
        with st.form("manage_entries"):

            st.subheader("1. Create New Entry")
            # Load cached lists
            type_list = get_type_list()
            assigned_to_list = get_assigned_to_list()
            drivers_list = get_drivers_list()

            # New entry container
            new = {}
            new["Assigned to"] = st.selectbox("Assigned to:", [""] + assigned_to_list)
            new_type = st.selectbox("Type (Vehicle):", [""] + type_list)
            new["Type"] = new_type
            new_vehicle_no = None
            if new_type:
                try:
                    new_vehicle_no = int(new_type.split("-")[0].strip())
                except ValueError:
                    st.error("Type must start with a numeric code.")
            new["Vehicle #"] = new_vehicle_no
            new["Status"] = st.selectbox("Status:", ["Confirmed", "Reserved"])
            new["Authorized Drivers"] = st.multiselect("Authorized Drivers:", drivers_list)

            # Date and other fields
            for col in [c for c in df.columns if c not in [
                    "Unique ID","Assigned to","Type","Vehicle #","Status","Authorized Drivers"]]:
                if pd.api.types.is_datetime64_any_dtype(df[col]):
                    dt = st.date_input(col + ":", value=datetime.today())
                    new[col] = datetime.combine(
                        dt,
                        datetime.max.time() if col.lower()=="return date" else datetime.min.time()
                    )
                elif pd.api.types.is_numeric_dtype(df[col]):
                    new[col] = st.number_input(col + ":", value=0)
                else:
                    new[col] = st.text_input(col + ":")

            st.markdown("---")
            st.subheader("2. Edit Existing Entry")
            selected = st.selectbox(
                "Select entry to edit:",
                options=[None] + df["Unique ID"].tolist(),
                format_func=lambda x: (
                    "Select…" if x is None else
                    (lambda row: f"{row['Vehicle #']}, {row['Assigned to']}, ({row['Checkout Date'].date()}→{row['Return Date'].date()})")(
                        df.loc[df["Unique ID"] == x].iloc[0]
                    )
                ))

edits = {}
if selected is not None:
    row = df[df["Unique ID"] == selected].iloc[0]

    # Assigned to
    edits["Assigned to"] = st.selectbox("Assigned to:", [""] + assigned_to_list,
                                        index=([""] + assigned_to_list).index(row["Assigned to"]),
                                        key=f"edit_assigned_to_{selected}")

    # Type and Vehicle #
    current_type = row["Type"]
    edits["Type"] = st.selectbox("Type (Vehicle):", [""] + type_list,
                                 index=([""] + type_list).index(current_type),
                                 key=f"edit_type_{selected}")
    edited_vehicle_no = None
    if edits["Type"]:
        try:
            edited_vehicle_no = int(edits["Type"].split("-")[0].strip())
        except ValueError:
            st.error("Type must start with a numeric code.")
    edits["Vehicle #"] = edited_vehicle_no

    # Status
    edits["Status"] = st.selectbox("Status:", ["Confirmed", "Reserved"],
                                   index=["Confirmed", "Reserved"].index(row["Status"]),
                                   key=f"edit_status_{selected}")

    # Authorized Drivers
    edits["Authorized Drivers"] = st.multiselect(
        "Authorized Drivers:", drivers_list,
        default=(row["Authorized Drivers"] or "").split(", "),
        key=f"edit_auth_drivers_{selected}"
    )

    # All other fields
    skip_cols = ["Unique ID", "Assigned to", "Type", "Vehicle #", "Status", "Authorized Drivers"]
    for col in [c for c in df.columns if c not in skip_cols]:
        widget_key = f"edit_{col}_{selected}"
        current_val = row[col]

        if pd.api.types.is_datetime64_any_dtype(df[col]):
            d = st.date_input(col + ":",
                              current_val.date() if not pd.isnull(current_val) else datetime.today(),
                              key=widget_key)
            edits[col] = datetime.combine(
                d,
                datetime.max.time() if col.lower() == "return date" else datetime.min.time()
            )
        elif pd.api.types.is_numeric_dtype(df[col]):
            edits[col] = st.number_input(col + ":", value=current_val if not pd.isnull(current_val) else 0,
                                         key=widget_key)
        else:
            edits[col] = st.text_input(col + ":", value=current_val or "", key=widget_key)


            st.markdown("---")
            st.subheader("3. Delete Entry")

            # Format function for user-friendly labels
            def format_func_d(x):
                if x is None:
                    return "Select..."
                row = df.loc[df["Unique ID"] == x].iloc[0]
                return f"{row['Vehicle #']}, {row['Assigned to']}, ({row['Checkout Date'].date()}→{row['Return Date'].date()})"

            # Selectbox with formatted labels
            delete_id = st.selectbox(
                "Select entry to delete:",
                options=[None] + df["Unique ID"].tolist(),
                format_func=format_func_d,
            )

            # Confirm checkbox
            confirm_delete = st.checkbox("Confirm deletion of selected entry")

            st.markdown("---")
            with st.expander("Bulk Delete"):
                st.subheader("4. Bulk Delete by Date Range")
                start_dt = st.date_input("Start Date for bulk delete:", value=None)
                end_dt = st.date_input("End Date for bulk delete:", value=None)
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
            status_opts = ["Confirmed", "Reserved"]

            cols = st.columns(3)
            with cols[0]:
                sel_types = st.multiselect("Filter by Type", options=type_opts, default=type_opts)
            with cols[1]:
                sel_assigned = st.multiselect("Filter by Assigned to", options=assigned_opts, default=assigned_opts)
            with cols[2]:
                sel_status = st.multiselect("Filter by Status", options=status_opts, default=status_opts)

            # Apply the filters
            mask = (
                    df["Type"].isin(sel_types) &
                    df["Assigned to"].isin(sel_assigned) &
                    df["Status"].isin(sel_status)
            )
            df_filtered = df[mask].copy()

            st.markdown(f"Showing {len(df_filtered)}/{len(df)} rows matching filters.")

            # 2) RENDER DATA EDITOR
            edited = st.data_editor(
                df_filtered,
                key="edit_table",
                num_rows="dynamic",
                use_container_width=True
            )

            # 3) SAVE BUTTON
            if st.button("Save Inline Edits"):
                # Merge edits back into the main df by Unique ID
                for _, row in edited.iterrows():
                    uid = row["Unique ID"]
                    if uid in df.index:
                        df.loc[uid, :] = row

                # Reassign Unique IDs just in case order changed
                df.reset_index(drop=True, inplace=True)
                df["Unique ID"] = df.index

                # Write to Excel and push
                df.to_excel(file_path, index=False, engine="openpyxl")
                st.success("Inline edits written to Excel.")

                with st.spinner("Pushing inline edits to GitHub..."):
                    push_changes_to_github()

        # AFTER form submit: process all pending actions
        if submitted:
            with st.spinner("Applying your changes…"):
                # 1. Create
                if new["Assigned to"] and new["Type"] and new["Vehicle #"] is not None:
                    new_row = new.copy()
                    new_row["Authorized Drivers"] = ", ".join(new_row["Authorized Drivers"])
                    df.loc[len(df)] = new_row
                    st.success("New entry added.")
                # 2. Edit
                if submitted:
                    if selected is not None:
                        for k, v in edits.items():
                            if k != "Unique ID":
                                df.at[selected, k] = ", ".join(v) if k == "Authorized Drivers" else v
                        st.success("Entry edited successfully.")
                # 3. Single delete
                if delete_id is not None and confirm_delete:
                    df.drop(index=delete_id, inplace=True)
                    st.success(f"Entry {delete_id} deleted.")
                # 4. Bulk delete
                if start_dt and end_dt and confirm_bulk:
                    mask = (df["Checkout Date"]>=pd.Timestamp(start_dt)) & (df["Return Date"]<=pd.Timestamp(end_dt))
                    df.drop(index=df[mask].index, inplace=True)
                    st.success("Bulk deletion complete.")

                # REASSIGN UNIQUE ID & SORT
                df.reset_index(drop=True, inplace=True)
                df["Unique ID"] = df.index

                # 5. WRITE ONCE
                df.to_excel(file_path, index=False, engine="openpyxl")

                # 6. UPDATE LOOKUP FILES IF THEY CHANGED
                # (You'd compare old vs new and write only if different.)
                # Example for assigned_to_list:
                current_assigned = get_assigned_to_list()
                if set(df["Assigned to"].unique()) != set(current_assigned):
                    with open("assigned_to_list.txt","w") as f:
                        for x in sorted(df["Assigned to"].unique()):
                            f.write(f"{x}\n")
                    get_assigned_to_list.clear()  # reset singleton

                # 7. GIT PUSH
                push_changes_to_github()

            st.success("All changes committed and pushed to GitHub.")