# CWU Python 3 + Flask + Firebase backend

This directory contains the Python 3 backend API for Cyber World University.

## Stack

- Python 3
- Flask
- Firebase Admin SDK
- Firebase Authentication
- Cloud Firestore
- Firebase Storage can be added for server-side file operations

MySQL is no longer required by this backend.

## Local setup

1. Create a Python 3 virtual environment.
2. Install dependencies:

   `pip install -r requirements.txt`

3. Create a Firebase service-account credential in Firebase/Google Cloud Console.
4. Keep the service-account JSON outside GitHub.
5. Set `GOOGLE_APPLICATION_CREDENTIALS` to the credential file path, or set `FIREBASE_SERVICE_ACCOUNT_JSON` to the JSON object in a secure environment variable.
6. Start the API:

   `python app.py`

The API verifies Firebase ID tokens from the frontend. Protected requests must send:

`Authorization: Bearer <firebase-id-token>`

## Important security rules

- Never commit a Firebase service-account JSON file.
- Never put service-account private keys in frontend files.
- Firebase web configuration may remain in the browser application.
- Use HTTPS in production.
- Keep admin authorization in Firestore rules and backend checks.

## Main API routes

- `GET /api/health`
- `GET /api/auth/me`
- `GET /api/courses`
- `GET /api/courses/<course_id>`
- `POST /api/enrollments`
- `GET /api/student/enrollments`
- `GET /api/admin/stats`

The remaining admin CRUD endpoints will be migrated from the legacy MySQL implementation to Firestore in the next phase.
