import json
from datetime import datetime, timedelta
import google.generativeai as genai
import os
from dotenv import load_dotenv
from google_calendar import get_google_calendar_service, add_event_to_calendar
import streamlit as st

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

def schedule_event(event_details, calendar_service):
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
        event_link = add_event_to_calendar(calendar_service, event_data)
        return start_datetime, end_datetime, event_link
    except Exception as e:
        raise Exception(f"Error scheduling event: {str(e)}")

def add_message(role, content):
    """Add a message to the chat history."""
    st.session_state.messages.append({"role": role, "content": content}) 