from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import os.path
import pickle
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st

# If modifying these scopes, delete the file token.pickle.
SCOPES = [
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/calendar.readonly'
]

def get_google_calendar_service():
    """Get Google Calendar service with proper authentication."""
    creds = None
    # The file token.pickle stores the user's access and refresh tokens
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                st.error(f"Error refreshing token: {str(e)}")
                os.remove('token.pickle')
                creds = None
        
        if not creds:
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES)
                # Use a fixed port for OAuth flow
                creds = flow.run_local_server(port=8080)
                # Save the credentials for the next run
                with open('token.pickle', 'wb') as token:
                    pickle.dump(creds, token)
            except Exception as e:
                st.error(f"Error during authentication: {str(e)}")
                st.error("Please make sure you have properly configured the OAuth consent screen in Google Cloud Console.")
                st.error("1. Go to Google Cloud Console > APIs & Services > OAuth consent screen")
                st.error("2. Set User Type to 'External'")
                st.error("3. Add your email as a test user")
                st.error("4. Add the following scopes:")
                st.error("   - https://www.googleapis.com/auth/calendar.events")
                st.error("   - https://www.googleapis.com/auth/calendar.readonly")
                st.stop()

    return build('calendar', 'v3', credentials=creds)

def add_event_to_calendar(service, event_details):
    """Add an event to Google Calendar."""
    event = {
        'summary': event_details['Task'],
        'start': {
            'dateTime': event_details['Start DateTime'].isoformat(),
            'timeZone': 'America/New_York',  # Fixed timezone that works with Google Calendar
        },
        'end': {
            'dateTime': event_details['End DateTime'].isoformat(),
            'timeZone': 'America/New_York',  # Fixed timezone that works with Google Calendar
        },
        'colorId': event_details.get('ColorId', '1'),  # Default blue color
    }
    
    event = service.events().insert(calendarId='primary', body=event).execute()
    return event.get('htmlLink')

def get_week_events(service, start_date):
    """Get all events for a specific week."""
    end_date = start_date + timedelta(days=7)
    
    events_result = service.events().list(
        calendarId='primary',
        timeMin=start_date.isoformat() + 'Z',
        timeMax=end_date.isoformat() + 'Z',
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    
    return events_result.get('items', [])

def convert_to_dataframe(events):
    """Convert Google Calendar events to pandas DataFrame."""
    events_list = []
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        end = event['end'].get('dateTime', event['end'].get('date'))
        
        events_list.append({
            'Task': event['summary'],
            'Start Time': datetime.fromisoformat(start.replace('Z', '+00:00')).strftime('%H:%M'),
            'End Time': datetime.fromisoformat(end.replace('Z', '+00:00')).strftime('%H:%M'),
            'Day': datetime.fromisoformat(start.replace('Z', '+00:00')).strftime('%a').upper(),
            'Color': f"#{event.get('colorId', '1')}",
            'Status': 'Pending'
        })
    
    return pd.DataFrame(events_list) 