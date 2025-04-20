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

# Custom CSS for responsive layout and dark theme
st.markdown("""
<style>
    /* Main app styling */
    .stApp {
        background-color: #1a1a1a;
        color: #ffffff;
        padding: 0 !important;
        margin: 0 !important;
    }
    
    /* Responsive container */
    .main-container {
        display: flex;
        flex-direction: column;
        height: calc(100vh - 60px);
        padding: 0;
        margin: 0;
    }
    
    @media (min-width: 768px) {
        .main-container {
            flex-direction: row;
        }
    }
    
    /* Calendar container */
    .calendar-container {
        flex: 2;
        min-height: 400px;
        margin: 0;
        padding: 0;
    }
    
    @media (min-width: 768px) {
        .calendar-container {
            margin-right: 0;
        }
    }
    
    /* Chat container */
    .chat-container {
        flex: 1;
        min-height: 300px;
        background-color: #2d2d2d;
        border-radius: 0;
        padding: 1rem;
        overflow-y: auto;
        margin: 0;
    }
    
    /* Chat messages */
    .chat-message {
        background-color: #2d2d2d;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
        max-width: 80%;
    }
    
    .chat-message.user {
        background-color: #1a73e8;
        margin-left: auto;
    }
    
    .chat-message.assistant {
        background-color: #2d2d2d;
        margin-right: auto;
    }
    
    /* Input styling */
    .stTextInput > div > div > input {
        background-color: #2d2d2d;
        color: white;
        border-radius: 8px;
        padding: 8px 12px;
    }
    
    /* Calendar iframe */
    .calendar-iframe {
        width: 100%;
        height: 100%;
        min-height: 400px;
        border: none;
        border-radius: 0;
    }
    
    /* Scrollbar styling */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: #2d2d2d;
    }
    
    ::-webkit-scrollbar-thumb {
        background: #404040;
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: #505050;
    }
    
    /* Remove extra padding */
    .main > div {
        padding: 0 !important;
        margin: 0 !important;
    }
    
    /* Fix Streamlit's default padding */
    .block-container {
        padding: 0 !important;
        margin: 0 !important;
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

# Main layout
st.markdown('<div class="main-container">', unsafe_allow_html=True)

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