from flask import Flask, request, jsonify
from utils import process_calendar_request
import google.generativeai as genai
import os
from google_calendar import get_google_calendar_service

app = Flask(__name__)

# Initialize Gemini model
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-pro')

# Initialize Google Calendar service
try:
    calendar_service, user_info = get_google_calendar_service()
except Exception as e:
    print("Error initializing Google Calendar service:", str(e))
    calendar_service = None
    user_info = None

@app.route('/process_message', methods=['POST'])
def process_message():
    try:
        data = request.get_json()
        user_text = data.get('message', '')
        
        if not user_text:
            return jsonify({'response': "I didn't receive any message. Please try again."}), 400
        
        # Process the message using the utility function
        success, response = process_calendar_request(
            user_text,
            model,
            calendar_service
        )
        
        return jsonify({'response': response})
        
    except Exception as e:
        return jsonify({'response': f"I encountered an error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True) 