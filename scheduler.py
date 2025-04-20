import google.generativeai as genai
from datetime import datetime, timedelta
import pandas as pd
import json
import os

class Scheduler:
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-pro')
        self.schedule = pd.DataFrame(columns=['Task', 'Start Time', 'End Time', 'Priority', 'Status', 'Day', 'Color'])
        self.system_prompt = """
        You are an expert personal scheduling assistant. Your role is to help users create and manage their weekly schedules efficiently.
        
        Your capabilities include:
        1. Understanding and processing natural language descriptions of tasks and commitments
        2. Considering various constraints and priorities when scheduling
        3. Detecting and resolving scheduling conflicts
        4. Making intelligent adjustments to existing schedules
        5. Asking relevant questions to gather necessary information
        
        When scheduling, consider:
        - Task priorities and deadlines
        - Time restrictions and preferences
        - Required break times between tasks
        - Travel time if applicable
        - Energy levels throughout the day
        - Task dependencies and prerequisites
        
        Always:
        1. Ask clarifying questions when information is missing
        2. Suggest optimal time slots based on the user's preferences
        3. Explain your reasoning for schedule decisions
        4. Propose alternatives when conflicts arise
        5. Consider the user's work-life balance
        
        Format your responses in a clear, structured manner, and be proactive in suggesting improvements to the schedule.
        """
    
    def add_task(self, task_name, start_time, end_time, priority, restrictions=None, day=None, color=None):
        """Add a new task to the schedule"""
        new_task = pd.DataFrame({
            'Task': [task_name],
            'Start Time': [start_time],
            'End Time': [end_time],
            'Priority': [priority],
            'Status': ['Pending'],
            'Restrictions': [restrictions or {}],
            'Day': [day],
            'Color': [color or '#1a73e8']  # Default blue color if none specified
        })
        self.schedule = pd.concat([self.schedule, new_task], ignore_index=True)
        return self.check_conflicts()
    
    def check_conflicts(self):
        """Check for scheduling conflicts"""
        conflicts = []
        for i in range(len(self.schedule)):
            for j in range(i + 1, len(self.schedule)):
                task1 = self.schedule.iloc[i]
                task2 = self.schedule.iloc[j]
                
                # Only check conflicts for tasks on the same day
                if task1['Day'] == task2['Day']:
                    time1_start = datetime.strptime(task1['Start Time'], '%H:%M')
                    time1_end = datetime.strptime(task1['End Time'], '%H:%M')
                    time2_start = datetime.strptime(task2['Start Time'], '%H:%M')
                    time2_end = datetime.strptime(task2['End Time'], '%H:%M')
                    
                    if (time1_start < time2_end and time1_end > time2_start):
                        conflicts.append((task1['Task'], task2['Task']))
        
        return conflicts
    
    def generate_schedule(self, user_input):
        """Generate a schedule using Gemini"""
        prompt = f"""
        {self.system_prompt}
        
        Current schedule state:
        {self.schedule.to_json()}
        
        User input:
        {user_input}
        
        Please analyze this information and provide:
        1. A response to the user's request
        2. Any clarifying questions you need
        3. Suggested schedule adjustments if applicable
        
        Format the schedule with the following columns:
        - Task: The name of the task
        - Start Time: In HH:MM format (24-hour)
        - End Time: In HH:MM format (24-hour)
        - Priority: High/Medium/Low
        - Status: Pending/Completed
        - Day: SUN/MON/TUE/WED/THU/FRI/SAT
        - Color: Hex color code for the task (e.g., #1a73e8 for blue)
        """
        
        response = self.model.generate_content(prompt)
        return self._parse_schedule_response(response.candidates[0].content.parts[0].text)
    
    def _parse_schedule_response(self, response_text):
        """Parse Gemini's response into a structured schedule"""
        try:
            # First, try to extract any JSON-like schedule data
            schedule_data = json.loads(response_text)
            df = pd.DataFrame(schedule_data)
            
            # Ensure all times are in HH:MM format
            df['Start Time'] = pd.to_datetime(df['Start Time']).dt.strftime('%H:%M')
            df['End Time'] = pd.to_datetime(df['End Time']).dt.strftime('%H:%M')
            
            return df
        except:
            # If parsing fails, return the raw response
            return response_text
    
    def adjust_schedule(self, task_name, new_requirements):
        """Adjust the schedule based on new requirements"""
        prompt = f"""
        {self.system_prompt}
        
        Current schedule state:
        {self.schedule.to_json()}
        
        Task to adjust: {task_name}
        New requirements: {new_requirements}
        
        Please provide:
        1. Analysis of the impact on the current schedule
        2. Suggested adjustments
        3. Any conflicts that might arise
        4. Alternative solutions if needed
        """
        
        response = self.model.generate_content(prompt)
        return self._parse_schedule_response(response.candidates[0].content.parts[0].text)
    
    def get_schedule(self):
        """Return the current schedule"""
        return self.schedule
    
    def save_schedule(self, filename):
        """Save the schedule to a file"""
        self.schedule.to_csv(filename, index=False)
    
    def load_schedule(self, filename):
        """Load a schedule from a file"""
        self.schedule = pd.read_csv(filename) 