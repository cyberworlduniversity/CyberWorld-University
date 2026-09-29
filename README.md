# Cyber World University (CWU)

Complete responsive **HTML + CSS + JavaScript** project starter for the Cyber World University online cybersecurity learning platform.

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
- Videos management UI
- Study materials management UI
- Question bank with 100 seeded questions
- Quiz management UI
- Final examination management UI
- Certificate management UI
- Advertisement management
- Student management
- Website content/settings

## Demo accounts

Student:
- Email: `student@cwu.example`
- Password: `student123`

Admin:
- Email: `admin@cwu.example`
- Password: `admin123`

## Run

No server is required for this frontend demo.

1. Extract the ZIP.
2. Open `index.html` in a browser.
3. For a better development experience, use VS Code + Live Server.

## Important architecture note

This ZIP is a functional frontend/prototype. It uses `localStorage` as a temporary browser database so the course, question, student, enrollment and advertisement demos work without a server.

For production, replace the demo localStorage layer with a backend such as:

Frontend: HTML/CSS/JavaScript
Backend: Python Flask
Database: MySQL
File storage: secure server/object storage
Authentication: server-side sessions + password hashing
Uploads: server-side MIME/type/size validation
Security: CSRF protection, authorization, secure cookies, validation and access controls

Do NOT use the demo admin password or client-side authentication in a production deployment.

## Project structure

CyberWorldUniversity/
├── index.html
├── courses.html
├── course-details.html
├── study-materials.html
├── quizzes.html
├── certificates.html
├── about.html
├── contact.html
├── login.html
├── register.html
├── dashboard.html
├── admin/
├── css/
└── js/
