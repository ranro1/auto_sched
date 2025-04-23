import json
import re
from datetime import datetime, timedelta
import google.generativeai as genai
import os
from google_calendar import add_event_to_calendar, get_week_events

def parse_natural_language(prompt, model):
    """Use Gemini to parse natural language into structured event details."""
    try:
        # Create a prompt for Gemini to extract event details
        system_prompt = """
        You are a friendly personal assistant helping with calendar management. Your task is to understand the user's intent and extract relevant information.
        
        Possible actions:
        1. CREATE: Create a new event
        2. EDIT: Modify an existing event
        3. DELETE: Remove an existing event
        4. UNKNOWN: Ask for clarification if the intent is unclear
        
        For each action, extract the following information:
        - action: One of CREATE, EDIT, DELETE, or UNKNOWN
        - title: The event title/description
        - day: The day of the week (MON, TUE, WED, THU, FRI, SAT, SUN) if specified
        - date: The date in format YYYY-MM-DD if specified
        - time: The time in 12-hour format with AM/PM (e.g., "05:00 PM")
        - duration: Duration in minutes (default to 30 if not specified)
        - original_title: For EDIT/DELETE actions, the original event title to identify the event
        - new_title: For EDIT action, the new title if specified
        - clarification: For UNKNOWN action, what information is missing
        
        Example outputs:
        For creating an event:
        {
            "action": "CREATE",
            "title": "Call with John",
            "day": "MON",
            "time": "05:00 PM",
            "duration": 30
        }
        
        For editing an event:
        {
            "action": "EDIT",
            "original_title": "Team Meeting",
            "new_title": "Team Standup",
            "day": "WED",
            "time": "10:00 AM",
            "duration": 60
        }
        
        For deleting an event:
        {
            "action": "DELETE",
            "original_title": "Call with John"
        }
        
        For unclear requests:
        {
            "action": "UNKNOWN",
            "clarification": "I need to know which event you want to modify and what changes you'd like to make."
        }
        """
        
        # Get structured response from Gemini
        response = model.generate_content(f"{system_prompt}\n\nText: {prompt}")
        
        # Extract JSON from response
        try:
            # Find JSON in the response
            json_str = response.text[response.text.find('{'):response.text.rfind('}')+1]
            event_details = json.loads(json_str)
            
            # Validate required fields based on action
            if event_details['action'] == 'CREATE':
                if not all(k in event_details for k in ['title', 'time']):
                    raise ValueError("Missing required fields for creating an event")
            elif event_details['action'] == 'EDIT':
                if not all(k in event_details for k in ['original_title']):
                    raise ValueError("Missing original event title for editing")
            elif event_details['action'] == 'DELETE':
                if not all(k in event_details for k in ['original_title']):
                    raise ValueError("Missing event title for deletion")
            
            # Standardize time format if present
            if 'time' in event_details:
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
            if 'duration' not in event_details and event_details['action'] == 'CREATE':
                event_details['duration'] = 30
            
            return event_details
        except json.JSONDecodeError:
            raise ValueError("Could not parse event details from response")
    except Exception as e:
        raise Exception(f"Error parsing natural language: {str(e)}")

def handle_calendar_action(event_details, calendar_service):
    """Handle different calendar actions based on the parsed event details."""
    try:
        if event_details['action'] == 'CREATE':
            return schedule_event(event_details, calendar_service)
        elif event_details['action'] == 'EDIT':
            return edit_event(event_details, calendar_service)
        elif event_details['action'] == 'DELETE':
            return delete_event(event_details, calendar_service)
        elif event_details['action'] == 'UNKNOWN':
            return None, None, None, event_details['clarification']
    except Exception as e:
        raise Exception(f"Error handling calendar action: {str(e)}")

def schedule_event(event_details, calendar_service):
    """Schedule an event in Google Calendar using event details."""
    try:
        # Convert time to 24-hour format
        try:
            time_obj = datetime.strptime(event_details['time'], '%I:%M %p')
        except ValueError:
            try:
                time_obj = datetime.strptime(event_details['time'], '%I %p')
            except ValueError:
                raise ValueError("Invalid time format. Please use format like '05:00 PM'")
        
        # Calculate event date based on whether day or date is provided
        if 'date' in event_details:
            try:
                if len(event_details['date'].split('-')) == 2:
                    current_year = datetime.now().year
                    event_details['date'] = f"{current_year}-{event_details['date']}"
                
                event_date = datetime.strptime(event_details['date'], '%Y-%m-%d')
                
                if event_date < datetime.now():
                    event_date = event_date.replace(year=datetime.now().year + 1)
            except ValueError:
                raise ValueError("Invalid date format. Please use YYYY-MM-DD or MM-DD format")
        else:
            start_date = datetime.now() - timedelta(days=datetime.now().weekday())
            day_offset = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'].index(event_details['day'])
            event_date = start_date + timedelta(days=day_offset)
            
            if event_date < datetime.now():
                event_date += timedelta(days=7)
        
        start_datetime = datetime.combine(event_date.date(), time_obj.time())
        start_datetime = start_datetime.replace(tzinfo=None)
        end_datetime = start_datetime + timedelta(minutes=event_details['duration'])
        
        event_data = {
            'Task': event_details['title'],
            'Start DateTime': start_datetime,
            'End DateTime': end_datetime,
            'ColorId': '1'
        }
        
        event_link = add_event_to_calendar(calendar_service, event_data)
        return start_datetime, end_datetime, event_link, None
    except Exception as e:
        raise Exception(f"Error scheduling event: {str(e)}")

def edit_event(event_details, calendar_service):
    """Edit an existing event in Google Calendar."""
    try:
        # Find the event to edit
        events = get_week_events(calendar_service, datetime.now())
        event_to_edit = None
        
        for event in events:
            if event['summary'].lower() == event_details['original_title'].lower():
                event_to_edit = event
                break
        
        if not event_to_edit:
            raise ValueError(f"Could not find event with title: {event_details['original_title']}")
        
        # Prepare updated event details
        updated_event = {
            'summary': event_details.get('new_title', event_to_edit['summary'])
        }
        
        if 'time' in event_details:
            try:
                time_obj = datetime.strptime(event_details['time'], '%I:%M %p')
            except ValueError:
                try:
                    time_obj = datetime.strptime(event_details['time'], '%I %p')
                except ValueError:
                    raise ValueError("Invalid time format. Please use format like '05:00 PM'")
            
            if 'date' in event_details:
                event_date = datetime.strptime(event_details['date'], '%Y-%m-%d')
            else:
                start_date = datetime.now() - timedelta(days=datetime.now().weekday())
                day_offset = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'].index(event_details['day'])
                event_date = start_date + timedelta(days=day_offset)
            
            start_datetime = datetime.combine(event_date.date(), time_obj.time())
            start_datetime = start_datetime.replace(tzinfo=None)
            end_datetime = start_datetime + timedelta(minutes=event_details.get('duration', 30))
            
            updated_event.update({
                'start': {
                    'dateTime': start_datetime.isoformat(),
                    'timeZone': 'America/New_York'
                },
                'end': {
                    'dateTime': end_datetime.isoformat(),
                    'timeZone': 'America/New_York'
                }
            })
        
        # Update the event
        updated_event = calendar_service.events().update(
            calendarId='primary',
            eventId=event_to_edit['id'],
            body=updated_event
        ).execute()
        
        return None, None, updated_event.get('htmlLink'), None
    except Exception as e:
        raise Exception(f"Error editing event: {str(e)}")

def delete_event(event_details, calendar_service):
    """Delete an event from Google Calendar."""
    try:
        # Find the event to delete
        events = get_week_events(calendar_service, datetime.now())
        event_to_delete = None
        
        for event in events:
            if event['summary'].lower() == event_details['original_title'].lower():
                event_to_delete = event
                break
        
        if not event_to_delete:
            raise ValueError(f"Could not find event with title: {event_details['original_title']}")
        
        # Delete the event
        calendar_service.events().delete(
            calendarId='primary',
            eventId=event_to_delete['id']
        ).execute()
        
        return None, None, None, None
    except Exception as e:
        raise Exception(f"Error deleting event: {str(e)}")

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