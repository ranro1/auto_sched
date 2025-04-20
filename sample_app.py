import streamlit as st
import google.generativeai as genai
import dotenv
import os

dotenv.load_dotenv()

API_KEY = os.getenv("API_KEY")
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

def get_response(messages):
  try:
    response = model.generate_content(messages)
    return response

  except Exception as e:
    return f"Error {e}"


def fetch_conversation_history():
  if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "user", "parts": "System Prompt: You are TeachGemini - the world's leading expert in teaching and learning. You should help users study or learn any concept they want. Be as helpful as possible but keep your responses brief and under 100 words. Use numbered lists whenever possible."}
    ]

  return st.session_state["messages"]


st.title("TeachGemini")

user_input = st.chat_input("You: ")

if user_input:
  message = fetch_conversation_history()
  message.append({"role": "user", "parts": user_input})
  repsonse = get_response(message)
  message.append({"role": "model", "parts": repsonse.candidates[0].content.parts[0].text}) # get the string from the response

  for message in message:
    if message["role"] == "model":
      st.write(f"TeachGemini: {message['parts']}")
    elif message["role"] == "user" and "System Prompt" not in message["parts"]:
      st.write(f"You: {message['parts']}")

