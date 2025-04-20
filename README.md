# Personal Scheduler Assistant

A smart scheduling assistant powered by Google's Gemini AI that helps you manage your weekly schedule efficiently.

## Features

- Natural language interaction for scheduling tasks
- Smart schedule generation based on priorities and restrictions
- Conflict detection and resolution
- Schedule adjustments during the week
- Task prioritization
- Persistent storage of schedules

## Setup

1. Clone this repository
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the root directory and add your Google API key:
   ```
   GOOGLE_API_KEY=your_api_key_here
   ```
4. Run the application:
   ```bash
   streamlit run app.py
   ```

## Usage

1. Start the application and you'll see the chat interface
2. Describe your tasks and schedule requirements in natural language
3. The assistant will generate a schedule based on your input
4. Review and modify the schedule as needed
5. During the week, you can ask the assistant to make adjustments to your schedule

## Example Commands

- "I have a meeting on Monday at 2 PM that will last 1 hour"
- "I need to study for 3 hours on Tuesday for my math test"
- "Can you add grocery shopping on Wednesday afternoon?"
- "I need more time for my project, can you adjust the schedule?"
- "What's my schedule for tomorrow?"

## Note

Make sure to keep your Google API key secure and never share it publicly. 