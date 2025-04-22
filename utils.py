import json
import re
from datetime import datetime, timedelta
import google.generativeai as genai
import os
from google_calendar import add_event_to_calendar, get_week_events
import pytz
from difflib import SequenceMatcher


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
    Accepts various input formats like 'MM/DD', 'MM-DD-YYYY', etc.
    """
    # Remove whitespace
    date_str = date_str.strip()
    
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
    
    # Special case for today, tomorrow, etc.
    if date_str.lower() == 'today':
        return datetime.now().strftime('%Y-%m-%d')
    elif date_str.lower() == 'tomorrow':
        return (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    elif date_str.lower() == 'yesterday':
        return (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    # Try each format
    for fmt in formats:
        try:
            parsed_date = datetime.strptime(date_str, fmt)
            
            # Set year to current year if not specified
            if '%Y' not in fmt:
                current_year = datetime.now().year
                
                # If the resulting date is in the past, and it's near the end of year,
                # assume it's for next year
                if parsed_date.replace(year=current_year) < datetime.now() and datetime.now().month > 10:
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
                events = []
                
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
                        start_time, end_time, event_link, _ = schedule_event(event_copy, calendar_service)
                        events.append((start_time, end_time, event_link))
                    except Exception as e:
                        print(f"Warning: Failed to create recurring event for {current_date}: {str(e)}")
                        continue
                
                if not events:
                    return None, None, None, "Failed to create any recurring events"
                
                # Return the first event's details and a summary message
                first_event = events[0]
                summary = f"Created recurring event '{event_details['title']}' for the next 7 days"
                return first_event[0], first_event[1], first_event[2], summary
            
            # For single events
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
    """Get events for a specific day with improved handling."""
    try:
        # Get user's timezone
        user_timezone = get_user_timezone()
        local_tz = pytz.timezone(user_timezone)
        
        # Determine target date
        if date:
            try:
                # Standardize date format first
                date = standardize_date_format(date)
                start_date = datetime.strptime(date, '%Y-%m-%d')
            except ValueError:
                raise InvalidInputError("Invalid date format. Please use YYYY-MM-DD format")
        elif day:
            # Standardize day format
            day = standardize_day_format(day)
            
            # Get current time in user's timezone
            now = datetime.now(local_tz)
            
            # Map days to weekday numbers (0=Monday, 6=Sunday)
            day_mapping = {'MON': 0, 'TUE': 1, 'WED': 2, 'THU': 3, 'FRI': 4, 'SAT': 5, 'SUN': 6}
            target_day = day_mapping[day]
            
            # Calculate days until target day
            days_ahead = (target_day - now.weekday()) % 7
            
            # If it's today and after 6pm, show next week's occurrence instead
            if days_ahead == 0 and now.hour >= 18:
                days_ahead = 7
                
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
        else:
            # Default to today
            now = datetime.now(local_tz)
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Ensure datetime is timezone-aware
        if not hasattr(start_date, 'tzinfo') or start_date.tzinfo is None:
            start_date = local_tz.localize(start_date)
            
        # Set time range to cover the entire day
        end_date = start_date.replace(hour=23, minute=59, second=59)
        
        # Convert to UTC for API call
        start_datetime_utc = start_date.astimezone(pytz.UTC)
        end_datetime_utc = end_date.astimezone(pytz.UTC)
        
        # Request events from Calendar API
        events_result = calendar_service.events().list(
            calendarId='primary',
            timeMin=start_datetime_utc.isoformat(),
            timeMax=end_datetime_utc.isoformat(),
            singleEvents=True,
            orderBy='startTime',
            maxResults=50  # Increased to ensure we get all day's events
        ).execute()
        
        events = events_result.get('items', [])
        
        formatted_events = []
        for event in events:
            # Parse event times
            event_start = parse_datetime_from_api(
                event['start'].get('dateTime', event['start'].get('date')), 
                event['start'].get('timeZone', user_timezone)
            )
            
            event_end = parse_datetime_from_api(
                event['end'].get('dateTime', event['end'].get('date')),
                event['end'].get('timeZone', user_timezone)
            )
            
            # Calculate duration in minutes
            duration = int((event_end - event_start).total_seconds() / 60)
            
            # Determine if it's an all-day event
            all_day = 'date' in event['start'] and 'date' in event['end']
            
            formatted_events.append({
                'id': event['id'],
                'title': event['summary'],
                'start': event_start,
                'end': event_end,
                'duration': duration,
                'all_day': all_day,
                'location': event.get('location', ''),
                'description': event.get('description', '')
            })
        
        # Sort events by start time
        formatted_events.sort(key=lambda x: x['start'])
        
        return formatted_events
        
    except InvalidInputError as e:
        raise
    except Exception as e:
        error_message = str(e).lower()
        if "invalid_grant" in error_message:
            raise AuthenticationError("Your Google Calendar access has expired")
        elif "quota" in error_message:
            raise APILimitError("Calendar API limit reached")
        else:
            raise Exception(f"Error getting events: {str(e)}")

def format_event_details(events):
    """Format event details for display with improved formatting."""
    if not events:
        return "No events found for this period."
    
    # Get user's timezone for consistent display
    user_timezone = get_user_timezone()
    
    # Group events by date
    events_by_date = {}
    for event in events:
        event_date = event['start'].astimezone(pytz.timezone(user_timezone)).date()
        if event_date not in events_by_date:
            events_by_date[event_date] = []
        events_by_date[event_date].append(event)
    
    # Format output
    details = ""
    for date, day_events in sorted(events_by_date.items()):
        # Add date header
        details += f"📅 {date.strftime('%A, %B %d, %Y')}\n\n"
        
        # Add events for this day
        for i, event in enumerate(day_events, 1):
            # Format the time display
            if event.get('all_day', False):
                time_display = "All day"
            else:
                start_time = event['start'].astimezone(pytz.timezone(user_timezone))
                end_time = event['end'].astimezone(pytz.timezone(user_timezone))
                time_display = f"{start_time.strftime('%I:%M %p')} to {end_time.strftime('%I:%M %p')}"
            
            # Format duration display
            hours = event['duration'] // 60
            minutes = event['duration'] % 60
            
            if event.get('all_day', False):
                duration_str = "All day"
            elif hours > 0 and minutes > 0:
                duration_str = f"{hours} hr{'s' if hours != 1 else ''}, {minutes} min"
            elif hours > 0:
                duration_str = f"{hours} hr{'s' if hours != 1 else ''}"
            else:
                duration_str = f"{minutes} min"
            
            # Build event display
            details += f"{i}. {event['title']}\n"
            details += f"   ⏰ {time_display}\n"
            details += f"   ⌛ {duration_str}\n"
            
            if event.get('location'):
                details += f"   📍 {event['location']}\n"
                
            details += "\n"
    
    return details

def parse_natural_language(prompt, model):
    """
    Parse natural language input to extract multiple calendar events.
    Returns a list of event details dictionaries.
    """
    system_prompt = """You are an expert calendar assistant helping schedule multiple events.
Your task is to:
1. Identify all events mentioned in the prompt
2. Extract details for each event including:
   - Title/description
   - Date/time (or recurring pattern)
   - Duration
   - Travel time (if mentioned)
   - Any dependencies or constraints
3. Format each event as a separate JSON object
4. Ensure no time conflicts between events

For each event, extract:
- action: "CREATE"
- title: event name/description
- date: specific date (YYYY-MM-DD) if mentioned
- day: day of week if mentioned
- time: start time
- duration: duration in minutes
- travel_time: travel duration in minutes if mentioned
- recurring: true/false if it's a daily/weekly event
- constraints: any specific constraints mentioned

IMPORTANT: Your response must be a valid JSON array of events. Do not include any explanatory text.
Each event must have at least title, time, and duration.

Example output format:
[
    {
        "action": "CREATE",
        "title": "Math Class",
        "day": "THU",
        "time": "06:00 PM",
        "duration": 180,
        "travel_time": 30
    },
    {
        "action": "CREATE",
        "title": "Workout",
        "recurring": true,
        "time": "06:00 AM",
        "duration": 60
    }
]

Now, analyze this prompt and extract all events. Return ONLY the JSON array:"""

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
        events = json.loads(json_str)
        
        # Validate each event
        validated_events = []
        for event in events:
            try:
                # Ensure required fields are present
                if 'title' not in event or 'time' not in event or 'duration' not in event:
                    print(f"Warning: Skipping event missing required fields: {event}")
                    continue
                    
                # Set default action if not specified
                if 'action' not in event:
                    event['action'] = 'CREATE'
                    
                # Validate the event
                validated_event = validate_event_details(event)
                validated_events.append(validated_event)
            except InvalidInputError as e:
                print(f"Warning: Skipping invalid event: {str(e)}")
                continue
                
        return validated_events
        
    except Exception as e:
        print(f"Error parsing natural language: {str(e)}")
        return [{
            'action': 'UNKNOWN',
            'clarification': "I'm having trouble understanding your schedule. Could you break it down into simpler, separate events?"
        }]

def process_calendar_request(user_text, gemini_model, calendar_service):
    """
    Process a user's calendar request with support for multiple events.
    Returns a tuple of (success, response_message).
    """
    try:
        # Parse natural language input to get multiple events
        events = parse_natural_language(user_text, gemini_model)
        
        # If we couldn't parse any events, return the clarification message
        if not events or (len(events) == 1 and events[0]['action'] == 'UNKNOWN'):
            return True, events[0].get('clarification', 
                "I'm not sure what you'd like to schedule. Could you rephrase that?")
        
        # Process each event
        responses = []
        for event in events:
            try:
                # Handle the calendar action
                start_time, end_time, event_link, response_message = handle_calendar_action(
                    event, 
                    calendar_service
                )
                
                # Build response for this event
                if event['action'] == 'CREATE':
                    formatted_start = start_time.strftime('%A, %B %d at %I:%M %p')
                    hours = event['duration'] // 60
                    minutes = event['duration'] % 60
                    
                    if hours > 0 and minutes > 0:
                        duration_str = f"{hours} hour{'s' if hours != 1 else ''} and {minutes} minute{'s' if minutes != 1 else ''}"
                    elif hours > 0:
                        duration_str = f"{hours} hour{'s' if hours != 1 else ''}"
                    else:
                        duration_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
                    
                    event_response = f"✅ Scheduled '{event['title']}' for {formatted_start} ({duration_str})"
                    
                    if event.get('travel_time'):
                        event_response += f" (including {event['travel_time']} minutes travel time)"
                        
                    if event_link:
                        event_response += f"\nView event: {event_link}"
                        
                    responses.append(event_response)
                    
            except Exception as e:
                responses.append(f"❌ Failed to schedule '{event.get('title', 'event')}': {str(e)}")
        
        # Combine all responses
        final_response = "I've processed your schedule:\n\n" + "\n\n".join(responses)
        return True, final_response
        
    except Exception as e:
        return False, f"Something unexpected happened. Please try again with a simpler request. Error details: {str(e)}"

def schedule_event(event_details, calendar_service):
    """Schedule an event with support for travel time and dependencies."""
    try:
        # Calculate start time considering travel time
        from datetime import datetime, timedelta
        import pytz
        
        # Get the event's date and time
        if 'date' in event_details:
            event_date = datetime.strptime(event_details['date'], '%Y-%m-%d')
        else:
            # Find next occurrence of the specified day
            today = datetime.now()
            days_ahead = 0
            while True:
                current_date = today + timedelta(days=days_ahead)
                if current_date.strftime('%a').upper()[:3] == event_details['day']:
                    event_date = current_date
                    break
                days_ahead += 1
        
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
        
        # Create datetime object
        start_time = event_date.replace(hour=hour, minute=minute)
        
        # Adjust for travel time if specified
        travel_time = event_details.get('travel_time', 0)
        if travel_time:
            start_time = start_time - timedelta(minutes=travel_time)
        
        # Calculate end time
        duration = event_details.get('duration', 30)
        end_time = start_time + timedelta(minutes=duration + travel_time)
        
        # Create event in Google Calendar
        event = {
            'summary': event_details['title'],
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': 'UTC',
            },
            'description': f"Duration: {duration} minutes" + (f"\nTravel time: {travel_time} minutes" if travel_time else "")
        }
        
        # Add any constraints to the description
        if 'constraints' in event_details:
            event['description'] += f"\nConstraints: {event_details['constraints']}"
        
        created_event = calendar_service.events().insert(calendarId='primary', body=event).execute()
        
        return start_time, end_time, created_event.get('htmlLink'), None
        
    except Exception as e:
        raise Exception(f"Error scheduling event: {str(e)}")

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
    """Delete an event with improved error handling."""
    try:
        # Validate the input first
        event_details = validate_event_details(event_details)
        
        # Find matching events
        matching_events = find_matching_events(calendar_service, event_details)
        
        if not matching_events:
            raise EventNotFoundError("I couldn't find any events matching your description")
        
        if len(matching_events) > 1:
            # Multiple matches found, provide details for selection
            return None, None, None, format_event_details(matching_events) + "\nPlease specify which event you want to delete by providing more specific details."
        
        # Get the event to delete
        event_to_delete = matching_events[0]
        event_title = event_to_delete['title']
        
        # Delete the event
        calendar_service.events().delete(
            calendarId='primary',
            eventId=event_to_delete['id']
        ).execute()
        
        return None, None, None, f"I've deleted '{event_title}' from your calendar."
        
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