# CWU Flask + MySQL backend

This directory contains the server-side foundation for Cyber World University.

## Setup
1. Run schema.sql in MySQL.
2. Copy .env.example to .env and set real credentials.
3. Create a Python virtual environment.
4. Install dependencies with pip install -r requirements.txt.
5. Start with python app.py.

The existing static frontend remains usable. The next integration step is replacing its localStorage calls with authenticated API requests.

Never commit .env, production passwords, or secret keys.
