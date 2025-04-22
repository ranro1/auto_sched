import json
import re
from datetime import datetime, timedelta
import google.generativeai as genai
import os
from google_calendar import add_event_to_calendar, get_week_events

def find_matching_events(calendar_service, event_details):
    """Find events that match the given criteria and return detailed information."""
    try:
        # Get events for the next 30 days to ensure we catch all relevant events
        start_date = datetime.now()
        end_date = start_date + timedelta(days=30)
        
        events = calendar_service.events().list(
            calendarId='primary',
            timeMin=start_date.isoformat() + 'Z',
            timeMax=end_date.isoformat() + 'Z',
            singleEvents=True,
            orderBy='startTime'
        ).execute().get('items', [])
        
        matching_events = []
        
        for event in events:
            matches = True
            
            # Check title match
            if 'original_title' in event_details:
                if event_details['original_title'].lower() not in event['summary'].lower():
                    matches = False
            
            # Check date match if provided
            if matches and 'date' in event_details:
                event_start = datetime.fromisoformat(event['start'].get('dateTime', event['start'].get('date')).replace('Z', '+00:00'))
                if event_start.date() != datetime.strptime(event_details['date'], '%Y-%m-%d').date():
                    matches = False
            
            # Check day match if provided
            if matches and 'day' in event_details:
                event_start = datetime.fromisoformat(event['start'].get('dateTime', event['start'].get('date')).replace('Z', '+00:00'))
                if event_start.strftime('%a').upper() != event_details['day']:
                    matches = False
            
            # Check time match if provided
            if matches and 'time' in event_details:
                event_start = datetime.fromisoformat(event['start'].get('dateTime', event['start'].get('date')).replace('Z', '+00:00'))
                try:
                    time_obj = datetime.strptime(event_details['time'], '%I:%M %p')
                except ValueError:
                    try:
                        time_obj = datetime.strptime(event_details['time'], '%I %p')
                    except ValueError:
                        continue
                
                if event_start.time().hour != time_obj.time().hour or event_start.time().minute != time_obj.time().minute:
                    matches = False
            
            if matches:
                event_start = datetime.fromisoformat(event['start'].get('dateTime', event['start'].get('date')).replace('Z', '+00:00'))
                event_end = datetime.fromisoformat(event['end'].get('dateTime', event['end'].get('date')).replace('Z', '+00:00'))
                
                matching_events.append({
                    'id': event['id'],
                    'title': event['summary'],
                    'start': event_start,
                    'end': event_end,
                    'duration': int((event_end - event_start).total_seconds() / 60)
                })
        
        return matching_events
    except Exception as e:
        raise Exception(f"Error finding matching events: {str(e)}")

def get_events_for_day(calendar_service, day=None, date=None):
    """Get all events for a specific day or date."""
    try:
        if date:
            start_date = datetime.strptime(date, '%Y-%m-%d')
        else:
            # Find the nearest occurrence of the specified day
            today = datetime.now()
            days_ahead = (['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'].index(day) - today.weekday()) % 7
            if days_ahead == 0 and today.hour >= 12:  # If it's past noon on the specified day, show next week
                days_ahead = 7
            start_date = today + timedelta(days=days_ahead)
        
        end_date = start_date + timedelta(days=1)
        
        events = calendar_service.events().list(
            calendarId='primary',
            timeMin=start_date.isoformat() + 'Z',
            timeMax=end_date.isoformat() + 'Z',
            singleEvents=True,
            orderBy='startTime'
        ).execute().get('items', [])
        
        formatted_events = []
        for event in events:
            event_start = datetime.fromisoformat(event['start'].get('dateTime', event['start'].get('date')).replace('Z', '+00:00'))
            event_end = datetime.fromisoformat(event['end'].get('dateTime', event['end'].get('date')).replace('Z', '+00:00'))
            
            formatted_events.append({
                'id': event['id'],
                'title': event['summary'],
                'start': event_start,
                'end': event_end,
                'duration': int((event_end - event_start).total_seconds() / 60)
            })
        
        return formatted_events
    except Exception as e:
        raise Exception(f"Error getting events for day: {str(e)}")

def format_event_details(events):
    """Format event details for user-friendly display."""
    if not events:
        return "No events found matching your criteria."
    
    details = "I found the following matching events:\n\n"
    for i, event in enumerate(events, 1):
        # Convert duration to hours and minutes
        hours = event['duration'] // 60
        minutes = event['duration'] % 60
        duration_str = ""
        if hours > 0:
            duration_str += f"{hours} hour{'s' if hours != 1 else ''}"
        if minutes > 0:
            if duration_str:
                duration_str += " and "
            duration_str += f"{minutes} minute{'s' if minutes != 1 else ''}"
        
        details += f"{i}. {event['title']}\n"
        details += f"   Date: {event['start'].strftime('%A, %B %d, %Y')}\n"
        details += f"   Time: {event['start'].strftime('%I:%M %p')} to {event['end'].strftime('%I:%M %p')}\n"
        details += f"   Duration: {duration_str}\n\n"
    
    return details

def parse_natural_language(prompt, model):
    """Use Gemini to parse natural language into structured event details."""
    try:
        system_prompt = """
        You are a friendly personal assistant helping with calendar management. Your task is to understand the user's intent and extract relevant information.
        
        You are able to have a conversation with the user, so the user won't feel like they are talking to a bot.
        Have a conversation with the user to understand their intent and extract relevant information.
        You can have a conversation about anything with the user, but you need to push towards one of the following actions:
        1. CREATE: Create a new event
        2. EDIT: Modify an existing event
        3. DELETE: Remove an existing event
        4. VIEW: View events for a specific day/date
        5. UNKNOWN: Ask for clarification if the intent is unclear
        
        For each action, extract the following information:
        - action: One of CREATE, EDIT, DELETE, VIEW, or UNKNOWN
        - title: The event title/description
        - day: The day of the week (Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday) if specified
        - date: The date in format YYYY-MM-DD if specified
        - time: The time in 12-hour format with AM/PM (e.g., "05:00 PM"). It can also be in 24-hour format (e.g., "17:00").
        - duration: Duration in minutes (default to 30 if not specified) or in hours (e.g., "1 hour", "2 hours", "30 minutes", "45 minutes")
        - original_title: For EDIT/DELETE actions, the original event title to identify the event
        - new_title: For EDIT action, the new title if specified
        - clarification: For UNKNOWN action, what information is missing
        
        IMPORTANT: 
        - For EDIT and DELETE actions, you MUST have enough information to uniquely identify the event.
        - For VIEW action, if only a day is specified, assume the nearest occurrence of that day.
        - If you're not sure which event the user is referring to, set action to UNKNOWN and provide clarification.
        - If the user is just having a conversation and not requesting any calendar action, set action to UNKNOWN and provide a conversational response.
        
        Example outputs:
        For creating an event:
        {
            "action": "CREATE",
            "title": "Call with John",
            "day": "Monday",
            "time": "05:00 PM",
            "duration": 30
        }
        
        For viewing events:
        {
            "action": "VIEW",
            "day": "Thursday"
        }
        
        For editing an event with complete information:
        {
            "action": "EDIT",
            "original_title": "Team Meeting",
            "new_title": "Team Standup",
            "day": "Wednesday",
            "time": "10:00 AM",
            "duration": 60
        }
        
        For deleting an event with complete information:
        {
            "action": "DELETE",
            "original_title": "Call with John",
            "day": "Monday",
            "time": "05:00 PM"
        }
        
        For unclear requests:
        {
            "action": "UNKNOWN",
            "clarification": "I need more information to identify the event. Please provide the exact date and time of the event you want to modify."
        }
        
        For general conversation:
        {
            "action": "UNKNOWN",
            "clarification": "I'm here to help with your calendar and have a friendly chat. What would you like to talk about?"
        }
        """
        
        response = model.generate_content(f"{system_prompt}\n\nText: {prompt}")
        
        try:
            json_str = response.text[response.text.find('{'):response.text.rfind('}')+1]
            event_details = json.loads(json_str)
            
            # Validate required fields based on action
            if event_details['action'] == 'CREATE':
                if not all(k in event_details for k in ['title', 'time']):
                    raise ValueError("Missing required fields for creating an event")
            elif event_details['action'] in ['EDIT', 'DELETE']:
                if not all(k in event_details for k in ['original_title']):
                    raise ValueError("Missing original event title")
                if not any(k in event_details for k in ['date', 'day', 'time']):
                    event_details['action'] = 'UNKNOWN'
                    event_details['clarification'] = "I need more information to identify the event. Please provide the date and time of the event you want to modify."
            elif event_details['action'] == 'VIEW':
                if not any(k in event_details for k in ['date', 'day']):
                    event_details['action'] = 'UNKNOWN'
                    event_details['clarification'] = "Please specify which day or date you want to view events for."
            
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
        elif event_details['action'] == 'VIEW':
            events = get_events_for_day(calendar_service, event_details.get('day'), event_details.get('date'))
            if not events:
                return None, None, None, "You have no events scheduled for this day."
            return None, None, None, format_event_details(events)
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
        # Find matching events
        matching_events = find_matching_events(calendar_service, event_details)
        
        if not matching_events:
            return None, None, None, "I couldn't find any events matching your description."
        
        if len(matching_events) > 1:
            return None, None, None, format_event_details(matching_events) + "\nPlease specify which event you want to edit by providing its number or more specific details."
        
        # Get the event to edit
        event_to_edit = matching_events[0]
        
        # Prepare updated event details
        updated_event = {
            'summary': event_details.get('new_title', event_to_edit['title'])
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
        # Find matching events
        matching_events = find_matching_events(calendar_service, event_details)
        
        if not matching_events:
            return None, None, None, "I couldn't find any events matching your description."
        
        if len(matching_events) > 1:
            return None, None, None, format_event_details(matching_events) + "\nPlease specify which event you want to delete by providing its number or more specific details."
        
        # Get the event to delete
        event_to_delete = matching_events[0]
        
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