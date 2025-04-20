import streamlit as st
import google.generativeai as genai
from datetime import datetime, timedelta
import pandas as pd
import json
import os
from dotenv import load_dotenv
from google_calendar import get_google_calendar_service, add_event_to_calendar, get_week_events, convert_to_dataframe
import time


# Load environment variables
load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
model = genai.GenerativeModel('gemini-1.5-flash')


def parse_natural_language(prompt):
    """Use Gemini to parse natural language into structured event details."""
    try:
        # Create a prompt for Gemini to extract event details
        system_prompt = """
        Extract event details from the following text and return a JSON object with:
        - title: The event title/description
        - day: The day of the week (MON, TUE, WED, THU, FRI, SAT, SUN) if specified
        - date: The date in format YYYY-MM-DD if specified (if year is not provided, use current year)
        - time: The time in 12-hour format with AM/PM (e.g., "05:00 PM")
        - duration: Duration in minutes (default to 30 if not specified)
        
        Example outputs:
        For day-based scheduling:
        {
            "title": "Call with John",
            "day": "MON",
            "time": "05:00 PM",
            "duration": 30
        }
        
        For date-based scheduling:
        {
            "title": "Team Meeting",
            "date": "2024-03-25",
            "time": "05:00 PM",
            "duration": 60
        }
        """
        
        # Get structured response from Gemini
        response = model.generate_content(f"{system_prompt}\n\nText: {prompt}")
        
        # Extract JSON from response
        try:
            # Find JSON in the response
            json_str = response.text[response.text.find('{'):response.text.rfind('}')+1]
            event_details = json.loads(json_str)
            
            # Validate required fields
            if not all(k in event_details for k in ['title', 'time']):
                raise ValueError("Missing required fields in response")
            
            # Standardize time format
            time_str = event_details['time'].upper()
            if 'AM' not in time_str and 'PM' not in time_str:
                time_str += ' PM' if int(time_str.split(':')[0]) < 12 else ' AM'
            event_details['time'] = time_str
            
            # Standardize day format if present
            if 'day' in event_details:
                day_map = {
                    'MONDAY': 'MON', 'TUESDAY': 'TUE', 'WEDNESDAY': 'WED',
                    'THURSDAY': 'THU', 'FRIDAY': 'FRI', 'SATURDAY': 'SAT', 'SUNDAY': 'SUN',
                    'MON': 'MON', 'TUE': 'TUE', 'WED': 'WED', 'THU': 'THU',
                    'FRI': 'FRI', 'SAT': 'SAT', 'SUN': 'SUN'
                }
                event_details['day'] = day_map.get(event_details['day'].upper(), 'MON')
            
            # Set default duration if not specified
            if 'duration' not in event_details:
                event_details['duration'] = 30
            
            return event_details
        except json.JSONDecodeError:
            raise ValueError("Could not parse event details from response")
    except Exception as e:
        raise Exception(f"Error parsing natural language: {str(e)}")

def schedule_event(event_details):
    """Schedule an event in Google Calendar using event details."""
    try:
        # Convert time to 24-hour format
        try:
            # Try parsing with leading zero format first
            time_obj = datetime.strptime(event_details['time'], '%I:%M %p')
        except ValueError:
            try:
                # Try parsing without leading zero
                time_obj = datetime.strptime(event_details['time'], '%I %p')
            except ValueError:
                raise ValueError("Invalid time format. Please use format like '05:00 PM'")
        
        # Calculate event date based on whether day or date is provided
        if 'date' in event_details:
            # Date-based scheduling
            try:
                # If date doesn't include year, add current year
                if len(event_details['date'].split('-')) == 2:
                    current_year = datetime.now().year
                    event_details['date'] = f"{current_year}-{event_details['date']}"
                
                event_date = datetime.strptime(event_details['date'], '%Y-%m-%d')
                
                # If the date is in the past, find the next occurrence in the current year
                if event_date < datetime.now():
                    event_date = event_date.replace(year=datetime.now().year + 1)
            except ValueError:
                raise ValueError("Invalid date format. Please use YYYY-MM-DD or MM-DD format")
        else:
            # Day-based scheduling
            start_date = datetime.now() - timedelta(days=datetime.now().weekday())
            day_offset = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'].index(event_details['day'])
            event_date = start_date + timedelta(days=day_offset)
            
            # If the day is in the past, move to next week
            if event_date < datetime.now():
                event_date += timedelta(days=7)
        
        # Create start and end datetime in UTC
        start_datetime = datetime.combine(event_date.date(), time_obj.time())
        # Convert to UTC to avoid timezone issues
        start_datetime = start_datetime.replace(tzinfo=None)
        end_datetime = start_datetime + timedelta(minutes=event_details['duration'])
        
        # Create event details
        event_data = {
            'Task': event_details['title'],
            'Start DateTime': start_datetime,
            'End DateTime': end_datetime,
            'ColorId': '1'  # Default blue color
        }
        
        # Add event to Google Calendar
        event_link = add_event_to_calendar(st.session_state.calendar_service, event_data)
        return start_datetime, end_datetime, event_link
    except Exception as e:
        raise Exception(f"Error scheduling event: {str(e)}")

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


# Initialize Google Calendar service
if 'calendar_service' not in st.session_state:
    try:
        st.session_state.calendar_service = get_google_calendar_service()
    except Exception as e:
        st.error("Please set up Google Calendar credentials. See README for instructions.")
        st.stop()

# Set page config
st.set_page_config(layout="wide", page_title="My Private Scheduler")

# Custom CSS for styling
st.markdown("""
<style>
    /* Calendar styling */
    .calendar-iframe {
        width: 100%;
        height: calc(100vh - 100px);
        min-height: 800px;
        border: none;
        margin-top: 10px;
    }
    
    /* Chat layout styling */
    .chat-container {
        display: flex;
        flex-direction: column;
        height: 100vh;
        position: relative;
    }
    
    .chat-title {
        padding: 15px;
        font-size: 24px;
        font-weight: bold;
        border-bottom: 1px solid #eee;
    }
    
    .chat-messages-container {
        flex: 1;
        overflow-y: auto;
        padding: 15px;
        margin-bottom: 80px; /* Space for the input */
    }
    
    .chat-input-container {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        background-color: white;
        padding: 15px;
        border-top: 1px solid #eee;
        z-index: 100;
    }
    
    /* Message styling */
    .message {
        max-width: 80%;
        padding: 12px 16px;
        border-radius: 15px;
        margin: 5px 0;
        font-size: 16px;
        line-height: 1.4;
    }
    
    .user-message {
        background-color: #e3f2fd;
        color: black;
        margin-left: auto;
        margin-right: 0;
        border-bottom-right-radius: 5px;
        text-align: right;
    }
    
    .assistant-message {
        background-color: #f5f5f5;
        color: black;
        margin-right: auto;
        margin-left: 0;
        border-bottom-left-radius: 5px;
        text-align: left;
    }
    
    /* Hide streamlit branding */
    #MainMenu, footer, header {
        visibility: hidden;
    }
</style>
""", unsafe_allow_html=True)


# Initialize session state for chat history
if 'messages' not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hello! I'm your private scheduler. How can I help you plan your time today?"}
    ]


# Initialize last_prompt to avoid loops
if 'last_prompt' not in st.session_state:
    st.session_state.last_prompt = None

# Function to add a message to the chat history
def add_message(role, content):
    st.session_state.messages.append({"role": role, "content": content})


# Main layout - Two columns
col1, col2 = st.columns([1, 2])

# Left column - Chat interface
with col1:
    
    # Title
    st.markdown('<div class="chat-title">Schedule Assistant</div>', unsafe_allow_html=True)

    # st.markdown('<div class="chat-container">', unsafe_allow_html=True)
    
    # Messages container
    st.markdown('<div class="chat-messages-container">', unsafe_allow_html=True)
    for message in st.session_state.messages:
        message_class = "user-message" if message["role"] == "user" else "assistant-message"
        st.markdown(
            f'<div class="message {message_class}">{message["content"]}</div>',
            unsafe_allow_html=True
        )
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Input container
    st.markdown('<div class="chat-input-container">', unsafe_allow_html=True)
    if prompt := st.chat_input("What would you like to schedule?"):
        if prompt != st.session_state.last_prompt:
            st.session_state.last_prompt = prompt
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            try:
                event_details = parse_natural_language(prompt)
                start_datetime, end_datetime, event_link = schedule_event(event_details)
                response = f"Scheduled {event_details['title']} on {event_details['day']} from {start_datetime.strftime('%I:%M %p')} to {end_datetime.strftime('%I:%M %p')}"
                st.session_state.messages.append({"role": "assistant", "content": response})
                st.rerun()
            except Exception as e:
                error_msg = f"I couldn't schedule the event. Error: {str(e)}"
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
                st.rerun()
    
    # st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)



# Right column - Google Calendar view
with col2:
    # Calendar section
    st.markdown('<div class="calendar-container">', unsafe_allow_html=True)
    try:
        calendar_list = st.session_state.calendar_service.calendarList().list().execute()
        primary_calendar = next((cal for cal in calendar_list.get('items', []) if cal.get('primary')), None)
        
        if primary_calendar:
            calendar_id = primary_calendar['id']
            timestamp = int(time.time())
            calendar_url = (
                f"https://calendar.google.com/calendar/embed?"
                f"src={calendar_id}&"
                f"height=1000&"
                f"wkst=1&"
                f"bgcolor=%231a1a1a&"
                f"ctz={datetime.now().astimezone().tzinfo}&"
                f"mode=WEEK&"
                f"showTitle=1&"
                f"showNav=1&"
                f"showDate=1&"
                f"showPrint=0&"
                f"showTabs=1&"
                f"showCalendars=1&"
                f"showTz=1&"
                f"hl=en&"
                f"t={timestamp}"
            )
            
            st.markdown("""
                <script>
                    function refreshCalendar() {
                        const iframe = document.querySelector('.calendar-iframe');
                        const currentSrc = iframe.src;
                        const newSrc = currentSrc.replace(/t=\\d+/, 't=' + Math.floor(Date.now() / 1000));
                        iframe.src = newSrc;
                    }
                    setInterval(refreshCalendar, 15000);
                </script>
            """, unsafe_allow_html=True)
            
            st.markdown(f"""
                <iframe 
                    class="calendar-iframe"
                    src="{calendar_url}"
                    frameborder="0">
                </iframe>
            """, unsafe_allow_html=True)
        else:
            st.error("Could not find your primary calendar. Please make sure you're properly authenticated.")
    except Exception as e:
        st.error(f"Error loading calendar: {str(e)}")

    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True) 