import streamlit as st
import pandas as pd
import datetime
import random




# Set page config
st.set_page_config(layout="wide", page_title="My Private Scheduler")

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
        padding: 20px;
        display: flex;
        flex-direction: column;
        gap: 10px;
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

# Sample events data (this would be replaced with actual calendar data)
def generate_sample_events(start_date, days=7):
    events = []
    subjects = ["Meeting", "Work", "Study", "Exercise", "Break", "Project"]
    colors = ["#4285f4", "#34a853", "#fbbc05", "#ea4335", "#46bdc6", "#7986cb"]
    
    for day in range(days):
        current_date = start_date + datetime.timedelta(days=day)
        # Generate 2-5 events per day
        for _ in range(random.randint(2, 5)):
            start_hour = random.randint(8, 16)
            duration = random.randint(1, 3)
            subject = random.choice(subjects)
            color = colors[subjects.index(subject)]
            
            events.append({
                'date': current_date,
                'start_time': datetime.time(start_hour, 0),
                'end_time': datetime.time(start_hour + duration, 0),
                'subject': subject,
                'color': color
            })
    
    return events

# Initialize session state for chat history
if 'messages' not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hello! I'm your private scheduler. How can I help you plan your time today?"}
    ]

# Initialize and manage week navigation
if 'current_week_offset' not in st.session_state:
    st.session_state.current_week_offset = 0

# Function to add a message to the chat history
def add_message(role, content):
    st.session_state.messages.append({"role": role, "content": content})

# Get current date and calculate displayed week based on offset
today = datetime.datetime.now().date()
start_of_week = today - datetime.timedelta(days=today.weekday()) + datetime.timedelta(weeks=st.session_state.current_week_offset)
events = generate_sample_events(start_of_week)

# Main layout - Two columns
col1, col2 = st.columns([1, 2])

# Left column - Chat interface
with col1:
    # Messages area
    with st.container():
        st.markdown('<div class="chat-messages">', unsafe_allow_html=True)
        for message in st.session_state.messages:
            message_class = "user-message" if message["role"] == "user" else "assistant-message"
            st.markdown(
                f'<div class="message {message_class}">{message["content"]}</div>',
                unsafe_allow_html=True
            )
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Input area
    st.markdown('<div class="chat-input">', unsafe_allow_html=True)
    with st.form(key="chat_form", clear_on_submit=True):
        user_input = st.text_input("Message", 
                                 placeholder="Type your scheduling request...", 
                                 label_visibility="collapsed",
                                 key="user_message")
        submit = st.form_submit_button("Send")
        
        
        if submit and user_input:
            add_message("user", user_input)
            
            # Simulate assistant response
            if "study" in user_input.lower() and "10 hours" in user_input.lower():
                response = "I've found 10 hours for your study sessions. I've added them to your calendar on Monday (2-4 PM), Tuesday (3-5 PM), Wednesday (1-3 PM), Thursday (2-4 PM), and Friday (3-5 PM)."
            else:
                response = "I'll help you schedule that. What days and times would work best for you?"
            
            add_message("assistant", response)
            st.rerun()
    
    st.markdown('</div></div>', unsafe_allow_html=True)

# Right column - Calendar view
with col2:
    st.markdown("### Weekly Schedule")
    
    # Calendar navigation
    col_prev, col_title, col_next = st.columns([1, 3, 1])
    with col_prev:
        if st.button("← Previous Week"):
            st.session_state.current_week_offset -= 1
            st.rerun()
    with col_title:
        week_display = f"{start_of_week.strftime('%b %d')} - {(start_of_week + datetime.timedelta(days=6)).strftime('%b %d, %Y')}"
        st.markdown(f"<h3 style='text-align: center;'>{week_display}</h3>", unsafe_allow_html=True)
    with col_next:
        if st.button("Next Week →"):
            st.session_state.current_week_offset += 1
            st.rerun()
    
    # Calendar display
    st.markdown('<div class="calendar-container">', unsafe_allow_html=True)
    
    # Day headers with dynamic dates
    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    cols = st.columns(7)
    for i, day in enumerate(days_of_week):
        with cols[i]:
            date = start_of_week + datetime.timedelta(days=i)
            st.markdown(f'<div class="calendar-header">{day}<br>{date.strftime("%m/%d")}</div>', unsafe_allow_html=True)
    
    # Time slots (8 AM to 6 PM)
    for hour in range(0, 25):
        st.markdown('<div style="display: flex; width: 100%;">', unsafe_allow_html=True)
        
        # Time column
        st.markdown(f'<div style="width: 50px; text-align: right; padding-right: 10px;">{hour}:00</div>', unsafe_allow_html=True)
        
        # Day columns
        for day_idx in range(7):
            current_date = start_of_week + datetime.timedelta(days=day_idx)
            day_events = [e for e in events if e['date'] == current_date and 
                          e['start_time'].hour <= hour < e['end_time'].hour]
            
            event_html = ""
            for event in day_events:
                event_html += f'<div class="event" style="background-color: {event["color"]}">{event["subject"]}</div>'
            
            st.markdown(f'<div class="time-slot" style="flex: 1;">{event_html}</div>', unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

# Add a notification area for recently scheduled events
st.markdown("""
<div style="margin-top: 20px; padding: 10px; background-color: #e8f0fe; border-radius: 5px;">
    <strong>Recently Scheduled:</strong> 10 hours of study time added for next week!
</div>
""", unsafe_allow_html=True)