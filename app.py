import pandas as pd
import plotly.express as px
import streamlit as st
from datetime import datetime, timedelta
import subprocess
import os
from pathlib import Path

# GitHub repository details
GITHUB_REPO = "forestryvehicleadmin/vehicle_gantt"  # Replace with your repo name
GITHUB_BRANCH = "main"  # Replace with your branch name
FILE_PATH = "Vehicle_Checkout_List.xlsx"  # Relative path to the Excel file in the repo

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

# Clone the GitHub repository if not already cloned
REPO_DIR = Path("repo")
if not REPO_DIR.exists():
    st.write("Cloning the repository...")
    subprocess.run(["git", "clone", f"git@github.com:{GITHUB_REPO}.git", REPO_DIR.name], check=True)

# Change working directory to the repo
os.chdir(REPO_DIR)

# Pull the latest changes
st.write("Pulling the latest changes...")
subprocess.run(["git", "pull", "origin", GITHUB_BRANCH], check=True)
# Path to the Excel file
file_path = r"Vehicle_Checkout_List.xlsx"

# Set the app to wide mode
st.set_page_config(layout="wide", page_title="SoF Vehicle Assignments", page_icon="📊")

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
            with open(file_path, "w") as file:
                for item in data:
                    file.write(f"{item}\n")

        # Add a new "Assigned to" entry
        if st.button("Add New Assigned To"):
            new_assigned_to = st.text_input("Enter new Assigned To (Must be Faculty or Staff):", "")
            if new_assigned_to and new_assigned_to not in assigned_to_list:
                assigned_to_list.append(new_assigned_to)
                with open("assigned_to_list.txt", "w") as file:
                    file.writelines(f"{name}\n" for name in assigned_to_list)
                st.success(f"Assigned to '{new_assigned_to}' added.")

        # "Type" field (dropdown for vehicle types)
        new_entry["Type"] = st.selectbox("Type (Vehicle):", options=[""] + type_list)

        # Automatically populate the Vehicle # based on the first 3 characters of Type
        if new_entry["Type"]:
            try:
                new_entry["Vehicle #"] = int(new_entry["Type"].split("-")[0].strip())  # Extract first part as integer
            except ValueError:
                st.error("The Type must start with a numeric value for Vehicle #.")
                new_entry["Vehicle #"] = None
        else:
            new_entry["Vehicle #"] = None

        # "Status" field as a Boolean dropdown
        new_entry["Status"] = st.selectbox("Status:", options=["Confirmed", "Reserved"])

        new_entry["Authorized Drivers"] = st.multiselect(
            "Authorized Drivers (May select multiple):",
            options=authorized_drivers_list,
            default=[]
        )


        def save_drivers_list(file_path, data):
            with open(file_path, "w") as file:
                for item in data:
                    file.write(f"{item}\n")


        # Add a new authorized driver
        if st.button("Add New Authorized Driver"):
            new_driver = st.text_input("Enter new Authorized Driver:", "")
            if new_driver and new_driver not in authorized_drivers_list:
                authorized_drivers_list.append(new_driver)
                save_drivers_list("authorized_drivers_list.txt", authorized_drivers_list)
                st.success(f"Authorized driver '{new_driver}' added.")

        # Fields for other columns
        for column in df.columns[:-1]:  # Exclude "Unique ID"
            if column not in ["Assigned to", "Type", "Vehicle #", "Status",
                              "Authorized Drivers"]:  # Already handled above
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
                elif new_entry["Vehicle #"] is None:
                    st.error("Error: Vehicle # could not be derived. Ensure Type starts with a numeric value.")
                else:
                    # Handle the Authorized Drivers as a comma-separated string
                    new_entry["Authorized Drivers"] = ", ".join(new_entry["Authorized Drivers"])

                    # Append the new entry to the DataFrame
                    new_row_df = pd.DataFrame([new_entry])
                    df = pd.concat([df, new_row_df], ignore_index=True)
                    df.reset_index(drop=True, inplace=True)  # Reset index
                    df["Unique ID"] = df.index  # Reassign Unique ID

                    # Save the updated DataFrame to the Excel file
                    df.to_excel(file_path, index=False, engine="openpyxl")
                    st.success("New entry added and saved successfully!")
            except Exception as e:
                st.error(f"Failed to add entry: {e}")

        # **2. Edit Existing Entry**
        st.subheader("Edit Entry")
        selected_id = st.selectbox(
            "Select an entry to edit:",
            options=df["Unique ID"].values,
            format_func=lambda
                x: f"{df.loc[x, 'Assigned to']} ({df.loc[x, 'Checkout Date']} - {df.loc[x, 'Return Date']})"
            if x in df["Unique ID"].values else "Unknown Entry"
        )

        st.write("Selected Entry Details:")
        st.write(df.loc[selected_id])

        edited_row = {}
        for column in df.columns[:-1]:  # Exclude Unique ID
            if pd.api.types.is_datetime64_any_dtype(df[column]):
                edited_row[column] = st.date_input(f"{column}:", value=df.loc[selected_id, column])
            elif pd.api.types.is_numeric_dtype(df[column]):
                edited_row[column] = st.number_input(f"{column}:", value=df.loc[selected_id, column])
            else:
                edited_row[column] = st.text_input(f"{column}:", value=df.loc[selected_id, column])

        if st.button("Update Entry"):
            for key, value in edited_row.items():
                df.at[selected_id, key] = value
            st.success("Entry updated successfully!")

        # **3. Delete an Entry**
        st.subheader("Delete Entry")
        if st.button("Delete Entry"):
            df = df.drop(index=selected_id).reset_index(drop=True)  # Reset index after deletion
            df["Unique ID"] = df.index  # Reassign Unique ID
            st.success("Entry deleted successfully!")

        # **2. Bulk Delete Entries by Date Range**
        st.subheader("Bulk Delete Entries (Save copy before deleting")
        start_date = st.date_input("Start Date:", value=datetime.today() - timedelta(weeks=4))
        end_date = st.date_input("End Date:", value=datetime.today())

        # Convert `start_date` and `end_date` to `pd.Timestamp`
        start_date = pd.Timestamp(start_date)
        end_date = pd.Timestamp(end_date)

        # Filter the entries within the specified date range
        filtered_df = df[(df["Checkout Date"] >= start_date) &
                         (df["Return Date"] <= end_date)]

        st.write("Entries to be deleted:")
        st.dataframe(filtered_df)

        # First confirmation button
        if st.button("Confirm Bulk Deletion"):
            st.warning("Are you sure? This action cannot be undone!")
            # Second confirmation button
            if st.button("Confirm and Delete"):
                try:
                    # Drop the filtered rows
                    df = df.drop(filtered_df.index).reset_index(drop=True)
                    df["Unique ID"] = df.index  # Reassign Unique ID

                    # Save changes to the Excel file
                    df.to_excel(file_path, index=False, engine="openpyxl")
                    st.success("Selected entries have been deleted and saved successfully!")
                except Exception as e:
                    st.error(f"Failed to delete entries: {e}")

        # **Save Changes**
        if st.button("Save Changes"):
            try:
                df.to_excel(file_path, index=False, engine="openpyxl")
                st.success("Changes saved to the Excel file!")
            except Exception as e:
                st.error(f"Failed to save changes: {e}")

    else:
        st.error("Incorrect passcode. Access denied!")
