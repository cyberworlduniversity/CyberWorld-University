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



def admin_payload():
    return request.get_json(silent=True) or {}


def required_text(data, key):
    value = str(data.get(key, "")).strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def course_data(data, existing=None):
    existing = existing or {}
    title = required_text(data, "title")
    category = required_text(data, "category")
    slug = str(data.get("slug") or title).strip().lower()
    slug = "".join(ch if ch.isalnum() or ch == " " else "-" for ch in slug).replace(" ", "-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    payload = {
        "title": title,
        "slug": slug.strip("-"),
        "category": category,
        "level": str(data.get("level", "Beginner")).strip() or "Beginner",
        "instructor": str(data.get("instructor", "CWU Academy")).strip() or "CWU Academy",
        "description": str(data.get("description", "")).strip(),
        "objectives": str(data.get("objectives", "")).strip(),
        "requirements": str(data.get("requirements", "")).strip(),
        "durationMinutes": int(data.get("durationMinutes", data.get("duration", 0)) or 0),
        "price": str(data.get("price", "Free")).strip() or "Free",
        "thumbnail": str(data.get("thumbnail", "")).strip(),
        "status": str(data.get("status", existing.get("status", "draft"))).strip().lower(),
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }
    if payload["status"] not in {"draft", "published"}:
        raise ValueError("status must be draft or published")
    return payload


@app.get("/api/admin/courses")
@firebase_user_required("admin")
def admin_courses():
    docs = db.collection("courses").order_by("createdAt", direction=firestore.Query.DESCENDING).stream()
    return jsonify({"courses": [serialize(doc) for doc in docs]})


@app.post("/api/admin/courses")
@firebase_user_required("admin")
def admin_create_course():
    data = admin_payload()
    try:
        payload = course_data(data)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid course data"}), 400
    payload["createdAt"] = firestore.SERVER_TIMESTAMP
    payload["createdBy"] = request.cwu_user["uid"]
    ref = db.collection("courses").document()
    ref.set(payload)
    return jsonify({"course": serialize(ref.get())}), 201


@app.put("/api/admin/courses/<course_id>")
@firebase_user_required("admin")
def admin_update_course(course_id):
    ref = db.collection("courses").document(course_id)
    doc = ref.get()
    if not doc.exists:
        return jsonify({"error": "Course not found"}), 404
    try:
        payload = course_data(admin_payload(), doc.to_dict())
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid course data"}), 400
    ref.update(payload)
    return jsonify({"course": serialize(ref.get())})


@app.delete("/api/admin/courses/<course_id>")
@firebase_user_required("admin")
def admin_delete_course(course_id):
    ref = db.collection("courses").document(course_id)
    if not ref.get().exists:
        return jsonify({"error": "Course not found"}), 404
    ref.delete()
    return jsonify({"message": "Course deleted"})


@app.get("/api/admin/courses/<course_id>/phases")
@firebase_user_required("admin")
def admin_course_phases(course_id):
    if not db.collection("courses").document(course_id).get().exists:
        return jsonify({"error": "Course not found"}), 404
    docs = db.collection("course_phases").where("courseId", "==", course_id).order_by("sortOrder").stream()
    return jsonify({"phases": [serialize(doc) for doc in docs]})


@app.post("/api/admin/courses/<course_id>/phases")
@firebase_user_required("admin")
def admin_create_phase(course_id):
    if not db.collection("courses").document(course_id).get().exists:
        return jsonify({"error": "Course not found"}), 404
    data = admin_payload()
    try:
        title = required_text(data, "title")
        sort_order = int(data.get("sortOrder", 1))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid phase data"}), 400
    ref = db.collection("course_phases").document()
    ref.set({
        "courseId": course_id,
        "title": title,
        "description": str(data.get("description", "")).strip(),
        "sortOrder": sort_order,
        "status": str(data.get("status", "draft")).strip().lower(),
        "createdAt": firestore.SERVER_TIMESTAMP,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    })
    return jsonify({"phase": serialize(ref.get())}), 201


@app.put("/api/admin/phases/<phase_id>")
@firebase_user_required("admin")
def admin_update_phase(phase_id):
    ref = db.collection("course_phases").document(phase_id)
    doc = ref.get()
    if not doc.exists:
        return jsonify({"error": "Phase not found"}), 404
    data = admin_payload()
    try:
        title = required_text(data, "title")
        sort_order = int(data.get("sortOrder", 1))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid phase data"}), 400
    ref.update({
        "title": title,
        "description": str(data.get("description", "")).strip(),
        "sortOrder": sort_order,
        "status": str(data.get("status", "draft")).strip().lower(),
        "updatedAt": firestore.SERVER_TIMESTAMP,
    })
    return jsonify({"phase": serialize(ref.get())})


@app.delete("/api/admin/phases/<phase_id>")
@firebase_user_required("admin")
def admin_delete_phase(phase_id):
    ref = db.collection("course_phases").document(phase_id)
    if not ref.get().exists:
        return jsonify({"error": "Phase not found"}), 404
    ref.delete()
    return jsonify({"message": "Phase deleted"})


@app.get("/api/admin/stats")
@firebase_user_required("admin")
def admin_stats():
    collections = [
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
    stats = {name: len(list(db.collection(name).stream())) for name in collections}
    stats["students"] = len(list(db.collection("users").where("role", "==", "student").stream()))
    stats["admins"] = len(list(db.collection("users").where("role", "==", "admin").stream()))
    return jsonify(stats)


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
    )
