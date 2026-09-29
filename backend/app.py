import json
import os
from functools import wraps

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import auth, credentials, firestore
from flask import Flask, jsonify, request
from flask_cors import CORS

load_dotenv()

app = Flask(__name__)
CORS(app, supports_credentials=False)

def _init_firebase():
    if firebase_admin._apps:
        return firebase_admin.get_app()

    service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if service_account_json:
        info = json.loads(service_account_json)
        return firebase_admin.initialize_app(credentials.Certificate(info))

    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if credentials_path:
        return firebase_admin.initialize_app(
            credentials.Certificate(credentials_path)
        )

    # Uses Application Default Credentials when running in a trusted environment.
    return firebase_admin.initialize_app()

_init_firebase()
db = firestore.client()


def firebase_user_required(role=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return jsonify({"error": "Firebase ID token required"}), 401

            token = header[7:].strip()
            if not token:
                return jsonify({"error": "Firebase ID token required"}), 401

            try:
                decoded = auth.verify_id_token(token)
            except Exception:
                return jsonify({"error": "Invalid or expired Firebase ID token"}), 401

            uid = decoded["uid"]
            profile = db.collection("users").document(uid).get()
            if not profile.exists:
                return jsonify({"error": "User profile not found"}), 403

            user = profile.to_dict() or {}
            user.update({"uid": uid, "email": decoded.get("email")})
            if role and user.get("role") != role:
                return jsonify({"error": "Forbidden"}), 403

            request.cwu_user = user
            return fn(*args, **kwargs)

        return wrapper
    return decorator


def serialize(doc):
    data = doc.to_dict() or {}
    data["id"] = doc.id
    return data


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "CWU Python 3 API", "database": "Firebase Firestore"})


@app.get("/api/auth/me")
@firebase_user_required()
def me():
    return jsonify({"user": request.cwu_user})


@app.get("/api/courses")
def courses():
    query = (
        db.collection("courses")
        .where("status", "==", "published")
        .order_by("createdAt", direction=firestore.Query.DESCENDING)
    )
    return jsonify({"courses": [serialize(doc) for doc in query.stream()]})


@app.get("/api/courses/<course_id>")
def course_detail(course_id):
    course_ref = db.collection("courses").document(course_id)
    course_doc = course_ref.get()

    if not course_doc.exists:
        return jsonify({"error": "Course not found"}), 404

    course = serialize(course_doc)
    if course.get("status") != "published":
        return jsonify({"error": "Course not found"}), 404

    phases_query = (
        db.collection("course_phases")
        .where("courseId", "==", course_id)
        .where("status", "==", "published")
        .order_by("sortOrder")
    )
    course["phases"] = [serialize(doc) for doc in phases_query.stream()]
    return jsonify({"course": course})


@app.post("/api/enrollments")
@firebase_user_required("student")
def enroll():
    data = request.get_json(silent=True) or {}
    course_id = str(data.get("course_id", "")).strip()
    if not course_id:
        return jsonify({"error": "course_id is required"}), 400

    uid = request.cwu_user["uid"]
    course_ref = db.collection("courses").document(course_id)
    course_doc = course_ref.get()

    if not course_doc.exists:
        return jsonify({"error": "Course not found"}), 404

    course = serialize(course_doc)
    if course.get("status") != "published":
        return jsonify({"error": "Course not found"}), 404

    existing = (
        db.collection("enrollments")
        .where("studentId", "==", uid)
        .where("courseId", "==", course_id)
        .limit(1)
        .stream()
    )
    if next(existing, None):
        return jsonify({"message": "Already enrolled", "course": course})

    enrollment_ref = db.collection("enrollments").document()
    enrollment_ref.set({
        "studentId": uid,
        "courseId": course_id,
        "progress": 0,
        "status": "active",
        "enrolledAt": firestore.SERVER_TIMESTAMP,
    })
    return jsonify({"message": "Enrollment successful", "course": course}), 201


@app.get("/api/student/enrollments")
@firebase_user_required("student")
def student_enrollments():
    uid = request.cwu_user["uid"]
    enrollment_docs = (
        db.collection("enrollments")
        .where("studentId", "==", uid)
        .order_by("enrolledAt", direction=firestore.Query.DESCENDING)
        .stream()
    )

    result = []
    for enrollment_doc in enrollment_docs:
        enrollment = serialize(enrollment_doc)
        course_id = enrollment.get("courseId")
        if not course_id:
            continue

        course_doc = db.collection("courses").document(course_id).get()
        if not course_doc.exists:
            continue

        course = serialize(course_doc)
        result.append({
            "enrollmentId": enrollment["id"],
            "courseId": course_id,
            "title": course.get("title", ""),
            "slug": course.get("slug", ""),
            "thumbnail": course.get("thumbnail", ""),
            "level": course.get("level", ""),
            "durationMinutes": course.get("durationMinutes", 0),
            "progress": enrollment.get("progress", 0),
            "status": enrollment.get("status", "active"),
            "enrolledAt": enrollment.get("enrolledAt"),
        })

    return jsonify({"enrollments": result})


@app.get("/api/admin/stats")
@firebase_user_required("admin")
def admin_stats():
    collections = [
        "users",
        "courses",
        "course_phases",
        "lessons",
        "videos",
        "materials",
        "questions",
        "quizzes",
        "exams",
        "certificates",
        "advertisements",
    ]
    stats = {}
    for name in collections:
        stats[name] = len(list(db.collection(name).stream()))
    return jsonify(stats)


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
    )
