import json
import re
from datetime import datetime, timedelta
import google.generativeai as genai
import os
from google_calendar import add_event_to_calendar, get_week_events
import pytz
from difflib import SequenceMatcher
import random


def validate_event_details(event_details):
    """
    Validate and clean event details before processing.
    Raises InvalidInputError with specific message if validation fails.
    Returns cleaned and standardized event details.
    """
    # Create a clean copy to work with
    validated = event_details.copy()
    
    # Check required fields based on action type
    if 'action' not in validated:
        raise InvalidInputError("No action specified in event details")
    
    # Validate CREATE action fields
    if validated['action'] == 'CREATE':
        if 'title' not in validated or not validated['title'].strip():
            raise InvalidInputError("Event title is required")
        
        # Clean title
        validated['title'] = validated['title'].strip()
        
        # Check for time information
        has_time_info = any(key in validated for key in ['time', 'day', 'date'])
        if not has_time_info:
            raise InvalidInputError("Please specify when this event should occur (time, day, or date)")
            
        # Validate and standardize time if present
        if 'time' in validated:
            validated['time'] = standardize_time_format(validated['time'])
            
        # Validate and standardize date if present
        if 'date' in validated:
            validated['date'] = standardize_date_format(validated['date'])
            
        # Validate and standardize day if present
        if 'day' in validated:
            validated['day'] = standardize_day_format(validated['day'])
            
        # Set default duration if not specified
        if 'duration' not in validated:
            validated['duration'] = 30  # Default 30 minutes
        else:
            # Ensure duration is an integer
            try:
                validated['duration'] = int(validated['duration'])
                if validated['duration'] <= 0:
                    validated['duration'] = 30  # Default if invalid
            except (ValueError, TypeError):
                validated['duration'] = 30  # Default if conversion fails
    
    # Validate EDIT action fields
    elif validated['action'] == 'EDIT':
        if 'original_title' not in validated or not validated['original_title'].strip():
            raise InvalidInputError("Please specify which event you want to edit")
            
        # Need at least one identifier beyond title
        identifiers = [key for key in ['date', 'day', 'time'] if key in validated]
        if not identifiers:
            raise InvalidInputError("I need more information to identify the event you want to edit. Please include date, day, or time.")
            
        # Clean any provided fields
        if 'time' in validated:
            validated['time'] = standardize_time_format(validated['time'])
        if 'date' in validated:
            validated['date'] = standardize_date_format(validated['date'])
        if 'day' in validated:
            validated['day'] = standardize_day_format(validated['day'])
            
        # Ensure new title is valid if provided
        if 'new_title' in validated and not validated['new_title'].strip():
            raise InvalidInputError("New event title cannot be empty")
    
    # Validate DELETE action fields
    elif validated['action'] == 'DELETE':
        if 'original_title' not in validated or not validated['original_title'].strip():
            raise InvalidInputError("Please specify which event you want to delete")
            
        # Need at least one identifier beyond title
        identifiers = [key for key in ['date', 'day', 'time'] if key in validated]
        if not identifiers:
            raise InvalidInputError("I need more information to identify the event you want to delete. Please include date, day, or time.")
            
        # Clean any provided fields
        if 'time' in validated:
            validated['time'] = standardize_time_format(validated['time'])
        if 'date' in validated:
            validated['date'] = standardize_date_format(validated['date'])
        if 'day' in validated:
            validated['day'] = standardize_day_format(validated['day'])
    
    # Validate VIEW action fields
    elif validated['action'] == 'VIEW':
        if not any(key in validated for key in ['date', 'day']):
            raise InvalidInputError("Please specify which day or date you want to view events for")
            
        # Clean any provided fields
        if 'date' in validated:
            validated['date'] = standardize_date_format(validated['date'])
        if 'day' in validated:
            validated['day'] = standardize_day_format(validated['day'])
    
    # Unknown action
    elif validated['action'] == 'UNKNOWN':
        if 'clarification' not in validated:
            validated['clarification'] = "I'm not sure what you want to do with your calendar. Could you be more specific?"
    
    # Invalid action
    else:
        raise InvalidInputError(f"Unknown action type: {validated['action']}")
    
    return validated

def standardize_time_format(time_str):
    """
    Standardize time format to '05:00 PM' format.
    Accepts various input formats like '5pm', '5:00 pm', '17:00', etc.
    """
    time_str = time_str.strip().upper()
    
    # Check for 24-hour format
    hour24_match = re.match(r'^(\d{1,2}):?(\d{2})$', time_str)
    if hour24_match:
        hour = int(hour24_match.group(1))
        minute = int(hour24_match.group(2)) if hour24_match.group(2) else 0
        
        if hour >= 24 or minute >= 60:
            raise InvalidInputError(f"Invalid time: {time_str}")
            
        # Convert to 12-hour format
        period = "AM" if hour < 12 else "PM"
        hour12 = hour % 12
        if hour12 == 0:
            hour12 = 12
            
        return f"{hour12:02d}:{minute:02d} {period}"
    
    # Check for 12-hour format with or without minutes
    hour12_match = re.match(r'^(\d{1,2})(?::(\d{2}))?\s*(AM|PM|A|P)?$', time_str)
    if hour12_match:
        hour = int(hour12_match.group(1))
        minute = int(hour12_match.group(2)) if hour12_match.group(2) else 0
        period = hour12_match.group(3) or "PM"  # Default to PM if not specified
        
        if period in ["A", "P"]:
            period = "AM" if period == "A" else "PM"
            
        if hour > 12 or minute >= 60:
            raise InvalidInputError(f"Invalid time: {time_str}")
            
        if hour == 0:
            hour = 12
            
        return f"{hour:02d}:{minute:02d} {period}"
    
    # If all parsing attempts fail
    raise InvalidInputError(f"Could not parse time: {time_str}")

def standardize_date_format(date_str):
    """
    Standardize date format to 'YYYY-MM-DD'.
    Accepts various input formats including relative time expressions.
    """
    # Remove whitespace and convert to lowercase
    date_str = date_str.strip().lower()
    
    # Get current date in user's timezone
    user_timezone = get_user_timezone()
    local_tz = pytz.timezone(user_timezone)
    today = datetime.now(local_tz)
    
    # Handle relative time expressions
    relative_dates = {
        'today': 0,
        'tomorrow': 1,
        'yesterday': -1,
        'next week': 7,
        'last week': -7,
        'next month': 30,
        'last month': -30
    }
    
    # Check for "in X days/weeks/months" format
    in_pattern = re.compile(r'in\s+(\d+)\s+(day|week|month)s?')
    in_match = in_pattern.match(date_str)
    if in_match:
        number = int(in_match.group(1))
        unit = in_match.group(2)
        if unit == 'day':
            days = number
        elif unit == 'week':
            days = number * 7
        else:  # month
            days = number * 30
        return (today + timedelta(days=days)).strftime('%Y-%m-%d')
    
    # Check for "X days/weeks/months ago" format
    ago_pattern = re.compile(r'(\d+)\s+(day|week|month)s?\s+ago')
    ago_match = ago_pattern.match(date_str)
    if ago_match:
        number = int(ago_match.group(1))
        unit = ago_match.group(2)
        if unit == 'day':
            days = -number
        elif unit == 'week':
            days = -number * 7
        else:  # month
            days = -number * 30
        return (today + timedelta(days=days)).strftime('%Y-%m-%d')
    
    # Check for simple relative dates
    if date_str in relative_dates:
        return (today + timedelta(days=relative_dates[date_str])).strftime('%Y-%m-%d')
    
    # Try different date formats
    formats = [
        '%Y-%m-%d',  # 2023-12-31
        '%m/%d/%Y',  # 12/31/2023
        '%m-%d-%Y',  # 12-31-2023
        '%m/%d',     # 12/31
        '%m-%d',     # 12-31
        '%B %d',     # December 31
        '%b %d',     # Dec 31
        '%d %B',     # 31 December
        '%d %b'      # 31 Dec
    ]
    
    # Try each format
    for fmt in formats:
        try:
            parsed_date = datetime.strptime(date_str, fmt)
            
            # Set year to current year if not specified
            if '%Y' not in fmt:
                current_year = today.year
                
                # If the resulting date is in the past, and it's near the end of year,
                # assume it's for next year
                if parsed_date.replace(year=current_year) < today and today.month > 10:
                    parsed_date = parsed_date.replace(year=current_year + 1)
                else:
                    parsed_date = parsed_date.replace(year=current_year)
            
            return parsed_date.strftime('%Y-%m-%d')
        except ValueError:
            continue
    
    # If all parsing attempts fail
    raise InvalidInputError(f"Could not parse date: {date_str}")

def standardize_day_format(day_str):
    """
    Standardize day format to 3-letter uppercase code (MON, TUE, etc.)
    """
    day_map = {
        'MONDAY': 'MON', 'TUESDAY': 'TUE', 'WEDNESDAY': 'WED',
        'THURSDAY': 'THU', 'FRIDAY': 'FRI', 'SATURDAY': 'SAT', 'SUNDAY': 'SUN',
        'MON': 'MON', 'TUE': 'TUE', 'WED': 'WED', 'THU': 'THU',
        'FRI': 'FRI', 'SAT': 'SAT', 'SUN': 'SUN',
        'M': 'MON', 'T': 'TUE', 'W': 'WED', 'TH': 'THU', 'F': 'FRI', 
        'SA': 'SAT', 'SU': 'SUN'
    }
    
    standardized = day_map.get(day_str.upper())
    if not standardized:
        raise InvalidInputError(f"Invalid day: {day_str}")
    
    return standardized

class CalendarError(Exception):
    """Base class for calendar operation errors"""
    pass

class AuthenticationError(CalendarError):
    """Raised when there are authentication issues with Google Calendar"""
    pass

class EventNotFoundError(CalendarError):
    """Raised when an event cannot be found"""
    pass

class InvalidInputError(CalendarError):
    """Raised when input data is invalid or incomplete"""
    pass

class APILimitError(CalendarError):
    """Raised when Google API limits are reached"""
    pass

class ParsingError(CalendarError):
    """Raised when natural language parsing fails"""
    pass

def handle_calendar_action(event_details, calendar_service):
    """Handle calendar actions with support for multiple events and dependencies."""
    try:
        if event_details['action'] == 'CREATE':
            # For recurring events, create multiple events
            if event_details.get('recurring'):
                # Get the next 7 days
                from datetime import datetime, timedelta
                today = datetime.now()
                events_created = 0
                
                for i in range(7):
                    current_date = today + timedelta(days=i)
                    # Skip if it's a specific day and doesn't match
                    if 'day' in event_details:
                        if current_date.strftime('%a').upper()[:3] != event_details['day']:
                            continue
                    
                    # Create event for this day
                    event_copy = event_details.copy()
                    event_copy['date'] = current_date.strftime('%Y-%m-%d')
                    del event_copy['recurring']
                    if 'day' in event_copy:
                        del event_copy['day']
                    
                    try:
                        success, _ = schedule_event(event_copy, calendar_service)
                        if success:
                            events_created += 1
                    except Exception as e:
                        print(f"Warning: Failed to create recurring event for {current_date}: {str(e)}")
                        continue
                
                if events_created == 0:
                    return False, "Failed to create any recurring events"
                
                # Return a simple summary message
                return True, f"Created recurring event '{event_details['title']}' for the next 7 days at {event_details['time']}"
            
            # For single events
            return schedule_event(event_details, calendar_service)
            
        elif event_details['action'] == 'EDIT':
            return edit_event(event_details, calendar_service)
            
        elif event_details['action'] == 'DELETE':
            return delete_event(event_details, calendar_service)
            
        elif event_details['action'] == 'VIEW':
            events = get_events_for_day(calendar_service, event_details.get('day'), event_details.get('date'))
            if not events:
                return True, "You have no events scheduled for this day."
            return True, format_event_details(events)
            
        elif event_details['action'] == 'UNKNOWN':
            return False, event_details['clarification']
            
    except Exception as e:
        return False, f"Error handling calendar action: {str(e)}"

def calculate_title_similarity(title1, title2):
    """
    Calculate similarity between two event titles using SequenceMatcher.
    Returns a score between 0 and 1, where 1 is a perfect match.
    """
    return SequenceMatcher(None, title1.lower(), title2.lower()).ratio()

def find_matching_events(calendar_service, event_details, user_timezone=None, similarity_threshold=0.6):
    """
    Find events that match the given criteria with improved matching logic.
    Includes fuzzy matching for titles and more flexible time matching.
    """
    try:
        # Get user timezone
        if user_timezone is None:
            user_timezone = get_user_timezone()
            
        # Calculate search range - look ahead up to 90 days
        start_date = datetime.now(pytz.timezone(user_timezone))
        end_date = start_date + timedelta(days=90)
        
        # Request events from Calendar API
        events_result = calendar_service.events().list(
            calendarId='primary',
            timeMin=start_date.isoformat(),
            timeMax=end_date.isoformat(),
            singleEvents=True,
            orderBy='startTime',
            maxResults=100  # Increase to get more potential matches
        ).execute()
        
        events = events_result.get('items', [])
        matching_events = []
        
        for event in events:
            # Skip events without summaries
            if 'summary' not in event:
                continue
                
            event_score = 0
            potential_match = True
            
            # Title matching with similarity score
            if 'original_title' in event_details:
                similarity = calculate_title_similarity(
                    event_details['original_title'], 
                    event['summary']
                )
                
                if similarity < similarity_threshold:
                    potential_match = False
                else:
                    # Add to score based on title similarity
                    event_score += similarity
            
            if not potential_match:
                continue
                
            # Parse event start/end times
            event_start = parse_datetime_from_api(
                event['start'].get('dateTime', event['start'].get('date')),
                event['start'].get('timeZone', user_timezone)
            )
            
            event_end = parse_datetime_from_api(
                event['end'].get('dateTime', event['end'].get('date')),
                event['end'].get('timeZone', user_timezone)
            )
            
            # Date matching
            if 'date' in event_details:
                target_date = datetime.strptime(event_details['date'], '%Y-%m-%d').date()
                if event_start.date() != target_date:
                    continue
                else:
                    event_score += 1  # Exact date match
            
            # Day of week matching
            if 'day' in event_details:
                # Convert day name to day number (0=Monday, 6=Sunday)
                day_map = {'MON': 0, 'TUE': 1, 'WED': 2, 'THU': 3, 'FRI': 4, 'SAT': 5, 'SUN': 6}
                target_day = day_map.get(event_details['day'])
                
                if event_start.weekday() != target_day:
                    continue
                else:
                    event_score += 0.8  # Day match (slightly less valuable than exact date)
            
            # Time matching - more flexible with a time window
            if 'time' in event_details:
                try:
                    # Try different time formats
                    time_formats = ['%I:%M %p', '%I %p', '%H:%M']
                    parsed_time = None
                    
                    for fmt in time_formats:
                        try:
                            parsed_time = datetime.strptime(event_details['time'], fmt)
                            break
                        except ValueError:
                            continue
                            
                    if not parsed_time:
                        raise ValueError(f"Could not parse time: {event_details['time']}")
                    
                    # Allow for slight time differences (15 min window)
                    time_difference = abs((event_start.hour * 60 + event_start.minute) - 
                                         (parsed_time.hour * 60 + parsed_time.minute))
                    
                    if time_difference > 15:  # 15-minute window
                        continue
                    else:
                        # Score based on time closeness (1.0 for exact, less for close)
                        time_match_score = 1.0 - (time_difference / 60)  # Scale by hour
                        event_score += time_match_score
                        
                except (ValueError, TypeError) as e:
                    # If time parsing fails, don't use it as a criterion
                    pass
            
            # If we got here, it's a potential match
            # Calculate duration for the event
            duration_minutes = int((event_end - event_start).total_seconds() / 60)
            
            matching_events.append({
                'id': event['id'],
                'title': event['summary'],
                'start': event_start,
                'end': event_end,
                'duration': duration_minutes,
                'match_score': event_score,  # How well it matches the criteria
                'all_day': 'date' in event['start'] and 'date' in event['end']
            })
        
        # Sort by match score, highest first
        matching_events.sort(key=lambda x: x['match_score'], reverse=True)
        
        return matching_events
    
    except Exception as e:
        # More specific error handling
        if "invalid_grant" in str(e):
            raise Exception("Authentication error with Google Calendar. Please reconnect your account.")
        elif "quota" in str(e).lower():
            raise Exception("Google Calendar API quota exceeded. Please try again later.")
        else:
            raise Exception(f"Error finding matching events: {str(e)}")

def get_user_timezone(user_id=None):
    """
    Get the user's preferred timezone.
    In a real implementation, this would fetch from a user settings database.
    """
    # TODO: Replace with actual user preference lookup
    return 'America/New_York'

def standardize_datetime(dt, user_timezone=None):
    """
    Convert datetime to a standard format with proper timezone handling.
    If the datetime is naive (no timezone), assign the user's timezone.
    """
    if user_timezone is None:
        user_timezone = get_user_timezone()
        
    # If datetime is naive (no timezone info), assign the user's timezone
    if dt.tzinfo is None:
        local_tz = pytz.timezone(user_timezone)
        dt = local_tz.localize(dt)
    
    return dt

def format_datetime_for_api(dt, user_timezone=None):
    """
    Format datetime for Google Calendar API with proper timezone.
    """
    dt = standardize_datetime(dt, user_timezone)
    return {
        'dateTime': dt.isoformat(),
        'timeZone': user_timezone or get_user_timezone()
    }

def parse_datetime_from_api(datetime_str, timezone_str=None):
    """
    Parse datetime from Google Calendar API response.
    """
    # Handle 'Z' UTC indicator by replacing with +00:00 format
    if datetime_str.endswith('Z'):
        datetime_str = datetime_str.replace('Z', '+00:00')
    
    dt = datetime.fromisoformat(datetime_str)
    
    # If timezone is provided in the response, use it
    if timezone_str:
        timezone = pytz.timezone(timezone_str)
        dt = dt.replace(tzinfo=pytz.UTC).astimezone(timezone)
    
    return dt

def get_events_for_day(calendar_service, day=None, date=None):
    """
    Get events for a specific day or date.
    Returns a list of events.
    """
    try:
        # Get user's timezone
        user_timezone = get_user_timezone()
        local_tz = pytz.timezone(user_timezone)
        
        # Convert day to date if needed
        if day and not date:
            # Get the next occurrence of the specified day
            today = datetime.now(local_tz)
            days_ahead = (day_map[day.upper()] - today.weekday()) % 7
            if days_ahead == 0:  # If today is the specified day
                date = today.strftime('%Y-%m-%d')
            else:
                date = (today + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
        
        # Get events for the specified date
        if date:
            # Convert date string to datetime
            start_date = datetime.strptime(date, '%Y-%m-%d')
            start_date = local_tz.localize(start_date)
            end_date = start_date + timedelta(days=1)
            
            # Get events from calendar
            events_result = calendar_service.events().list(
                calendarId='primary',
                timeMin=start_date.isoformat(),
                timeMax=end_date.isoformat(),
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            return events_result.get('items', [])
            
        return []
        
    except Exception as e:
        raise CalendarError(f"Error getting events: {str(e)}")

def format_event_details(events):
    """Format event details for display with proper timezone handling."""
    if not events:
        return "No events found for this period."
    
    # Get user's timezone (America/New_York)
    user_timezone = pytz.timezone('America/New_York')
    
    # Group events by date
    events_by_date = {}
    for event in events:
        try:
            # Parse the event times
            if 'dateTime' in event['start']:
                # Parse the UTC time
                start_time = datetime.fromisoformat(event['start']['dateTime'].replace('Z', '+00:00'))
                end_time = datetime.fromisoformat(event['end']['dateTime'].replace('Z', '+00:00'))
                
                # Convert to user's timezone
                start_time = start_time.astimezone(user_timezone)
                end_time = end_time.astimezone(user_timezone)
            else:
                # Handle all-day events
                start_time = datetime.fromisoformat(event['start']['date']).replace(tzinfo=user_timezone)
                end_time = datetime.fromisoformat(event['end']['date']).replace(tzinfo=user_timezone)
            
            # Use the converted time for grouping
            event_date = start_time.date()
            if event_date not in events_by_date:
                events_by_date[event_date] = []
            events_by_date[event_date].append({
                **event,
                'start_time': start_time,
                'end_time': end_time
            })
        except Exception as e:
            print(f"Error processing event time: {str(e)}")
            continue
    
    # Format output
    details = ""
    for date, day_events in sorted(events_by_date.items()):
        # Add date header
        details += f"📅 {date.strftime('%A, %B %d, %Y')}\n\n"
        
        # Add events for this day
        for i, event in enumerate(day_events, 1):
            # Format the time display using the converted times
            if 'date' in event['start']:
                time_display = "All day"
            else:
                time_display = f"{event['start_time'].strftime('%I:%M %p')} - {event['end_time'].strftime('%I:%M %p')}"
            
            # Format duration display
            if 'date' in event['start']:
                duration_str = "All day"
            else:
                duration_minutes = int((event['end_time'] - event['start_time']).total_seconds() / 60)
                hours = duration_minutes // 60
                minutes = duration_minutes % 60
                
                if hours > 0 and minutes > 0:
                    duration_str = f"{hours} hr{'s' if hours != 1 else ''}, {minutes} min"
                elif hours > 0:
                    duration_str = f"{hours} hr{'s' if hours != 1 else ''}"
                else:
                    duration_str = f"{minutes} min"
            
            # Build event display
            details += f"{i}. {event['summary']}\n"
            details += f"   ⏰ {time_display}\n"
            details += f"   ⌛ {duration_str}\n"
            
            if event.get('location'):
                details += f"   📍 {event['location']}\n"
                
            if event.get('description'):
                details += f"   📝 {event['description']}\n"
                
            details += "\n"
    
    return details

# Add day mapping for get_events_for_day function
day_map = {
    'MON': 0, 'TUE': 1, 'WED': 2, 'THU': 3, 'FRI': 4, 'SAT': 5, 'SUN': 6
}

def parse_natural_language(prompt, model):
    """
    Parse natural language input to extract calendar actions.
    Returns a list of event details dictionaries.
    """
    system_prompt = """You are an expert calendar assistant helping with calendar operations.
Your task is to:
1. Identify the type of action requested (CREATE, EDIT, DELETE, VIEW)
2. Extract relevant details for the action

For CREATE actions, extract:
- action: "CREATE"
- title: event name/description
- date: specific date (YYYY-MM-DD) if mentioned
- day: day of week if mentioned
- time: start time
- duration: duration in minutes
- travel_time: travel duration in minutes if mentioned
- recurring: true/false if it's a daily/weekly event
- constraints: any specific constraints mentioned

For DELETE actions, extract:
- action: "DELETE"
- original_title: event title to delete
- date: specific date (YYYY-MM-DD) if mentioned
- day: day of week if mentioned
- time: specific time if mentioned

For EDIT actions, extract:
- action: "EDIT"
- original_title: current event title
- new_title: new title if mentioned
- date: specific date (YYYY-MM-DD) if mentioned
- day: day of week if mentioned
- time: new time if mentioned
- duration: new duration if mentioned

For DELETE actions, extract:
- action: "DELETE"
- original_title: event title to delete
- date: specific date (YYYY-MM-DD) if mentioned
- day: day of week if mentioned
- time: specific time if mentioned

IMPORTANT: Your response must be a valid JSON array of actions. Do not include any explanatory text.
Each action must have at least the action type and necessary identifiers.

Example output format:
[
    {
        "action": "VIEW",
        "day": "MON"
    },
    {
        "action": "CREATE",
        "title": "Math Class",
        "day": "THU",
        "time": "06:00 PM",
        "duration": 180
    }
]

Now, analyze this prompt and extract all actions. Return ONLY the JSON array:"""

    try:
        response = model.generate_content(system_prompt + "\n\n" + prompt)
        
        # Clean the response to ensure it's valid JSON
        response_text = response.text.strip()
        
        # Find the JSON array in the response
        start_idx = response_text.find('[')
        end_idx = response_text.rfind(']') + 1
        
        if start_idx == -1 or end_idx == 0:
            raise ValueError("No valid JSON array found in response")
            
        json_str = response_text[start_idx:end_idx]
        
        # Parse the JSON
        actions = json.loads(json_str)
        
        # Validate each action
        validated_actions = []
        for action in actions:
            try:
                # Ensure required fields are present based on action type
                if action['action'] == 'VIEW':
                    if not any(key in action for key in ['date', 'day']):
                        print(f"Warning: Skipping VIEW action missing date or day: {action}")
                        continue
                elif action['action'] == 'CREATE':
                    if not all(key in action for key in ['title', 'time']):
                        print(f"Warning: Skipping CREATE action missing required fields: {action}")
                        continue
                elif action['action'] == 'EDIT':
                    if 'original_title' not in action:
                        print(f"Warning: Skipping EDIT action missing original title: {action}")
                        continue
                elif action['action'] == 'DELETE':
                    if 'original_title' not in action:
                        print(f"Warning: Skipping DELETE action missing title: {action}")
                        continue
                
                # Validate the action
                validated_action = validate_event_details(action)
                validated_actions.append(validated_action)
            except InvalidInputError as e:
                print(f"Warning: Skipping invalid action: {str(e)}")
                continue
                
        return validated_actions
        
    except Exception as e:
        print(f"Error parsing natural language: {str(e)}")
        return [{
            'action': 'UNKNOWN',
            'clarification': "I'm having trouble understanding your request. Could you be more specific?"
        }]

def standardize_time_for_comparison(time_str):
    """
    Convert various time formats to a standard format for comparison.
    Returns a tuple of (hour, minute) in 24-hour format.
    """
    time_str = time_str.strip().upper()
    
    # Handle "HH:MM AM/PM" format
    time_match = re.match(r'(\d{1,2}):?(\d{2})?\s*(AM|PM)', time_str)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2)) if time_match.group(2) else 0
        period = time_match.group(3)
        
        # Convert to 24-hour format
        if period == 'PM' and hour != 12:
            hour += 12
        elif period == 'AM' and hour == 12:
            hour = 0
            
        return hour, minute
    
    # Handle "HH AM/PM" format
    time_match = re.match(r'(\d{1,2})\s*(AM|PM)', time_str)
    if time_match:
        hour = int(time_match.group(1))
        period = time_match.group(2)
        
        # Convert to 24-hour format
        if period == 'PM' and hour != 12:
            hour += 12
        elif period == 'AM' and hour == 12:
            hour = 0
            
        return hour, 0
    
    # Handle 24-hour format "HH:MM"
    time_match = re.match(r'(\d{1,2}):?(\d{2})', time_str)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        return hour, minute
    
    raise ValueError(f"Could not parse time: {time_str}")

def compare_times(time1, time2, tolerance_minutes=5):
    """
    Compare two times with a tolerance.
    time1 and time2 should be tuples of (hour, minute).
    """
    hour1, minute1 = time1
    hour2, minute2 = time2
    
    # Convert to minutes since midnight
    total_minutes1 = hour1 * 60 + minute1
    total_minutes2 = hour2 * 60 + minute2
    
    # Calculate difference
    diff_minutes = abs(total_minutes1 - total_minutes2)
    
    return diff_minutes <= tolerance_minutes

def detect_mood(text):
    """
    Enhanced mood detection with support for emotional context.
    Returns a tuple of (mood_type, intensity, context)
    """
    # Enhanced mood categories
    mood_categories = {
        'positive': ['happy', 'great', 'excited', 'good', 'wonderful', 'amazing', 'fantastic', 'love', 'enjoy', 'looking forward'],
        'negative': ['sad', 'down', 'tired', 'stressed', 'overwhelmed', 'exhausted', 'frustrated', 'anxious', 'worried', 'depressed'],
        'neutral': ['okay', 'fine', 'alright', 'normal', 'usual']
    }
    
    # Supportive context keywords
    support_context = {
        'need_break': ['tired', 'exhausted', 'overwhelmed', 'stressed', 'burned out'],
        'need_activity': ['bored', 'restless', 'stuck', 'unmotivated'],
        'need_support': ['sad', 'down', 'depressed', 'lonely', 'anxious']
    }
    
    text = text.lower()
    mood_scores = {mood: 0 for mood in mood_categories}
    context_scores = {context: 0 for context in support_context}
    
    # Calculate mood scores
    for mood, keywords in mood_categories.items():
        for keyword in keywords:
            if keyword in text:
                mood_scores[mood] += 1
    
    # Calculate context scores
    for context, keywords in support_context.items():
        for keyword in keywords:
            if keyword in text:
                context_scores[context] += 1
    
    # Find dominant mood
    max_mood_score = max(mood_scores.values())
    if max_mood_score == 0:
        return 'neutral', 0.0, None
    
    dominant_mood = max(mood_scores.items(), key=lambda x: x[1])[0]
    intensity = min(1.0, max_mood_score / 3)  # Normalize intensity
    
    # Determine context
    max_context_score = max(context_scores.values())
    if max_context_score > 0:
        dominant_context = max(context_scores.items(), key=lambda x: x[1])[0]
    else:
        dominant_context = None
    
    return dominant_mood, intensity, dominant_context

def get_supportive_response(mood_type, intensity, context=None):
    """
    Generate supportive responses based on mood and context.
    """
    # Supportive responses for different moods
    supportive_responses = {
        'negative': [
            "I notice you're feeling down. Would you like to schedule some self-care time?",
            "It's important to take care of yourself. How about scheduling a relaxing activity?",
            "I'm here to support you. Would you like to plan something to help you feel better?"
        ],
        'positive': [
            "I'm glad you're feeling good! Would you like to schedule something to maintain this positive energy?",
            "That's wonderful to hear! Would you like to plan something to celebrate this mood?",
            "Your positive attitude is inspiring! Would you like to schedule something to keep this momentum going?"
        ],
        'neutral': [
            "How are you feeling today? I'm here to support you!",
            "Is there anything specific you'd like to focus on?",
            "Remember, I'm here to help you stay organized and motivated!"
        ]
    }
    
    # Wellness activities based on context
    wellness_activities = {
        'need_break': [
            {"title": "Relaxing Bath", "duration": 45, "description": "Time to unwind and relax"},
            {"title": "Meditation Session", "duration": 30, "description": "A peaceful moment to center yourself"},
            {"title": "Mindful Break", "duration": 20, "description": "A short break to practice mindfulness"}
        ],
        'need_activity': [
            {"title": "Gentle Walk", "duration": 30, "description": "A refreshing walk to clear your mind"},
            {"title": "Light Stretching", "duration": 20, "description": "Some gentle stretches to energize your body"},
            {"title": "Fresh Air Break", "duration": 15, "description": "A short break to get some fresh air"}
        ],
        'need_support': [
            {"title": "Self-Care Time", "duration": 60, "description": "Dedicated time for self-care and relaxation"},
            {"title": "Creative Break", "duration": 45, "description": "Time to engage in a creative activity"},
            {"title": "Nature Connection", "duration": 30, "description": "Time to connect with nature and find peace"}
        ]
    }
    
    # Get base response
    base_responses = supportive_responses.get(mood_type, supportive_responses['neutral'])
    response = random.choice(base_responses)
    
    # Add activity suggestions for negative moods
    if mood_type == 'negative' and context in wellness_activities:
        activities = wellness_activities[context]
        activity = random.choice(activities)
        response += f"\n\nI can suggest some activities that might help:\n"
        for i, act in enumerate(activities, 1):
            response += f"{i}. {act['title']} ({act['duration']} minutes) - {act['description']}\n"
        response += "\nWould you like to schedule any of these activities?"
    
    return response

def process_calendar_request(user_text, gemini_model, calendar_service, context=None):
    """
    Process a user's calendar request with enhanced emotional support.
    Returns a tuple of (success, response_message).
    """
    try:
        # Detect mood and context first
        mood_type, intensity, support_context = detect_mood(user_text)
        
        # If user is expressing emotions without a specific calendar request
        if mood_type == 'negative' and intensity > 0.3:  # Lower threshold for emotional support
            # Get supportive response
            supportive_response = get_supportive_response(mood_type, intensity, support_context)
            
            # Add a gentle transition to calendar functionality
            calendar_prompt = "\n\nI'm here to help you manage your schedule as well. Would you like to create, delete, edit, or view any events?"
            
            return True, supportive_response + calendar_prompt
        
        # Use context for better understanding if available
        if context:
            # Extract relevant information from context
            conversation_history = "\n".join([f"{msg['role']}: {msg['parts']}" for msg in context])
            
            # Add context to the prompt for better understanding
            enhanced_prompt = f"Previous conversation:\n{conversation_history}\n\nCurrent request: {user_text}"
        else:
            enhanced_prompt = user_text
        
        # First, determine if we need more information
        system_prompt = """You are Donna, a friendly and helpful calendar assistant.
        Your task is to:
        1. Determine if you have enough information to execute a calendar action
        2. If not, ask for the missing information
        3. If yes, execute the appropriate action
        
        For calendar actions, you need:
        
        For CREATE:
        - Action type: "CREATE"
        - Title: meeting/event name
        - Date/time: when the event will occur
        - Duration: how long it will last
        
        For DELETE:
        - Action type: "DELETE"
        - Original title: the exact title of the event to delete
        - Date/time: when the event is scheduled (to identify the correct instance)
        - IMPORTANT: For DELETE, you MUST have both the exact title and time to proceed
        
        For EDIT:
        - Action type: "EDIT"
        - Original title: current event title
        - New details: what needs to be changed
        
        For VIEW:
        - Action type: "VIEW"
        - Day: day of the week (e.g., "THU" for Thursday)
        - OR Date: specific date (e.g., "2024-04-27")
        - IMPORTANT: For VIEW, you only need either day OR date, not both
        
        When you have enough information, format the event_details like this:
        
        For CREATE:
        {
            "action": "CREATE",
            "title": "Meeting Title",
            "day": "THU",  // 3-letter day code
            "time": "03:00 PM",  // 12-hour format with AM/PM
            "duration": 60  // in minutes
        }
        
        For DELETE:
        {
            "action": "DELETE",
            "original_title": "Meeting Title",
            "day": "THU",  // 3-letter day code
            "time": "03:00 PM"  // 12-hour format with AM/PM
        }
        
        For EDIT:
        {
            "action": "EDIT",
            "original_title": "Current Title",
            "new_title": "New Title",  // if changing title
            "day": "THU",  // if changing day
            "time": "03:00 PM",  // if changing time
            "duration": 60  // if changing duration
        }
        
        For VIEW:
        {
            "action": "VIEW",
            "day": "THU"  // 3-letter day code
            // OR
            "date": "2024-04-27"  // specific date
        }
        
        Return your response in this format:
        {
            "needs_more_info": true/false,
            "missing_info": ["field1", "field2"],
            "action": "CREATE/DELETE/EDIT/VIEW/UNKNOWN",
            "event_details": {...},
            "response": "Your response to the user"
        }
        
        If the user hasn't provided enough information, set needs_more_info to true and ask for the missing information.
        If they have provided enough information, set needs_more_info to false and include the complete event details.
        """
        
        # Get structured response from Gemini
        response = gemini_model.generate_content(system_prompt + "\n\n" + enhanced_prompt)
        
        try:
            # Clean the response text to ensure it's valid JSON
            response_text = response.text.strip()
            
            # Find the JSON object in the response
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx == -1 or end_idx == 0:
                raise ValueError("No valid JSON object found in response")
                
            json_str = response_text[start_idx:end_idx]
            
            # Parse the response
            response_data = json.loads(json_str)
            
            if response_data.get("needs_more_info", False):
                # Return the response asking for more information
                return True, response_data["response"]
            
            # If we have enough information, process the action
            if response_data.get("action") in ["CREATE", "DELETE", "EDIT", "VIEW"]:
                # Ensure event_details has the required fields
                event_details = response_data.get("event_details", {})
                if not event_details:
                    return True, "I'm having trouble understanding the event details. Could you please provide them again?"
                
                # Ensure action is included in event_details
                event_details["action"] = response_data["action"]
                
                # Special handling for VIEW operations
                if event_details["action"] == "VIEW":
                    # Get events for the specified day/date
                    events = get_events_for_day(
                        calendar_service,
                        event_details.get("day"),
                        event_details.get("date")
                    )
                    
                    if not events:
                        # Format the day/date for the response
                        if event_details.get("day"):
                            day_str = event_details["day"]
                        else:
                            try:
                                date_obj = datetime.strptime(event_details["date"], "%Y-%m-%d")
                                day_str = date_obj.strftime("%A")
                            except ValueError:
                                day_str = event_details["date"]
                        
                        return True, f"You have no events scheduled for {day_str}."
                    
                    # Format the events for display
                    formatted_events = format_event_details(events)
                    return True, formatted_events
                
                # Special handling for DELETE operations
                if event_details["action"] == "DELETE":
                    # Validate required fields
                    if "original_title" not in event_details:
                        return True, "I need to know which event you want to delete. Could you please specify the event title?"
                    
                    # Check if we have time information
                    if "time" not in event_details:
                        # Find all events with this title on the specified day
                        search_details = {
                            "action": "VIEW",
                            "day": event_details.get("day"),
                            "date": event_details.get("date")
                        }
                        
                        # Get events for the day
                        events = get_events_for_day(calendar_service, search_details.get("day"), search_details.get("date"))
                        
                        # Filter events by title
                        matching_events = [
                            event for event in events 
                            if event["summary"].lower() == event_details["original_title"].lower()
                        ]
                        
                        if not matching_events:
                            return True, f"I couldn't find any events with the title '{event_details['original_title']}' on {event_details.get('day', 'the specified day')}."
                        
                        # Format the events for display
                        event_list = "\n".join([
                            f"{i+1}. {event['summary']} at {event['start'].get('dateTime', 'all day')}"
                            for i, event in enumerate(matching_events)
                        ])
                        
                        return True, f"I found these events with the title '{event_details['original_title']}':\n{event_list}\n\nWhich one would you like to delete? Please specify the time."
                    
                    # If we have time, verify the exact event exists
                    search_details = {
                        "action": "VIEW",
                        "day": event_details.get("day"),
                        "date": event_details.get("date")
                    }
                    
                    events = get_events_for_day(calendar_service, search_details.get("day"), search_details.get("date"))
                    
                    # Find exact match
                    exact_match = None
                    try:
                        # Convert user's time to standard format
                        user_time = standardize_time_for_comparison(event_details["time"])
                        
                        for event in events:
                            if event["summary"].lower() == event_details["original_title"].lower():
                                if "dateTime" in event["start"]:
                                    # Parse the event time
                                    event_time_str = event["start"]["dateTime"].split("T")[1]
                                    event_hour = int(event_time_str[:2])
                                    event_minute = int(event_time_str[3:5])
                                    
                                    # Compare times with tolerance
                                    if compare_times(user_time, (event_hour, event_minute)):
                                        exact_match = event
                                        break
                    except ValueError as e:
                        return True, f"I'm having trouble understanding the time format. Could you please specify the time in a format like '11:00 AM' or '3:00 PM'?"
                    
                    if not exact_match:
                        # Show all events with this title to help the user
                        matching_events = [
                            event for event in events 
                            if event["summary"].lower() == event_details["original_title"].lower()
                        ]
                        
                        if matching_events:
                            event_list = "\n".join([
                                f"{i+1}. {event['summary']} at {event['start'].get('dateTime', 'all day')}"
                                for i, event in enumerate(matching_events)
                            ])
                            return True, f"I couldn't find an event with the title '{event_details['original_title']}' at {event_details['time']} on {event_details.get('day', 'the specified day')}. Here are all the events with this title:\n{event_list}\n\nCould you please verify the time?"
                        else:
                            return True, f"I couldn't find any events with the title '{event_details['original_title']}' on {event_details.get('day', 'the specified day')}. Could you please verify the title and time?"
                
                # Process the calendar action
                success, response_message = handle_calendar_action(
                    event_details,
                    calendar_service
                )
                
                if success:
                    # Add supportive response if needed
                    if mood_type == 'negative' and intensity > 0.5:
                        supportive_response = get_supportive_response(mood_type, intensity, support_context)
                        response_message += "\n\n" + supportive_response
                    return True, response_message
                else:
                    return False, f"Failed to process action: {response_message}"
            
            # If action is UNKNOWN, return the clarification
            return True, response_data.get("response", "I'm not sure what you'd like to do. Could you be more specific?")
            
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error parsing response: {str(e)}")
            # If we can't parse the response, fall back to basic processing
            actions = parse_natural_language(enhanced_prompt, gemini_model)
            
            if not actions or (len(actions) == 1 and actions[0]['action'] == 'UNKNOWN'):
                return True, actions[0].get('clarification', 
                    "I'm not sure what you'd like to do. Could you rephrase that?")
            
            # Process each action
            responses = []
            for action in actions:
                try:
                    success, response_message = handle_calendar_action(
                        action, 
                        calendar_service
                    )
                    
                    if success:
                        responses.append(response_message)
                    else:
                        responses.append(f"❌ Failed to process action: {response_message}")
                    
                except Exception as e:
                    responses.append(f"❌ Failed to process action: {str(e)}")
            
            # Combine all responses
            final_response = "I've processed your request:\n\n" + "\n\n".join(responses)
            return True, final_response
        
    except Exception as e:
        print(f"Error in process_calendar_request: {str(e)}")
        return False, f"Something unexpected happened. Please try again with a simpler request. Error details: {str(e)}"

def schedule_event(event_details, calendar_service):
    """Schedule an event with support for travel time and dependencies."""
    try:
        from datetime import datetime, timedelta
        import pytz
        
        # Get user's timezone
        user_timezone = get_user_timezone()
        local_tz = pytz.timezone(user_timezone)
        current_time = datetime.now(local_tz)
        
        # Get the event's date and time
        if 'date' in event_details:
            # Parse the date string to get the date
            event_date = datetime.strptime(event_details['date'], '%Y-%m-%d')
            event_date = local_tz.localize(event_date)
        elif 'day' in event_details:
            # Find the next occurrence of the specified day
            today = current_time
            days_ahead = 0
            while True:
                current_date = today + timedelta(days=days_ahead)
                if current_date.strftime('%a').upper()[:3] == event_details['day']:
                    event_date = current_date
                    break
                days_ahead += 1
        else:
            # If no date or day specified, use today
            event_date = current_time
        
        # Parse the time
        time_str = event_details['time']
        time_parts = time_str.split()
        hour_min = time_parts[0].split(':')
        hour = int(hour_min[0])
        minute = int(hour_min[1]) if len(hour_min) > 1 else 0
        period = time_parts[1]
        
        # Convert to 24-hour format
        if period == 'PM' and hour != 12:
            hour += 12
        elif period == 'AM' and hour == 12:
            hour = 0
        
        # Create datetime object for start time in user's timezone
        start_time = event_date.replace(hour=hour, minute=minute)
        
        # Skip if the event is in the past
        if start_time < current_time:
            return False, f"Skipped scheduling '{event_details['title']}' as it's in the past"
        
        # Calculate total duration including travel time
        duration = event_details.get('duration', 30)
        travel_time = event_details.get('travel_time', 0)
        total_duration = duration + travel_time
        
        # Adjust for travel time
        if travel_time:
            start_time = start_time - timedelta(minutes=travel_time)
        
        # Calculate end time
        end_time = start_time + timedelta(minutes=total_duration)
        
        # Convert times to UTC for Google Calendar
        utc = pytz.UTC
        start_time_utc = start_time.astimezone(utc)
        end_time_utc = end_time.astimezone(utc)
        
        # Create event in Google Calendar
        event = {
            'summary': event_details['title'],
            'start': {
                'dateTime': start_time_utc.isoformat(),
                'timeZone': user_timezone,
            },
            'end': {
                'dateTime': end_time_utc.isoformat(),
                'timeZone': user_timezone,
            },
            'description': f"Duration: {duration} minutes" + \
                         (f"\nTravel time: {travel_time} minutes" if travel_time else "")
        }
        
        # Add any constraints to the description
        if 'constraints' in event_details:
            event['description'] += f"\nConstraints: {event_details['constraints']}"
        
        created_event = calendar_service.events().insert(calendarId='primary', body=event).execute()
        
        # Format the response message
        formatted_start = start_time.strftime('%A, %B %d at %I:%M %p')
        hours = duration // 60
        minutes = duration % 60
        
        if hours > 0 and minutes > 0:
            duration_str = f"{hours} hour{'s' if hours != 1 else ''} and {minutes} minute{'s' if minutes != 1 else ''}"
        elif hours > 0:
            duration_str = f"{hours} hour{'s' if hours != 1 else ''}"
        else:
            duration_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
        
        response_message = f"✅ Scheduled '{event_details['title']}' for {formatted_start} ({duration_str})"
        
        if travel_time:
            response_message += f" (including {travel_time} minutes travel time)"
            
        return True, response_message
        
    except Exception as e:
        return False, f"Error scheduling event: {str(e)}"

def edit_event(event_details, calendar_service):
    """Edit an existing event with improved handling."""
    try:
        # Validate the input first
        event_details = validate_event_details(event_details)
        
        # Find matching events
        matching_events = find_matching_events(calendar_service, event_details)
        
        if not matching_events:
            raise EventNotFoundError("I couldn't find any events matching your description")
        
        if len(matching_events) > 1:
            # Multiple matches found, provide details for selection
            return None, None, None, format_event_details(matching_events) + "\nPlease specify which event you want to edit by providing more specific details."
        
        # Get the event to edit
        event_to_edit = matching_events[0]
        
        # Get the full event details from Calendar API
        full_event = calendar_service.events().get(
            calendarId='primary',
            eventId=event_to_edit['id']
        ).execute()
        
        # Create updated event with original values as defaults
        updated_event = {
            'summary': event_details.get('new_title', full_event['summary'])
        }
        
        # Update description if provided
        if 'description' in event_details:
            updated_event['description'] = event_details['description']
        elif 'description' in full_event:
            updated_event['description'] = full_event['description']
            
        # Update location if provided
        if 'location' in event_details:
            updated_event['location'] = event_details['location']
        elif 'location' in full_event:
            updated_event['location'] = full_event['location']
        
        # Get user's timezone
        user_timezone = get_user_timezone()
        
        # Update date/time if provided
        if any(key in event_details for key in ['time', 'date', 'day', 'duration']):
            # Start with existing event time
            event_start = parse_datetime_from_api(
                full_event['start'].get('dateTime', full_event['start'].get('date')),
                full_event['start'].get('timeZone', user_timezone)
            )
            
            # Calculate duration from existing event
            event_end = parse_datetime_from_api(
                full_event['end'].get('dateTime', full_event['end'].get('date')),
                full_event['end'].get('timeZone', user_timezone)
            )
            duration_minutes = int((event_end - event_start).total_seconds() / 60)
            
            # Update with provided values
            
            # Update time if provided
            if 'time' in event_details:
                try:
                    time_obj = datetime.strptime(event_details['time'], '%I:%M %p')
                    # Replace just the time portion
                    event_start = event_start.replace(
                        hour=time_obj.hour,
                        minute=time_obj.minute
                    )
                except ValueError:
                    raise InvalidInputError("Invalid time format")
            
            # Update date if provided
            if 'date' in event_details:
                try:
                    date_obj = datetime.strptime(event_details['date'], '%Y-%m-%d')
                    # Replace just the date portion
                    event_start = event_start.replace(
                        year=date_obj.year,
                        month=date_obj.month,
                        day=date_obj.day
                    )
                except ValueError:
                    raise InvalidInputError("Invalid date format")
            
            # Update day if provided
            elif 'day' in event_details:
                day_mapping = {'MON': 0, 'TUE': 1, 'WED': 2, 'THU': 3, 'FRI': 4, 'SAT': 5, 'SUN': 6}
                target_day = day_mapping[event_details['day']]
                today = datetime.now(pytz.timezone(user_timezone))
                
                # Calculate days until target day
                days_ahead = (target_day - today.weekday()) % 7
                if days_ahead == 0 and today.hour > event_start.hour:
                    days_ahead = 7
                    
                target_date = today + timedelta(days=days_ahead)
                
                # Replace just the date portion
                event_start = event_start.replace(
                    year=target_date.year,
                    month=target_date.month,
                    day=target_date.day
                )
            
            # Update duration if provided
            if 'duration' in event_details:
                try:
                    duration_minutes = int(event_details['duration'])
                except (ValueError, TypeError):
                    raise InvalidInputError("Invalid duration format")
            
            # Calculate end time based on duration
            event_end = event_start + timedelta(minutes=duration_minutes)
            
            # Add updated times to event
            updated_event.update({
                'start': {
                    'dateTime': event_start.isoformat(),
                    'timeZone': user_timezone
                },
                'end': {
                    'dateTime': event_end.isoformat(),
                    'timeZone': user_timezone
                }
            })
        
        # Update the event
        updated_event = calendar_service.events().update(
            calendarId='primary',
            eventId=event_to_edit['id'],
            body=updated_event
        ).execute()
        return None, None, updated_event.get('htmlLink'), f"I've updated '{updated_event['summary']}' in your calendar."
    
    except EventNotFoundError as e:
        raise
    except InvalidInputError as e:
        raise
    except Exception as e:
        error_message = str(e).lower()
        if "invalid_grant" in error_message:
            raise AuthenticationError("Your Google Calendar access has expired")
        elif "quota" in error_message:
            raise APILimitError("Calendar API limit reached")
        else:
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
            return False, f"Could not find event with title: {event_details['original_title']}"
        
        # Delete the event
        calendar_service.events().delete(
            calendarId='primary',
            eventId=event_to_delete['id']
        ).execute()
        
        return True, f"I've deleted '{event_details['original_title']}' from your calendar."
        
    except Exception as e:
        return False, f"Error deleting event: {str(e)}"

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