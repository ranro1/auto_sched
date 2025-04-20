import streamlit as st
import google.generativeai as genai
from datetime import datetime, timedelta
import pandas as pd
import json
import os
from dotenv import load_dotenv
from scheduler import Scheduler
from google_calendar import get_google_calendar_service, add_event_to_calendar, get_week_events, convert_to_dataframe

# Load environment variables
load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
model = genai.GenerativeModel('gemini-1.5-flash')

# Initialize Google Calendar service
if 'calendar_service' not in st.session_state:
    try:
        st.session_state.calendar_service = get_google_calendar_service()
    except Exception as e:
        st.error("Please set up Google Calendar credentials. See README for instructions.")
        st.stop()

# Initialize session state
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'last_prompt' not in st.session_state:
    st.session_state.last_prompt = None

# Custom CSS for styling
st.markdown("""
<style>
    /* Calendar styling */
    .calendar-container {
        border: 1px solid #ddd;
        border-radius: 5px;
        overflow: hidden;
    }
    .calendar-header {
        background-color: #f8f9fa;
        padding: 10px;
        border-bottom: 1px solid #ddd;
        font-weight: bold;
    }
    .time-slot {
        border-top: 1px solid #eee;
        padding: 8px;
        min-height: 40px;
    }
    .event {
        background-color: #4285f4;
        color: white;
        border-radius: 4px;
        padding: 5px;
        margin: 2px 0;
        font-size: 0.9em;
    }
    
    /* Chat messages area */
    .chat-messages {
        flex-grow: 1;
        overflow-y: auto;
        margin: 0;
    }
    
    /* Message bubbles */
    .message {
        max-width: 80%;
        padding: 12px 16px;
        border-radius: 15px;
        margin: 5px 0;
        font-size: 30px;
        line-height: 1.4;
    }
    
    .user-message {
        background-color: #e3f2fd;
        color: black;
        margin-left: auto;
        margin-right: 0;
        font-size: 22px;
        border-bottom-right-radius: 5px;
        text-align: right;
    }
    
    .assistant-message {
        background-color: #f5f5f5;
        color: black;
        margin-right: auto;
        margin-left: 0;
        font-size: 22px;
        border-bottom-left-radius: 5px;
        text-align: left;
    }
    
    /* Chat input area */
    .chat-input {
        padding: 20px;
        border-top: 1px solid #ddd;
    }

    /* Style the input field */
    .stTextInput input {
        font-size: 22px !important;
        height: 50px !important;
        border-radius: 25px !important;
    }

    /* Style the submit button */
    .stButton button {
        font-size: 30px !important;
        padding: 10px 25px !important;
        margin-top: 10px !important;
    }

    /* Hide Streamlit elements we don't want to see */
    .stTextInput > div > div > input {
        border: 1px solid #ddd !important;
    }
</style>
""", unsafe_allow_html=True)

def parse_schedule_prompt(prompt):
    """Parse the scheduling prompt to extract event details."""
    import re
    
    # Default values
    task_name = "Meeting"
    day = None
    time_str = None
    duration = 30
    
    # Extract task name
    task_match = re.search(r'([^0-9]+)(?:\s+on|\s+at|\s+for)', prompt, re.IGNORECASE)
    if task_match:
        task_name = task_match.group(1).strip()
    
    # Extract day
    day_match = re.search(r'(?:on\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)', prompt, re.IGNORECASE)
    if day_match:
        day = day_match.group(1).upper()[:3]
    
    # Extract time
    time_match = re.search(r'at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)', prompt, re.IGNORECASE)
    if time_match:
        time_str = time_match.group(1)
    
    # Extract duration
    duration_match = re.search(r'for\s+(\d+)\s*(?:min|minutes|mins|hour|hours|hr|hrs)', prompt, re.IGNORECASE)
    if duration_match:
        duration = int(duration_match.group(1))
    
    return task_name, day, time_str, duration

def schedule_event(task_name, day, time_str, duration):
    """Schedule an event in Google Calendar."""
    try:
        # Convert time to 24-hour format
        try:
            time_obj = datetime.strptime(time_str.strip(), '%I:%M %p')
        except:
            time_obj = datetime.strptime(time_str.strip(), '%I %p')
        
        # Calculate start and end datetime
        start_date = datetime.now() - timedelta(days=datetime.now().weekday())
        day_offset = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'].index(day)
        event_date = start_date + timedelta(days=day_offset)
        
        start_datetime = datetime.combine(event_date.date(), time_obj.time())
        end_datetime = start_datetime + timedelta(minutes=duration)
        
        # Add event to Google Calendar
        event_details = {
            'Task': task_name,
            'Start DateTime': start_datetime,
            'End DateTime': end_datetime,
            'ColorId': '1'  # Default blue color
        }
        
        event_link = add_event_to_calendar(st.session_state.calendar_service, event_details)
        return start_datetime, end_datetime, event_link
    except Exception as e:
        raise Exception(f"Error scheduling event: {str(e)}")

# Main layout - Two columns
col1, col2 = st.columns([1, 2])

# Calendar section
st.markdown('<div class="calendar-container">', unsafe_allow_html=True)
st.markdown("""
    <iframe 
        class="calendar-iframe"
        src="https://calendar.google.com/calendar/embed?height=600&wkst=1&bgcolor=%231a1a1a&ctz=UTC&mode=WEEK&showTitle=0&showNav=1&showDate=1&showPrint=0&showTabs=0&showCalendars=0&showTz=0"
        frameborder="0" 
        scrolling="no">
    </iframe>
""", unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# Chat section
st.markdown('<div class="chat-container">', unsafe_allow_html=True)
st.subheader("Chat with your Assistant")

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# Chat input
if prompt := st.chat_input("What would you like to schedule?"):
    # Check if this is a new prompt to avoid loops
    if prompt != st.session_state.last_prompt:
        st.session_state.last_prompt = prompt
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.write(prompt)
        
        with st.chat_message("assistant"):
            try:
                # Parse the prompt and schedule the event
                task_name, day, time_str, duration = parse_schedule_prompt(prompt)
                
                if day and time_str:
                    start_datetime, end_datetime, event_link = schedule_event(task_name, day, time_str, duration)
                    
                    # Show confirmation
                    response = f"Scheduled {task_name} on {day} from {start_datetime.strftime('%I:%M %p')} to {end_datetime.strftime('%I:%M %p')}"
                    st.write(response)
                    st.write(f"[View in Google Calendar]({event_link})")
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": response
                    })
                    
                    # Force page refresh to show updated calendar
                    st.experimental_rerun()
                else:
                    st.write("Please provide both day and time for scheduling. Example: 'Meeting on Monday at 2pm for 30 mins'")
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": "Please provide both day and time for scheduling. Example: 'Meeting on Monday at 2pm for 30 mins'"
                    })
            except Exception as e:
                st.write(f"I couldn't schedule the event. Error: {str(e)}")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"I couldn't schedule the event. Error: {str(e)}"
                })

st.markdown('</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True) 