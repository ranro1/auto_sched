import streamlit as st
import google.generativeai as genai
from datetime import datetime, timedelta
import pandas as pd
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
model = genai.GenerativeModel('gemini-pro')

# Initialize session states
if 'current_week' not in st.session_state:
    st.session_state.current_week = datetime.now()
if 'events' not in st.session_state:
    st.session_state.events = []
if 'selected_slot' not in st.session_state:
    st.session_state.selected_slot = None
if 'messages' not in st.session_state:
    st.session_state.messages = []

# Custom CSS for calendar styling
st.markdown("""
<style>
    /* Dark theme and general styles */
    .stApp {
        background-color: #202124;
        color: #ffffff;
    }
    
    /* Calendar container */
    .calendar-container {
        background-color: #2d2e31;
        border-radius: 8px;
        padding: 10px;
        margin: 10px 0;
    }
    
    /* Time column */
    .time-column {
        color: #70757a;
        font-size: 12px;
        text-align: right;
        padding-right: 10px;
        border-right: 1px solid #333;
    }
    
    /* Calendar grid */
    .calendar-grid {
        display: grid;
        grid-template-columns: 80px repeat(7, 1fr);
        gap: 1px;
        background-color: #333;
    }
    
    /* Time slot */
    .time-slot {
        background-color: #2d2e31;
        padding: 4px;
        min-height: 30px;
        border-bottom: 1px solid #333;
        cursor: pointer;
        position: relative;
    }
    .time-slot:hover {
        background-color: #3c4043;
    }
    
    /* Event block */
    .event-block {
        background-color: #1a73e8;
        color: white;
        border-radius: 4px;
        padding: 4px 8px;
        margin: 2px 0;
        font-size: 12px;
        cursor: pointer;
        position: relative;
        z-index: 2;
    }
    .event-block:hover {
        filter: brightness(1.1);
    }
    
    /* Current time indicator */
    .current-time {
        border-top: 2px solid #ea4335;
        position: absolute;
        width: 100%;
        z-index: 1;
    }
    
    /* Day header */
    .day-header {
        background-color: #2d2e31;
        padding: 8px;
        text-align: center;
        font-weight: bold;
        border-bottom: 1px solid #333;
    }
    .current-day {
        color: #1a73e8;
    }
    
    /* Navigation */
    .nav-container {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 10px;
        background-color: #2d2e31;
        border-radius: 8px;
        margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

def format_time(dt, format_12h=False):
    """Format time in either 24h or 12h format"""
    if format_12h:
        return dt.strftime("%I:%M %p").lstrip("0")
    return dt.strftime("%H:%M")

def create_time_slots():
    """Create 30-minute time slots from 8 AM to 8 PM"""
    slots = []
    start = datetime.strptime("08:00", "%H:%M")
    end = datetime.strptime("20:00", "%H:%M")
    current = start
    while current <= end:
        slots.append(current)
        current += timedelta(minutes=30)
    return slots

def is_current_time_slot(time_slot, day):
    """Check if this is the current time slot"""
    now = datetime.now()
    return (now.strftime("%A").upper()[:3] == day and 
            time_slot.hour == now.hour and 
            time_slot.minute <= now.minute < time_slot.minute + 30)

def handle_slot_click(day, time_slot):
    """Handle click on a time slot"""
    st.session_state.selected_slot = {
        'day': day,
        'time': time_slot
    }

def create_calendar():
    """Create the calendar grid"""
    # Navigation
    col1, col2, col3, col4, col5 = st.columns([1, 2, 6, 2, 1])
    with col1:
        if st.button("←"):
            st.session_state.current_week -= timedelta(days=7)
    with col2:
        if st.button("Today"):
            st.session_state.current_week = datetime.now()
    with col3:
        start_date = st.session_state.current_week - timedelta(days=st.session_state.current_week.weekday())
        st.markdown(f"### {start_date.strftime('%B %Y')}")
    with col5:
        if st.button("→"):
            st.session_state.current_week += timedelta(days=7)

    # Calendar grid
    week_days = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']
    dates = [(start_date + timedelta(days=i)) for i in range(7)]
    
    # Day headers
    st.markdown('<div class="calendar-grid">', unsafe_allow_html=True)
    st.markdown('<div class="time-column"></div>', unsafe_allow_html=True)
    for i, (day, date) in enumerate(zip(week_days, dates)):
        is_current = date.date() == datetime.now().date()
        st.markdown(
            f'<div class="day-header {"current-day" if is_current else ""}">'
            f'{day}<br>{date.strftime("%d")}</div>',
            unsafe_allow_html=True
        )
    
    # Time slots and events
    time_slots = create_time_slots()
    for time_slot in time_slots:
        # Time column
        st.markdown(
            f'<div class="time-column">{format_time(time_slot)}</div>',
            unsafe_allow_html=True
        )
        
        # Day columns
        for day in week_days:
            events = [e for e in st.session_state.events 
                     if e['day'] == day and 
                     datetime.strptime(e['start_time'], "%H:%M") <= time_slot < 
                     datetime.strptime(e['end_time'], "%H:%M")]
            
            slot_html = f'<div class="time-slot" onclick="handle_slot_click(\'{day}\', \'{format_time(time_slot)}\')">'

            # Current time indicator
            if is_current_time_slot(time_slot, day):
                slot_html += '<div class="current-time"></div>'
            
            # Events
            for event in events:
                slot_html += f"""
                <div class="event-block" style="background-color: {event.get('color', '#1a73e8')}">
                    {event['title']}<br>
                    <small>{event['start_time']} - {event['end_time']}</small>
                </div>
                """
            
            slot_html += '</div>'
            st.markdown(slot_html, unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

# Main layout - Two columns
col1, col2 = st.columns([1, 2])

# Left column - Chat interface
with col1:
    # Chat container
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)
    
    # Messages area
    st.markdown('<div class="chat-messages">', unsafe_allow_html=True)
    
    # Display messages
    for message in st.session_state.messages:
        message_class = "user-message" if message["role"] == "user" else "assistant-message"
        st.markdown(
            f'<div class="message {message_class}">{message["content"]}</div>',
            unsafe_allow_html=True
        )
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Input area
    st.markdown('<div class="chat-input">', unsafe_allow_html=True)
    if prompt := st.chat_input("What would you like to schedule?"):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Get assistant response
        chat_response = model.generate_content(f"""
        You are a helpful scheduling assistant. The user said: "{prompt}"
        Current schedule: {json.dumps(st.session_state.events)}
        Please provide a helpful response and suggest any schedule changes.
        """)
        
        # Add assistant response
        st.session_state.messages.append({
            "role": "assistant",
            "content": chat_response.candidates[0].content.parts[0].text
        })
        
        # Rerun to update chat
        st.rerun()
    
    st.markdown('</div></div>', unsafe_allow_html=True)

# Right column - Calendar
with col2:
    st.title("Calendar")
    create_calendar()
