import streamlit as st
import google.generativeai as genai
from datetime import datetime
import pandas as pd
import json
import os
from dotenv import load_dotenv
from google_calendar import get_google_calendar_service
import time
from utils import parse_natural_language, handle_calendar_action, process_calendar_request


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

# Set page config
st.set_page_config(layout="wide", page_title="Donna")

# Load external CSS
with open('style.css') as f:
    st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# Initialize session state for chat history
if 'messages' not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hello! I'm Donna, your friendly calendar assistant. How can I help you manage your schedule today?"}
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
    st.markdown('<div class="chat-title">Donna</div>', unsafe_allow_html=True)

    # Create a container for chat messages with fixed height
    chat_container = st.container(height=700)  # Using a larger pixel value to fill most of the screen
    
    # Display chat history in the container
    with chat_container:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.write(message["content"])
    
    # Chat input at the bottom
    if prompt := st.chat_input("What would you like to do with your calendar?"):
        if prompt != st.session_state.last_prompt:
            st.session_state.last_prompt = prompt
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            try:
                # Process the calendar request using the new function
                success, response = process_calendar_request(prompt, model, st.session_state.calendar_service)
                
                # Add the response to the chat history
                st.session_state.messages.append({"role": "assistant", "content": response})
                
                # Only refresh if the request was successful and it was a calendar action
                if success:
                    st.rerun()
            except Exception as e:
                error_msg = f"I'm having trouble understanding your request. Could you please rephrase it? Error: {str(e)}"
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
                st.rerun()


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