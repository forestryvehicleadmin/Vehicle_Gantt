import pandas as pd
import plotly.express as px
import streamlit as st
from datetime import datetime, timedelta
import subprocess
import os
from pathlib import Path
import shutil

# --- 1. CONFIGURATION & SETUP ---
st.set_page_config(layout="wide", page_title="SoF Vehicle Assignments", page_icon="📊")

# GitHub repository details
GITHUB_REPO = "jcs595/Vehicle_Gantt"  # Replace with your repo name
GITHUB_BRANCH = "master"  # Replace with your branch name
FILE_PATH = "Vehicle_Checkout_List.xlsx"  # Relative path to the Excel file in the repo
REPO_DIR = Path("repo")

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

# --- 2. GIT FUNCTIONS ---
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
    try:
        # Check for unstaged changes
        result = subprocess.run(["git", "status", "--porcelain"], stdout=subprocess.PIPE)
        if result.stdout.strip():
            # Stash unstaged changes if needed (optional logic here)
            subprocess.run(["git", "stash", "--include-untracked"], check=True)

        # Pull latest changes to avoid conflicts
        subprocess.run(["git", "pull", "origin", GITHUB_BRANCH, "--rebase"], check=True)

        # Restore stashed changes
        if result.stdout.strip():
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
        subprocess.run(["git", "push", "origin", GITHUB_BRANCH], check=True)

        st.success("Changes successfully pushed to GitHub!")
    except subprocess.CalledProcessError as e:
        st.error(f"Failed to push changes: {e}")
    finally:
        # Optional cleanup of stash in case of errors
        subprocess.run(["git", "stash", "drop"], check=False, stderr=subprocess.DEVNULL)

# --- 3. DATA LOADING ---
# Path to the Excel file
file_path = "Vehicle_Checkout_List.xlsx"

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

# Streamlit app title
st.title("SoF Vehicle Assignments")

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

# --- 4. GANTT CHART ---
st.markdown("###")

# Add a button to toggle the legend
show_legend = st.checkbox("Show Legend", value=False)

# Calculate dynamic zoom range: past 2 weeks and next 4 weeks
today = datetime.today()
start_range = today - timedelta(weeks=2)  # 2 weeks ago
end_range = today + timedelta(weeks=4)    # 4 weeks from now
week_range = end_range + timedelta(weeks=10)   # grids timeframe

# Create the Gantt chart
fig = px.timeline(
    df,
    x_start="Checkout Date",
    x_end="Return Date",
    y="Type",
    color="Assigned to",
    title="Vehicle Assignments",
    hover_data=["Unique ID", "Assigned to", "Status", "Type", "Checkout Date", "Return Date"],
)

# Ensure the Y-axis order is preserved
unique_types = df['Type'].unique()
fig.update_yaxes(
    categoryorder="array",
    categoryarray=unique_types
)

# Add semi-transparent overlays for 'Reserved' bars
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
            fillcolor="rgba(255,0,0,0.1)",  # Red with 10% opacity
            line=dict(width=0),  # No border for reserved
            layer="below"  # Ensure Reserved is drawn under Confirmed
        )

# Adjust bar opacity for the timeline
for trace in fig.data:
    trace.opacity = 0.9  # Set all timeline bars to 90% opacity

# Sort the y-axis by ascending order of 'Type' and Limit labels
fig.update_yaxes(
    categoryorder="array",
    categoryarray=df["Type"].unique(),
    ticktext=[label[:3] for label in df["Type"]],  # Truncated labels
    tickvals=df["Type"],
    title=None,
)

# Add today's date as a vertical red line
fig.add_shape(
    type="line",
    x0=today, y0=0, x1=today, y1=1,
    xref="x", yref="paper",
    line=dict(color="red", width=2, dash="dot"),
    name="Today"
)

# Add weekly and daily grid lines
current_date = start_range
while current_date <= week_range:
    # Add weekly grid lines (thicker lines)
    if current_date.weekday() == 0:  # Monday
        fig.add_shape(
            type="line",
            x0=current_date, y0=0, x1=current_date, y1=1,
            xref="x", yref="paper",
            line=dict(color="gray", width=1.5, dash="solid"),
            layer="below",
        )
    # Add daily grid lines (thinner lines)
    fig.add_shape(
        type="line",
        x0=current_date, y0=0, x1=current_date, y1=1,
        xref="x", yref="paper",
        line=dict(color="lightgray", width=0.5, dash="dot"),
        layer="below",
    )
    current_date += timedelta(days=1)

# Add horizontal grid lines only for used rows
unique_y_values = df["Type"].unique()
for idx, label in enumerate(unique_y_values):
    fig.add_shape(
        type="line",
        x0=start_range, y0=idx - 0.5,
        x1=week_range, y1=idx - 0.5,
        xref="x", yref="y",
        line=dict(color="lightgray", width=1, dash="dot"),
    )

# Update layout for dynamic zoom and better visualization
fig.update_layout(
    height=800,
    title_font_size=20,
    margin=dict(l=0, r=0, t=40, b=0),
    showlegend=show_legend,
    xaxis_range=[start_range, end_range]
)

# Display the Gantt chart full screen
st.plotly_chart(fig, use_container_width=True)

# Add a dropdown to display the DataFrame
with st.expander("View and Filter Data Table"):
    st.subheader("Filter and View Data Table")
    columns = st.multiselect("Select Columns to Display:", df.columns, default=df.columns.tolist())
    st.dataframe(df[columns])

# --- 5. MANAGEMENT SECTION ---
with st.expander("Manage Entries (Create, Edit, Delete) VEM use only."):

    # Passcode validation
    passcode = st.text_input("Enter the 4-digit passcode:", type="password")
    if passcode == "1234":  # Replace with your secure passcode
        st.success("Access granted!")

        # Helper Functions for loading lists
        def load_type_list(file_path):
            try:
                with open(file_path, "r") as file:
                    return [line.strip() for line in file if line.strip()]
            except FileNotFoundError:
                return []

        def load_drivers_list(file_path):
            try:
                with open(file_path, "r") as file:
                    return [line.strip() for line in file if line.strip()]
            except FileNotFoundError:
                return []

        def load_assigned_to_list(file_path):
            try:
                with open(file_path, "r") as file:
                    return [line.strip() for line in file if line.strip()]
            except FileNotFoundError:
                return []

        # Load lists
        type_list = load_type_list("type_list.txt")
        authorized_drivers_list = load_drivers_list("authorized_drivers_list.txt")
        assigned_to_list = load_assigned_to_list("assigned_to_list.txt")

        st.subheader("Create New Entry")
        new_entry = {}

        # Helpers for saving lists
        def save_assigned_to_list(file_path, data):
            with open(file_path, "w") as file:
                for item in data:
                    file.write(f"{item}\n")

        def save_drivers_list(file_path, data):
            with open(file_path, "w") as file:
                for item in data:
                    file.write(f"{item}\n")

        # Function to handle new "Assigned To" addition
        def add_new_assigned_to():
            new_val = st.session_state.get("new_assigned_to", "")
            if new_val and new_val not in assigned_to_list:
                assigned_to_list.append(new_val)
                save_assigned_to_list("assigned_to_list.txt", assigned_to_list)
                st.success(f"'Assigned To' '{new_val}' successfully added.")
                push_changes_to_github()
                st.session_state["new_assigned_to"] = ""
            elif not new_val:
                st.warning("Input cannot be empty.")
            else:
                st.warning("This entry already exists.")

        # Text input with callback
        st.text_input("Enter new 'Assigned To':", key="new_assigned_to", on_change=add_new_assigned_to)

        # "Assigned to" dropdown
        new_entry["Assigned to"] = st.selectbox("Assigned to:", options=[""] + assigned_to_list)

        # "Type" field
        new_entry["Type"] = st.selectbox("Type (Vehicle):", options=[""] + type_list)

        # Auto-populate Vehicle #
        if new_entry["Type"]:
            try:
                new_entry["Vehicle #"] = int(new_entry["Type"].split("-")[0].strip())
            except ValueError:
                st.error("The Type must start with a numeric value for Vehicle #.")
                new_entry["Vehicle #"] = None
        else:
            new_entry["Vehicle #"] = None

        new_entry["Status"] = st.selectbox("Status:", options=["Confirmed", "Reserved"])

        # Function to handle new authorized driver addition
        def add_new_driver():
            new_drv = st.session_state.get("new_driver", "")
            if new_drv and new_drv not in authorized_drivers_list:
                authorized_drivers_list.append(new_drv)
                save_drivers_list("authorized_drivers_list.txt", authorized_drivers_list)
                st.success(f"Authorized driver '{new_drv}' successfully added.")
                push_changes_to_github()
                st.session_state["new_driver"] = ""
            elif not new_drv:
                st.warning("Input cannot be empty.")
            else:
                st.warning("This driver already exists.")

        st.text_input("Enter new Authorized Driver:", key="new_driver", on_change=add_new_driver)

        new_entry["Authorized Drivers"] = st.multiselect(
            "Authorized Drivers (May select multiple):",
            options=authorized_drivers_list,
            default=[]
        )

        # Fields for other columns
        for column in df.columns[:-1]:  # Exclude "Unique ID"
            if column not in ["Assigned to", "Type", "Vehicle #", "Status", "Authorized Drivers"]:
                if pd.api.types.is_datetime64_any_dtype(df[column]):
                    new_entry[column] = st.date_input(f"{column}:", value=datetime.today())
                elif pd.api.types.is_numeric_dtype(df[column]):
                    new_entry[column] = st.number_input(f"{column}:", value=0)
                else:
                    new_entry[column] = st.text_input(f"{column}:")

        # Add entry button
        if st.button("Add Entry"):
            try:
                if not new_entry["Assigned to"] or not new_entry["Type"]:
                    st.error("Error: 'Assigned to' and 'Type' cannot be empty.")
                elif new_entry["Checkout Date"] > new_entry["Return Date"]:
                    st.error("Error: 'Checkout Date' cannot be after 'Return Date'.")
                else:
                    new_entry["Authorized Drivers"] = ", ".join(new_entry["Authorized Drivers"])
                    new_row_df = pd.DataFrame([new_entry])
                    df = pd.concat([df, new_row_df], ignore_index=True)
                    df.reset_index(drop=True, inplace=True)
                    df["Unique ID"] = df.index
                    
                    df.to_excel(file_path, index=False, engine="openpyxl")
                    push_changes_to_github()
                    st.success("New entry added and saved successfully!")
                    st.rerun()
            except Exception as e:
                st.error(f"Failed to add entry: {e}")

        # **2. Edit Existing Entry**
        st.subheader("Edit Entry")
        
        # Dropdown to select an entry by Unique ID
        def get_fmt(x):
            if pd.notna(x) and x in df["Unique ID"].values:
                row = df.loc[x]
                return f"{row['Assigned to']} ({row['Checkout Date']} - {row['Return Date']})"
            return "Select an entry"

        selected_id = st.selectbox(
            "Select an entry to edit:",
            options=[None] + df["Unique ID"].tolist(),
            format_func=get_fmt
        )

        if selected_id is not None:
            st.write("Selected Entry Details:")
            st.write(df.loc[selected_id])
            edited_row = {}

            # Editable fields
            for column in df.columns:
                if column == "Assigned to":
                    idx = assigned_to_list.index(df.loc[selected_id, column]) if df.loc[selected_id, column] in assigned_to_list else 0
                    edited_row[column] = st.selectbox(f"{column}:", options=assigned_to_list, index=idx, key=f"edit_dropdown_{column}")
                elif column == "Type":
                    idx = type_list.index(df.loc[selected_id, column]) if df.loc[selected_id, column] in type_list else 0
                    edited_row[column] = st.selectbox(f"{column}:", options=type_list, index=idx, key=f"edit_dropdown_{column}")
                elif column == "Status":
                    opts = ["Confirmed", "Reserved"]
                    idx = opts.index(df.loc[selected_id, column]) if df.loc[selected_id, column] in opts else 0
                    edited_row[column] = st.selectbox(f"{column}:", options=opts, index=idx, key=f"edit_dropdown_{column}")
                elif column == "Authorized Drivers":
                    defaults = df.loc[selected_id, column].split(", ") if pd.notna(df.loc[selected_id, column]) else []
                    # Ensure defaults exist in list
                    safe_defaults = [d for d in defaults if d in authorized_drivers_list]
                    edited_row[column] = st.multiselect(f"{column}:", options=authorized_drivers_list, default=safe_defaults, key=f"edit_multiselect_{column}")
                elif pd.api.types.is_datetime64_any_dtype(df[column]):
                    val = pd.Timestamp(df.loc[selected_id, column]) if pd.notna(df.loc[selected_id, column]) else datetime.today()
                    edited_row[column] = st.date_input(f"{column}:", value=val, key=f"edit_date_{column}")
                elif pd.api.types.is_numeric_dtype(df[column]):
                    val = df.loc[selected_id, column] if pd.notna(df.loc[selected_id, column]) else 0
                    edited_row[column] = st.number_input(f"{column}:", value=val, key=f"edit_number_{column}")
                else:
                    val = df.loc[selected_id, column] if pd.notna(df.loc[selected_id, column]) else ""
                    edited_row[column] = st.text_input(f"{column}:", value=val, key=f"edit_text_{column}")

            if st.button("Update Entry"):
                try:
                    for key, value in edited_row.items():
                        if key == "Authorized Drivers":
                            value = ", ".join(value)
                        df.at[selected_id, key] = value
                    
                    df.to_excel(file_path, index=False, engine="openpyxl")
                    push_changes_to_github()
                    st.success("Entry updated successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to update entry: {e}")
        else:
            st.info("Please select an entry to edit.")

        # **3. Delete an Entry**
        st.subheader("Delete Entry")
        if selected_id is not None and st.button("Delete Entry"):
            df = df.drop(index=selected_id).reset_index(drop=True)
            df["Unique ID"] = df.index
            df.to_excel(file_path, index=False, engine="openpyxl")
            push_changes_to_github()
            st.success("Entry deleted successfully!")
            st.rerun()

        # **4. Bulk Delete**
        st.subheader("Bulk Delete Entries")
        start_date = st.date_input("Start Date:", value=None)
        end_date = st.date_input("End Date:", value=None)

        if start_date and end_date:
            start_date = pd.Timestamp(start_date)
            end_date = pd.Timestamp(end_date)
            filtered_df = df[(df["Checkout Date"] >= start_date) & (df["Return Date"] <= end_date)]

            st.write("Entries to be deleted:")
            st.dataframe(filtered_df)

            if st.button("Confirm Bulk Deletion"):
                st.warning("Are you sure? This action cannot be undone!")
                if st.button("Confirm and Delete"):
                    try:
                        df = df.drop(filtered_df.index).reset_index(drop=True)
                        df["Unique ID"] = df.index
                        df.to_excel(file_path, index=False, engine="openpyxl")
                        push_changes_to_github()
                        st.success("Selected entries deleted!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to delete entries: {e}")

        # **Save Changes Manual Trigger**
        if st.button("Save Changes Manually"):
            try:
                df.to_excel(file_path, index=False, engine="openpyxl")
                push_changes_to_github()
                st.success("Changes saved!")
            except Exception as e:
                st.error(f"Failed to save changes: {e}")

    else:
        st.error("Incorrect passcode. Access denied!")
