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
    """Handle different calendar actions with improved error handling"""
    try:
        if event_details['action'] == 'CREATE':
            return schedule_event(event_details, calendar_service)
        elif event_details['action'] == 'EDIT':
            return edit_event(event_details, calendar_service)
        elif event_details['action'] == 'DELETE':
            return delete_event(event_details, calendar_service)
        elif event_details['action'] == 'VIEW':
            try:
                events = get_events_for_day(
                    calendar_service, 
                    event_details.get('day'), 
                    event_details.get('date')
                )
                if not events:
                    return None, None, None, "You have no events scheduled for this day."
                return None, None, None, format_event_details(events)
            except Exception as e:
                if "invalid date format" in str(e).lower():
                    raise InvalidInputError(f"I couldn't understand the date format. Please use YYYY-MM-DD format.")
                else:
                    raise
        elif event_details['action'] == 'UNKNOWN':
            return None, None, None, event_details['clarification']
        else:
            raise InvalidInputError(f"Unknown action type: {event_details['action']}")
            
    except AuthenticationError as e:
        return None, None, None, f"Authentication error: {str(e)}. Please reconnect your Google Calendar."
    except EventNotFoundError as e:
        return None, None, None, f"I couldn't find that event: {str(e)}. Could you provide more details?"
    except InvalidInputError as e:
        return None, None, None, f"There was an issue with the information provided: {str(e)}"
    except APILimitError:
        return None, None, None, "We've hit Google's API rate limits. Please try again in a few minutes."
    except ParsingError as e:
        return None, None, None, f"I'm having trouble understanding your request: {str(e)}"
    except Exception as e:
        # Generic error handling as a last resort
        error_message = str(e)
        if "invalid_grant" in error_message:
            return None, None, None, "Your Google Calendar connection needs to be refreshed. Please reconnect your account."
        elif "quota" in error_message.lower():
            return None, None, None, "Google Calendar API limit reached. Please try again later."
        else:
            # Log the full error for debugging (would go to your logging system)
            print(f"Unexpected error in calendar action: {error_message}")
            return None, None, None, "I encountered an unexpected problem with your calendar. Please try again or contact support if the issue persists."

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
    """Use Gemini to parse natural language with improved context and fallbacks."""
    try:
        system_prompt = """
        You are a friendly personal assistant helping with calendar management. You have a warm, helpful personality and make scheduling feel effortless. Your task is to understand the user's intent and extract relevant information.
        
        You can have natural conversations with the user about anything, not just calendar management. When the user is just chatting or asking general questions, respond in a friendly, conversational way.
        
        When the user wants to do something with their calendar, parse it carefully and extract the intent and details.
        
        POSSIBLE ACTIONS:
        1. CREATE: Create a new event
        2. EDIT: Modify an existing event
        3. DELETE: Remove an existing event
        4. VIEW: View events for a specific day/date
        5. UNKNOWN: Used when the intent is unclear or for general conversation
        
        EXTRACTION REQUIREMENTS:
        - action: One of CREATE, EDIT, DELETE, VIEW, or UNKNOWN
        - title: The event title/description
        - day: The day of the week (MON, TUE, WED, THU, FRI, SAT, SUN)
        - date: The date in format YYYY-MM-DD
        - time: The time in 12-hour format with AM/PM (e.g., "05:00 PM")
        - duration: Duration in minutes (default to 30 if not specified)
        - original_title: For EDIT/DELETE actions, the original event title to identify the event
        - new_title: For EDIT action, the new title if specified
        - clarification: For UNKNOWN action, what information is missing or a friendly response for general conversation
        
        HANDLING USER EXPRESSIONS:
        - Interpret time expressions like "tomorrow", "next Monday", "this afternoon", etc.
        - For times like "afternoon", use: morning = 9am, afternoon = 2pm, evening = 7pm
        - For "lunch meeting", default to noon (12:00 PM)
        - For "breakfast meeting", default to 8:00 AM
        - For "dinner meeting", default to 7:00 PM
        - If only day of week is specified, find the next occurrence of that day
        - If someone says "meeting with X", it should be a CREATE action
        - If someone mentions "cancel" or "delete", it's likely a DELETE action
        - If someone mentions "change" or "move" or "reschedule", it's likely an EDIT action
        - If someone says "what's on my calendar", it's a VIEW action
        - Default duration for meetings is 30 minutes unless specified
        
        SPECIAL HANDLING:
        - When the query is clearly not calendar-related, set action to "UNKNOWN" with a helpful conversational response
        - For small talk or greetings, respond with an appropriate conversational message
        - If a description or location is mentioned, include those fields
        
        OUTPUT FORMAT:
        Return a JSON object with the extracted fields. Include only fields that are relevant to the detected action.
        Do not include explanation text outside the JSON.
        
        Example outputs:
        
        For calendar actions:
        {"action": "CREATE", "title": "Team meeting", "day": "TUE", "time": "10:00 AM", "duration": 60}
        {"action": "EDIT", "original_title": "Doctor appointment", "new_title": "Dentist appointment", "day": "WED", "time": "02:00 PM"}
        {"action": "DELETE", "original_title": "Gym class", "day": "FRI", "time": "05:00 PM"}
        {"action": "VIEW", "day": "MON"}
        
        For general conversation:
        {"action": "UNKNOWN", "clarification": "Hi! How can I help you today? I can help you manage your calendar or just chat."}
        {"action": "UNKNOWN", "clarification": "I'm doing well, thank you for asking! How can I assist you with your schedule today?"}
        {"action": "UNKNOWN", "clarification": "That's interesting! While I'm here to help with your calendar, I'm happy to chat about other things too."}
        """
        
        # Add examples of real-world inputs for improved comprehension
        examples = """
        Examples of user inputs and expected outputs:
        
        Input: "Hi, how are you?"
        Output: {"action": "UNKNOWN", "clarification": "Hello! I'm doing well, thank you for asking. How can I help you today? I can assist with your calendar or just chat."}
        
        Input: "What's the weather like?"
        Output: {"action": "UNKNOWN", "clarification": "I'm here to help with your calendar, but I can't check the weather. Would you like to see your schedule for today?"}
        
        Input: "I need to meet John for coffee tomorrow afternoon"
        Output: {"action": "CREATE", "title": "Coffee with John", "date": "2023-04-23", "time": "02:00 PM", "duration": 30}
        
        Input: "Schedule a doctor appointment on Friday at 3pm"
        Output: {"action": "CREATE", "title": "Doctor appointment", "day": "FRI", "time": "03:00 PM", "duration": 30}
        
        Input: "My dentist appointment on Wednesday needs to be moved to Thursday at 2pm"
        Output: {"action": "EDIT", "original_title": "Dentist appointment", "day": "THU", "time": "02:00 PM"}
        
        Input: "Cancel my lunch with Sarah tomorrow"
        Output: {"action": "DELETE", "original_title": "Lunch with Sarah", "date": "2023-04-23", "time": "12:00 PM"}
        
        Input: "What's on my calendar for next Monday?"
        Output: {"action": "VIEW", "day": "MON"}
        """
        
        # Generate current date information to help with relative date references
        from datetime import datetime
        current_date = datetime.now().strftime("%Y-%m-%d")
        current_day = datetime.now().strftime("%a").upper()[:3]
        date_context = f"Current date: {current_date}, Current day: {current_day}"
        
        # Combine prompts with date context
        full_prompt = f"{system_prompt}\n\n{examples}\n\n{date_context}\n\nUser text: {prompt}"
        
        # Get response from Gemini
        response = model.generate_content(full_prompt)
        
        try:
            # Extract JSON from response
            text = response.text.strip()
            # Find the JSON part in the response (looking for opening/closing braces)
            json_start = text.find('{')
            json_end = text.rfind('}') + 1
            
            if json_start < 0 or json_end <= 0:
                raise ValueError("No valid JSON found in response")
                
            json_str = text[json_start:json_end]
            event_details = json.loads(json_str)
            
            # Post-process the extracted data
            
            # Standardize date format if present
            if 'date' in event_details:
                try:
                    event_details['date'] = standardize_date_format(event_details['date'])
                except InvalidInputError:
                    # If standardizing fails, remove the date
                    del event_details['date']
            
            # Standardize time format if present
            if 'time' in event_details:
                try:
                    event_details['time'] = standardize_time_format(event_details['time'])
                except InvalidInputError:
                    # Use default times based on context if standardizing fails
                    if 'lunch' in prompt.lower():
                        event_details['time'] = '12:00 PM'
                    elif 'breakfast' in prompt.lower():
                        event_details['time'] = '08:00 AM'
                    elif 'dinner' in prompt.lower():
                        event_details['time'] = '07:00 PM'
                    elif 'morning' in prompt.lower():
                        event_details['time'] = '09:00 AM'
                    elif 'afternoon' in prompt.lower():
                        event_details['time'] = '02:00 PM'
                    elif 'evening' in prompt.lower():
                        event_details['time'] = '07:00 PM'
                    else:
                        # If no context clues, remove the time
                        del event_details['time']
            
            # Standardize day format if present
            if 'day' in event_details:
                try:
                    event_details['day'] = standardize_day_format(event_details['day'])
                except InvalidInputError:
                    # If standardizing fails, remove the day
                    del event_details['day']
            
            # Make sure required fields are present based on action
            if event_details['action'] == 'CREATE':
                if 'title' not in event_details:
                    event_details['title'] = 'Untitled Event'
                if 'duration' not in event_details:
                    event_details['duration'] = 30
            
            return event_details
            
        except json.JSONDecodeError:
            # Fallback if JSON parsing fails
            return {
                'action': 'UNKNOWN',
                'clarification': 'I had trouble understanding your request. Could you rephrase it in terms of creating, viewing, editing, or deleting a calendar event?'
            }
            
    except Exception as e:
        # Final fallback for any other errors
        return {
            'action': 'UNKNOWN',
            'clarification': f'Sorry, I experienced a technical issue. Could you try again with a simpler request?'
        }
    
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
    """Schedule an event in Google Calendar with improved handling."""
    try:
        # Validate the input first
        event_details = validate_event_details(event_details)
        
        # Get user's timezone
        user_timezone = get_user_timezone()
        
        # Parse the time
        try:
            time_obj = datetime.strptime(event_details['time'], '%I:%M %p')
        except ValueError:
            raise InvalidInputError("Invalid time format. Please use format like '05:00 PM'")
        
        # Determine the event date
        if 'date' in event_details:
            try:
                event_date = datetime.strptime(event_details['date'], '%Y-%m-%d')
            except ValueError:
                raise InvalidInputError("Invalid date format. Please use YYYY-MM-DD format")
        else:
            # Use the day of week to determine date
            today = datetime.now(pytz.timezone(user_timezone))
            day_mapping = {'MON': 0, 'TUE': 1, 'WED': 2, 'THU': 3, 'FRI': 4, 'SAT': 5, 'SUN': 6}
            target_day = day_mapping[event_details['day']]
            
            # Calculate days until target day
            days_ahead = (target_day - today.weekday()) % 7
            
            # If today is the target day and it's already past the specified time, schedule for next week
            if days_ahead == 0 and today.hour > time_obj.hour:
                days_ahead = 7
            
            event_date = today + timedelta(days=days_ahead)
        
        # Combine date and time
        start_datetime = datetime.combine(
            event_date.date(), 
            time_obj.time()
        )
        
        # Add timezone information
        start_datetime = pytz.timezone(user_timezone).localize(start_datetime)
        
        # Calculate end time
        end_datetime = start_datetime + timedelta(minutes=event_details['duration'])
        
        # Format for API
        event_data = {
            'summary': event_details['title'],
            'start': {
                'dateTime': start_datetime.isoformat(),
                'timeZone': user_timezone
            },
            'end': {
                'dateTime': end_datetime.isoformat(),
                'timeZone': user_timezone
            },
            'colorId': event_details.get('color_id', '1'),  # Default to blue
            'reminders': {
                'useDefault': True
            }
        }
        
        # Add description if provided
        if 'description' in event_details:
            event_data['description'] = event_details['description']
        
        # Add location if provided
        if 'location' in event_details:
            event_data['location'] = event_details['location']
        
        # Create the event
        created_event = calendar_service.events().insert(
            calendarId='primary',
            body=event_data
        ).execute()
        
        return start_datetime, end_datetime, created_event.get('htmlLink'), None
        
    except InvalidInputError as e:
        raise
    except Exception as e:
        # Check for specific API errors
        error_message = str(e).lower()
        if "invalid_grant" in error_message:
            raise AuthenticationError("Your Google Calendar access has expired")
        elif "quota" in error_message:
            raise APILimitError("Calendar API limit reached")
        else:
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

def process_calendar_request(user_text, gemini_model, calendar_service):
    """
    Process a user's calendar request with improved handling.
    Returns a tuple of (success, response_message).
    """
    try:
        # Parse natural language input
        event_details = parse_natural_language(user_text, gemini_model)
        
        # Log the parsed intent for debugging (you might want to remove this in production)
        print(f"Parsed intent: {event_details}")
        
        # If we couldn't parse the intent clearly, ask for clarification
        if event_details['action'] == 'UNKNOWN':
            return True, event_details.get('clarification', 
                "I'm not sure what you'd like to do with your calendar. Could you rephrase that?")
        
        # Validate the extracted information
        try:
            event_details = validate_event_details(event_details)
        except InvalidInputError as e:
            return False, f"I need a bit more information: {str(e)}"
        
        # Handle the calendar action
        try:
            start_time, end_time, event_link, response_message = handle_calendar_action(
                event_details, 
                calendar_service
            )
            
            # If we got a direct response message, return it
            if response_message:
                return True, response_message
                
            # Otherwise, build an appropriate response based on the action type
            if event_details['action'] == 'CREATE':
                # Format start time for display
                formatted_start = start_time.strftime('%A, %B %d at %I:%M %p')
                
                # Calculate duration for display
                hours = event_details['duration'] // 60
                minutes = event_details['duration'] % 60
                
                if hours > 0 and minutes > 0:
                    duration_str = f"{hours} hour{'s' if hours != 1 else ''} and {minutes} minute{'s' if minutes != 1 else ''}"
                elif hours > 0:
                    duration_str = f"{hours} hour{'s' if hours != 1 else ''}"
                else:
                    duration_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
                
                response = f"✅ I've scheduled '{event_details['title']}' for {formatted_start} ({duration_str})"
                
                if event_link:
                    response += f"\n\nYou can view or edit this event here: {event_link}"
                    
                return True, response
                
            elif event_details['action'] == 'EDIT':
                response = f"✅ Your event has been updated successfully"
                
                if event_link:
                    response += f"\n\nYou can view the updated event here: {event_link}"
                    
                return True, response
                
            elif event_details['action'] == 'DELETE':
                return True, f"✅ I've deleted the event '{event_details.get('original_title', 'specified event')}' from your calendar."
                
            else:
                return False, "Something went wrong. Please try again."
                
        except EventNotFoundError:
            return False, f"I couldn't find an event matching '{event_details.get('original_title', '')}'. Could you provide more details?"
            
        except AuthenticationError:
            return False, "It looks like your Google Calendar connection needs to be refreshed. Please reconnect your account."
            
        except APILimitError:
            return False, "We've reached the limit of Google Calendar API requests. Please try again in a few minutes."
            
        except Exception as e:
            return False, f"I encountered an error: {str(e)}"
            
    except Exception as e:
        return False, f"Something unexpected happened. Please try again with a simpler request. Error details: {str(e)}"