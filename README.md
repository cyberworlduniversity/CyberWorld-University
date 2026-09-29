# Cyber World University (CWU)

Cyber World University is a responsive online cybersecurity learning platform.

## Architecture

- Frontend: HTML + CSS + JavaScript
- Backend: Python 3 + Flask
- Authentication: Firebase Authentication
- Database: Cloud Firestore
- Trusted backend access: Firebase Admin SDK
- Production API: Render Web Service
- Website: static frontend files served separately from the Flask API

## Included

### Public website
- Home
- Courses
- Course Details
- Study Materials
- Quizzes
- Certificates
- About
- Contact
- Student Login
- Student Registration
- Student Dashboard

### Admin panel
- Dashboard
- Course CRUD
- Phase and lesson management
- Videos management
- Study materials management
- Question bank
- Quiz management
- Final examination management
- Certificate management
- Advertisement management
- Student management
- Website content/settings

## Security

- Firebase ID tokens are verified by the Flask backend.
- Admin API routes require an authenticated Firebase user with the admin role.
- Quiz and examination answer keys are not returned to students.
- Quiz/examination timing is enforced server-side.
- Enrollment, lesson-progress, quiz-attempt and exam-attempt writes are protected behind the trusted backend.
- Firebase service-account credentials must remain in secure environment variables and must never be committed to GitHub.
- Firebase browser configuration is public client configuration and is protected by Firebase Security Rules and backend authorization.

## Backend

The Flask backend is in `backend/`.

Install dependencies:

`pip install -r backend/requirements.txt`

Run locally:

`cd backend && python app.py`

Production start command:

`gunicorn --bind 0.0.0.0:$PORT app:app`

Required production secret:

- `FIREBASE_SERVICE_ACCOUNT_JSON`

## Deployment

`render.yaml` defines the Render Python Web Service and uses `/api/health` as its health check.

The current development/production branch for this implementation is:

`cwu-flask-mysql-foundation`

Before promoting to the main production branch, run the final browser and live API smoke tests with the deployed frontend and Render service.

## Repository

GitHub: https://github.com/cyberworlduniversity/CyberWorld-University
