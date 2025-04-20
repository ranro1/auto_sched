import streamlit as st
import google.generativeai as genai
from datetime import datetime, timedelta
import pandas as pd
import json
import os
from dotenv import load_dotenv
from scheduler import Scheduler
from google_calendar import get_google_calendar_service, add_event_to_calendar, get_week_events, convert_to_dataframe
import time

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

# Load environment variables
load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
model = genai.GenerativeModel('gemini-1.5-flash')

# Initialize Google Calendar service
if 'calendar_service' not in st.session_state:
    try:
        st.session_state.calendar_service = get_google_calendar_service()
        st.success("Successfully connected to Google Calendar!")
    except Exception as e:
        st.error(f"Failed to connect to Google Calendar: {str(e)}")
        st.error("Please set up Google Calendar credentials. See README for instructions.")
        st.stop()

# Initialize session state
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'last_prompt' not in st.session_state:
    st.session_state.last_prompt = None

# Custom CSS for enhanced UI
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
        color: #ffffff;
        padding: 0 !important;
        margin: 0 !important;
    }
    
    .main-container {
        display: flex;
        flex-direction: row;
        align-items: stretch;
        padding: 0;
        margin: 0;
        min-height: 100vh;
    }
    
    .chat-container {
        flex: 1;
        max-width: 400px;
        background: rgba(45, 45, 45, 0.8);
        padding: 1rem;
    }
    
    .calendar-container {
        flex: 3;
        background: rgba(45, 45, 45, 0.8);
    }
    
    .calendar-iframe {
        width: 100%;
        height: 100vh;
        border: none;
    }
    
    .messages-container {
        height: calc(100vh - 200px);
        overflow-y: auto;
        padding: 1rem;
    }
    
    .chat-message {
        background-color: rgba(45, 45, 45, 0.8);
        border-radius: 12px;
        padding: 1rem;
        margin: 0.5rem 0;
        max-width: 85%;
    }
    
    .chat-message.user {
        background: linear-gradient(135deg, #1a73e8 0%, #0d47a1 100%);
        margin-left: auto;
    }
    
    .chat-message.assistant {
        background: rgba(45, 45, 45, 0.8);
        margin-right: auto;
    }
    
    .stTextInput > div > div > input {
        background-color: rgba(45, 45, 45, 0.8);
        color: white;
        border-radius: 12px;
        padding: 12px 16px;
    }
    
    h1 {
        color: white;
        margin: 0 !important;
        padding: 0 !important;
        font-size: 1.8rem !important;
    }
</style>
""", unsafe_allow_html=True)

# Main container
st.markdown('<div class="main-container">', unsafe_allow_html=True)

# Chat section
st.markdown('<div class="chat-container">', unsafe_allow_html=True)
st.title("Schedule Assistant")

# Messages container
st.markdown('<div class="messages-container">', unsafe_allow_html=True)
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])
st.markdown('</div>', unsafe_allow_html=True)

# Chat input
if prompt := st.chat_input("What would you like to schedule?"):
    if prompt != st.session_state.last_prompt:
        st.session_state.last_prompt = prompt
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.write(prompt)
        
        with st.chat_message("assistant"):
            try:
                event_details = parse_natural_language(prompt)
                start_datetime, end_datetime, event_link = schedule_event(event_details)
                response = f"Scheduled {event_details['title']} on {event_details['day']} from {start_datetime.strftime('%I:%M %p')} to {end_datetime.strftime('%I:%M %p')}"
                st.write(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
                st.experimental_rerun()
            except Exception as e:
                error_msg = f"I couldn't schedule the event. Error: {str(e)}"
                st.write(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})

st.markdown('</div>', unsafe_allow_html=True)

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