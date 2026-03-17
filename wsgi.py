import sys, os
project_home = '/home/focusquest2026/focusquest'
if project_home not in sys.path:
    sys.path.insert(0, project_home)
os.environ['SECRET_KEY'] = 'focusquest-v3-hackathon-2024'
os.environ['GEMINI_API_KEY'] = 'your-gemini-key-here'
from app import app, init_db
init_db()
application = app
