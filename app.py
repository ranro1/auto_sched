import streamlit as st
import google.generativeai as genai
from datetime import datetime, timedelta
import pandas as pd
import json
import os
from dotenv import load_dotenv
from scheduler import Scheduler

# Load environment variables
load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
model = genai.GenerativeModel('gemini-pro')

# Initialize scheduler
if 'scheduler' not in st.session_state:
    st.session_state.scheduler = Scheduler()
if 'current_week' not in st.session_state:
    st.session_state.current_week = datetime.now()

# Initialize session state
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'schedule' not in st.session_state:
    st.session_state.schedule = pd.DataFrame(columns=['Task', 'Start Time', 'End Time', 'Priority', 'Status', 'Day', 'Color'])

# Custom CSS for dark theme and calendar styling
st.markdown("""
<style>
    /* Dark theme */
    .stApp {
        background-color: #202124;
        color: #ffffff;
    }
    
    /* Calendar header */
    .calendar-header {
        background-color: #2d2e31;
        padding: 10px;
        border-radius: 8px;
        margin-bottom: 10px;
    }
    
    /* Time column */
    .time-column {
        color: #70757a;
        font-size: 12px;
        text-align: right;
        padding-right: 10px;
    }
    
    /* Calendar grid */
    .calendar-grid {
        border: 1px solid #333;
        background-color: #2d2e31;
    }
    
    /* Event blocks */
    .event-block {
        border-radius: 4px;
        padding: 4px 8px;
        margin: 2px 0;
        font-size: 14px;
    }
    
    /* Navigation buttons */
    .nav-button {
        background-color: transparent;
        border: none;
        color: #ffffff;
        cursor: pointer;
    }
</style>
""", unsafe_allow_html=True)

def format_time_24h(time):
    """Format time in 24h format"""
    return time.strftime("%H:%M")

def format_time_12h(time):
    """Format time in 12h format"""
    return time.strftime("%I:%M %p")

def create_weekly_calendar(schedule_df):
    # Calendar header with navigation
    col1, col2, col3, col4, col5 = st.columns([1, 3, 8, 3, 1])
    
    with col1:
        if st.button("←"):
            st.session_state.current_week -= timedelta(days=7)
    
    with col2:
        st.button("Today", key="today_button", 
                 on_click=lambda: setattr(st.session_state, 'current_week', datetime.now()))
    
    with col3:
        start_date = st.session_state.current_week - timedelta(days=st.session_state.current_week.weekday())
        end_date = start_date + timedelta(days=6)
        st.markdown(f"### {start_date.strftime('%B %Y')}")
    
    with col4:
        st.selectbox("View", ["Week", "Month", "Year"], key="view_selector")
    
    with col5:
        if st.button("→"):
            st.session_state.current_week += timedelta(days=7)

    # Create the calendar grid
    week_days = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT']
    dates = [(start_date + timedelta(days=i)).day for i in range(7)]
    
    # Day headers
    cols = st.columns([0.8] + [1] * 7)
    with cols[0]:
        st.write("")  # Empty space for time column
    for i, (day, date) in enumerate(zip(week_days, dates)):
        with cols[i + 1]:
            st.markdown(f"**{day}**\n{date}", unsafe_allow_html=True)
    
    # Time slots and events
    for hour in range(24):
        time_slot = datetime.strptime(f"{hour:02d}:00", "%H:%M")
        cols = st.columns([0.8] + [1] * 7)
        
        # Time column
        with cols[0]:
            st.markdown(f"""
            <div class="time-column">
                {format_time_24h(time_slot)}<br>
                <small>{format_time_12h(time_slot)}</small>
            </div>
            """, unsafe_allow_html=True)
        
        # Event columns
        for day_idx, day in enumerate(week_days):
            with cols[day_idx + 1]:
                day_events = schedule_df[
                    (schedule_df['Day'] == day) & 
                    (pd.to_datetime(schedule_df['Start Time']).dt.hour <= hour) & 
                    (pd.to_datetime(schedule_df['End Time']).dt.hour > hour)
                ]
                
                for _, event in day_events.iterrows():
                    color = event.get('Color', '#1a73e8')  # Default blue color
                    st.markdown(f"""
                    <div class="event-block" style="background-color: {color}">
                        {event['Task']}<br>
                        <small>{event['Start Time']} - {event['End Time']}</small>
                    </div>
                    """, unsafe_allow_html=True)

# Chat interface in a sidebar
with st.sidebar:
    st.subheader("Chat with your Assistant")
    
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
    
    # Chat input
    if prompt := st.chat_input("What would you like to schedule?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.write(prompt)
        
        with st.chat_message("assistant"):
            schedule_response = st.session_state.scheduler.generate_schedule(prompt)
            chat_response = model.generate_content(f"""
            You are a helpful scheduling assistant. The user said: "{prompt}"
            Current schedule: {st.session_state.schedule.to_json()}
            Scheduling response: {schedule_response}
            """)
            
            if isinstance(schedule_response, pd.DataFrame):
                st.session_state.schedule = schedule_response
            
            st.write(chat_response.candidates[0].content.parts[0].text)
            st.session_state.messages.append({
                "role": "assistant",
                "content": chat_response.candidates[0].content.parts[0].text
            })

# Main calendar view
st.markdown("## Schedule")
create_weekly_calendar(st.session_state.schedule)

# Add task form in an expander
with st.expander("Add New Task"):
    with st.form("add_task"):
        task_name = st.text_input("Task Name")
        col1, col2 = st.columns(2)
        with col1:
            day = st.selectbox("Day", ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'])
            start_time = st.time_input("Start Time")
        with col2:
            color = st.color_picker("Color", "#1a73e8")
            end_time = st.time_input("End Time")
        
        priority = st.selectbox("Priority", ["High", "Medium", "Low"])
        restrictions = st.text_area("Restrictions")
        submitted = st.form_submit_button("Add Task")
        
        if submitted:
            restrictions_dict = {"restrictions": restrictions} if restrictions else {}
            conflicts = st.session_state.scheduler.add_task(
                task_name=task_name,
                start_time=start_time.strftime('%H:%M'),
                end_time=end_time.strftime('%H:%M'),
                priority=priority,
                restrictions=restrictions_dict,
                day=day,
                color=color
            )
            
            if conflicts:
                st.warning(f"Warning: Scheduling conflicts detected: {conflicts}")
            else:
                st.success("Task added successfully!")
            
            st.session_state.schedule = st.session_state.scheduler.get_schedule() 