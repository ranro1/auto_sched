import streamlit as st
import time
from datetime import datetime
from utils import parse_natural_language, schedule_event, add_message
from google_calendar import get_google_calendar_service

# Initialize Google Calendar service
if 'calendar_service' not in st.session_state:
    try:
        st.session_state.calendar_service = get_google_calendar_service()
    except Exception as e:
        st.error("Please set up Google Calendar credentials. See README for instructions.")
        st.stop()

# Set page config
st.set_page_config(layout="wide", page_title="My Private Scheduler")

# Load CSS
with open('styles.css', 'r') as f:
    st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# Initialize session state for chat history
if 'messages' not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hello! I'm your private scheduler. How can I help you plan your time today?"}
    ]

# Initialize last_prompt to avoid loops
if 'last_prompt' not in st.session_state:
    st.session_state.last_prompt = None

# Main layout - Two columns
col1, col2 = st.columns([1, 2])

# Left column - Chat interface
with col1:
    # Title
    st.markdown('<div class="chat-title">Schedule Assistant</div>', unsafe_allow_html=True)
    
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
                start_datetime, end_datetime, event_link = schedule_event(event_details, st.session_state.calendar_service)
                response = f"Scheduled {event_details['title']} on {event_details['day']} from {start_datetime.strftime('%I:%M %p')} to {end_datetime.strftime('%I:%M %p')}"
                st.session_state.messages.append({"role": "assistant", "content": response})
                st.rerun()
            except Exception as e:
                error_msg = f"I couldn't schedule the event. Error: {str(e)}"
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
                st.rerun()
    
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