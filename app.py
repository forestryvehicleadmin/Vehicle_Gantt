import pandas as pd
import plotly.express as px
import streamlit as st
from datetime import datetime, timedelta
import subprocess
import os
from pathlib import Path
import shutil

# Set the app to wide mode
st.set_page_config(layout="wide", page_title="SoF Vehicle Assignments", page_icon="📊")

# GitHub repository details
GITHUB_REPO = "forestryvehicleadmin/Vehicle_Gantt" # Replace with your repo name
GITHUB_BRANCH = "master"  # Replace with your branch name
FILE_PATH = "Vehicle_Checkout_List.xlsx"  # Relative path to the Excel file in the repo

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
    
    # Force Git to use the SSH URL so your key actually works
    subprocess.run(["git", "remote", "set-url", "origin", f"git@github.com:{GITHUB_REPO}.git"], check=False)

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
        subprocess.run(["git", "pull", "origin", GITHUB_BRANCH, "--rebase"], check=True)

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
        subprocess.run(["git", "push", "origin", GITHUB_BRANCH], check=True)

        st.success("Changes successfully pushed to GitHub!")
    except subprocess.CalledProcessError as e:
        st.error(f"Failed to push changes: {e}")
    finally:
        # Optional cleanup of stash in case of errors
        subprocess.run(["git", "stash", "drop"], check=False, stderr=subprocess.DEVNULL)

# Path to the Excel file
file_path = r"Vehicle_Checkout_List.xlsx"

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
    #labels={"Assigned to": "Vehicle"}
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

# Sort the y-axis by ascending order of 'Type'
fig.update_yaxes(
    categoryorder="array",
    categoryarray=df["Type"].unique(),  # Use the sorted 'Type' column
    ticktext=[label[:3] for label in df["Type"]],  # Truncated labels
    tickvals=df["Type"],
    title=None,  # Hide Y-axis title
)

# Limit the y-axis labels to three characters
fig.update_yaxes(
    ticktext=[label[:3] for label in df["Type"]],  # Truncated labels
    tickvals=df["Type"],
    title=None,  # Hide Y-axis title
)

# Add today's date as a vertical red line
fig.add_shape(
    type="line",
    x0=today,
    y0=0,
    x1=today,
    y1=1,
    xref="x",
    yref="paper",
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
            x0=current_date,
            y0=0,
            x1=current_date,
            y1=1,
            xref="x",
            yref="paper",
            line=dict(color="gray", width=1.5, dash="solid"),
            layer="below",
        )
    # Add daily grid lines (thinner lines)
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

# Add horizontal grid lines only for used rows
unique_y_values = df["Type"].unique()
for idx, label in enumerate(unique_y_values):
    fig.add_shape(
        type="line",
        x0=start_range,
        y0=idx - 0.5,  # Align with the row's center
        x1=week_range,
        y1=idx - 0.5,
        xref="x",
        yref="y",
        line=dict(color="lightgray", width=1, dash="dot"),
    )

# Update layout for dynamic zoom and better visualization
fig.update_layout(
    height=800,  # Adjust chart height to fit full screen
    title_font_size=20,
    margin=dict(l=0, r=0, t=40, b=0),  # Minimize margins
    showlegend=show_legend,  # Toggle legend based on the checkbox
    xaxis_range=[start_range, end_range]  # Set initial zoom range
)

# Display the Gantt chart full screen
st.plotly_chart(fig, use_container_width=True)

# Add a dropdown to display the DataFrame
with st.expander("View and Filter Data Table"):
    st.subheader("Filter and View Data Table")
    columns = st.multiselect("Select Columns to Display:", df.columns, default=df.columns.tolist())
    st.dataframe(df[columns])  # Display the selected columns

# Secure edit/delete and create entry section
with st.expander("Manage Entries (Create, Edit, Delete) VEM use only."):

    # Passcode validation
    passcode = st.text_input("Enter the 4-digit passcode:", type="password")
    if passcode == "1234":  # Replace with your secure passcode
        st.success("Access granted!")

        # **1. Create a New Entry**
        # Function to load and parse the type list from the TXT file
        def load_type_list(file_path):
            try:
                with open(file_path, "r") as file:
                    lines = file.readlines()
                    return [line.strip() for line in lines if line.strip()]  # Remove empty lines
            except FileNotFoundError:
                return []


        # Function to load the authorized drivers from the TXT file
        def load_drivers_list(file_path):
            try:
                with open(file_path, "r") as file:
                    return [line.strip() for line in file if line.strip()]  # Remove empty lines
            except FileNotFoundError:
                return []


        # Function to load the "Assigned to" list from the TXT file
        def load_assigned_to_list(file_path):
            try:
                with open(file_path, "r") as file:
                    return [line.strip() for line in file if line.strip()]  # Remove empty lines
            except FileNotFoundError:
                return []


        # Load the type list from the uploaded file
        type_list = load_type_list("type_list.txt")
        # Load the authorized drivers list
        authorized_drivers_list = load_drivers_list("authorized_drivers_list.txt")
        # Load the assigned to list
        assigned_to_list = load_assigned_to_list("assigned_to_list.txt")

        st.subheader("Create New Entry")
        new_entry = {}

        # Dynamic dropdown options for Assigned to, Type, and Authorized Drivers
        assigned_to_options = df["Assigned to"].dropna().unique().tolist()
        type_options = df["Type"].dropna().unique().tolist()  # Type field options
        driver_options = df["Authorized Drivers"].dropna().str.split(",").explode().unique().tolist()

        # "Assigned to" field with an option to add a new name
        new_entry["Assigned to"] = st.selectbox(
            "Assigned to:", options=[""] + assigned_to_list
        )


        def save_assigned_to_list(file_path, data):
            """Save the assigned to list to a file."""
            with open(file_path, "w") as file:
                for item in data:
                    file.write(f"{item}\n")


        # Function to handle new "Assigned To" addition
        def add_new_assigned_to():
            # Access the global input value
            new_assigned_to = st.session_state["new_assigned_to"]
            if new_assigned_to and new_assigned_to not in assigned_to_list:
                assigned_to_list.append(new_assigned_to)

                # Save the updated list to the file
                save_assigned_to_list("assigned_to_list.txt", assigned_to_list)

                # Display success message and updated list
                st.success(f"'Assigned To' '{new_assigned_to}' successfully added.")

                # Push changes to GitHub
                push_changes_to_github()

                # Clear the input field
                st.session_state["new_assigned_to"] = ""  # Reset the text input
            elif not new_assigned_to:
                st.warning("Input cannot be empty.")
            else:
                st.warning("This entry already exists in the list.")


        # Text input with `on_change` to trigger the callback
        st.text_input(
            "Enter new 'Assigned To':",
            key="new_assigned_to",  # Store the input in session state
            on_change=add
