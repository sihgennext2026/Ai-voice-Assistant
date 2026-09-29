
# RAGAVA Project - Quick Run Guide

## 1. Automated Start
Double-click the `run_project.bat` file in the `Backend` folder.
This will open two terminal windows:
1. **Backend Server**: Handles the AI logic, transcription, and speech.
2. **Frontend UI**: Launches the React interface.

## 2. Manual Start
If you prefer running terminals manually:

### Terminal 1: Backend
```powershell
# Navigate to Backend
cd "c:\Autonomus voice agent\Backend"
# Activate Virtual Environment (if not active)
.venv\Scripts\activate
# Start Server
uvicorn api:app --reload
```

### Terminal 2: Frontend
```powershell
# Navigate to Frontend
cd "c:\Autonomus voice agent\Backend\VoiceAssistant"
# Start UI
npm run dev
```

## 3. Accessing the App
Open your browser to the URL shown in the Frontend terminal (usually `http://localhost:5173`).

## Troubleshooting
- **Microphone Error**: Ensure your microphone is connected and not being used by another app.
- **API Key Error**: check your `.env` file in the Backend folder.
