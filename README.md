# 🧠 NagrikAI — Backend (FastAPI + Gemini AI)

This repository contains the backend service for NagrikAI, acting as the "Brain" of the civic complaint management platform. Built in a 24-hour hackathon, this backend handles AI-driven information extraction, intelligent clarification loops, SLA routing, and database management. 

The service is built with FastAPI and utilizes the Google Gemini API to parse natural language civic complaints into structured, actionable JSON data.

---

## 📂 Project Structure

Based on our separation of concerns, the backend is modularized into four core files:

- main.py: The FastAPI application server, CORS configuration, and route definitions.
- ai_engine.py: Contains the extraction prompts and the Google Gemini API call functions.
- database.py: Handles the SQLite connection and the insert_ticket() execution.
- constants.py: Stores the ticket JSON schema and the DEPARTMENTS dictionary (mapping 10 fixed categories to departments and SLA hours).

---

## 🔌 API Contract

The frontend and backend communicate exclusively through these three endpoints. 

### 1. POST /api/analyze
Analyzes a new citizen complaint and attempts to extract all necessary fields.
- Request Body: {"text": "..."}
- Response: Returns a finalized ticket JSON. If critical information (like location) is missing, it returns a JSON containing a clarification_question to be handled by the frontend.

### 2. POST /api/clarify
Handles the clarification loop when the AI needs more details from the citizen.
- Request Body: {"original_text": "...", "reply": "..."}
- Response: Merges the texts, re-runs the Gemini extraction, and returns the updated ticket JSON.

### 3. GET /api/tickets
Fetches all saved tickets for the staff dashboard.
- Response: Returns a list of all tickets from the SQLite database, including their current SLA status.

---

## ⚙️ Core Logic & Features

- Smart Clarification Loop: Instead of failing on vague complaints, the backend detects missing fields and asks the user contextual follow-up questions.
- Automated SLA Enforcement: Uses the DEPARTMENTS constant to calculate sla_deadline based on category. Tickets past their deadline are flagged as "breached": true for frontend escalation.
- Edge Case Handling: Prompt logic is designed to navigate multi-issue complaints, handle vague/sarcastic tones, and automatically boost urgency if escalation language is detected.

---

## 🚀 Local Setup & Run Instructions

### 1. Prerequisites
Ensure you have Python 3.8+ installed. 

### 2. Install Dependencies
Navigate to the backend folder and install the required packages:
```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
pip install fastapi uvicorn google-generativeai
