import json
import os
from functools import wraps
from datetime import datetime, timezone

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
    course["phases"] = []
    for phase_doc in phases_query.stream():
        phase = serialize(phase_doc)
        lesson_query = (
            db.collection("lessons")
            .where("phaseId", "==", phase_doc.id)
            .where("status", "==", "published")
            .order_by("sortOrder")
        )
        phase["lessons"] = [serialize(doc) for doc in lesson_query.stream()]
        course["phases"].append(phase)
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


def phase_exists(phase_id):
    return db.collection("course_phases").document(phase_id).get()


def lesson_payload(data):
    title = required_text(data, "title")
    return {
        "title": title,
        "description": str(data.get("description", "")).strip(),
        "sortOrder": int(data.get("sortOrder", 1) or 1),
        "status": str(data.get("status", "draft")).strip().lower(),
        "durationMinutes": int(data.get("durationMinutes", 0) or 0),
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }


@app.get("/api/admin/phases/<phase_id>/lessons")
@firebase_user_required("admin")
def admin_phase_lessons(phase_id):
    if not phase_exists(phase_id).exists:
        return jsonify({"error": "Phase not found"}), 404
    docs = db.collection("lessons").where("phaseId", "==", phase_id).order_by("sortOrder").stream()
    return jsonify({"lessons": [serialize(doc) for doc in docs]})


@app.post("/api/admin/phases/<phase_id>/lessons")
@firebase_user_required("admin")
def admin_create_lesson(phase_id):
    if not phase_exists(phase_id).exists:
        return jsonify({"error": "Phase not found"}), 404
    try:
        payload = lesson_payload(admin_payload())
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid lesson data"}), 400
    payload.update({
        "phaseId": phase_id,
        "createdAt": firestore.SERVER_TIMESTAMP,
        "createdBy": request.cwu_user["uid"],
    })
    ref = db.collection("lessons").document()
    ref.set(payload)
    return jsonify({"lesson": serialize(ref.get())}), 201


@app.put("/api/admin/lessons/<lesson_id>")
@firebase_user_required("admin")
def admin_update_lesson(lesson_id):
    ref = db.collection("lessons").document(lesson_id)
    if not ref.get().exists:
        return jsonify({"error": "Lesson not found"}), 404
    try:
        payload = lesson_payload(admin_payload())
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid lesson data"}), 400
    ref.update(payload)
    return jsonify({"lesson": serialize(ref.get())})


@app.delete("/api/admin/lessons/<lesson_id>")
@firebase_user_required("admin")
def admin_delete_lesson(lesson_id):
    ref = db.collection("lessons").document(lesson_id)
    if not ref.get().exists:
        return jsonify({"error": "Lesson not found"}), 404
    ref.delete()
    return jsonify({"message": "Lesson deleted"})



def student_enrollment(course_id, uid):
    docs = (
        db.collection("enrollments")
        .where("studentId", "==", uid)
        .where("courseId", "==", course_id)
        .limit(1)
        .stream()
    )
    return next(docs, None)


def published_course_content(course_id):
    phases = (
        db.collection("course_phases")
        .where("courseId", "==", course_id)
        .where("status", "==", "published")
        .order_by("sortOrder")
        .stream()
    )
    result = []
    for phase_doc in phases:
        phase = serialize(phase_doc)
        lessons = (
            db.collection("lessons")
            .where("phaseId", "==", phase_doc.id)
            .where("status", "==", "published")
            .order_by("sortOrder")
            .stream()
        )
        phase["lessons"] = []
        for lesson_doc in lessons:
            lesson = serialize(lesson_doc)
            videos = (
                db.collection("videos")
                .where("lessonId", "==", lesson_doc.id)
                .where("status", "==", "published")
                .order_by("sortOrder")
                .stream()
            )
            materials = (
                db.collection("materials")
                .where("lessonId", "==", lesson_doc.id)
                .where("status", "==", "published")
                .order_by("sortOrder")
                .stream()
            )
            lesson["videos"] = [serialize(doc) for doc in videos]
            lesson["materials"] = [serialize(doc) for doc in materials]
            phase["lessons"].append(lesson)
        result.append(phase)
    return result


@app.get("/api/student/courses/<course_id>")
@firebase_user_required("student")
def student_course(course_id):
    uid = request.cwu_user["uid"]
    enrollment_doc = student_enrollment(course_id, uid)
    if not enrollment_doc:
        return jsonify({"error": "You must enroll in this course first"}), 403

    course_doc = db.collection("courses").document(course_id).get()
    if not course_doc.exists or course_doc.to_dict().get("status") != "published":
        return jsonify({"error": "Course not found"}), 404

    course = serialize(course_doc)
    course["phases"] = published_course_content(course_id)

    progress_docs = (
        db.collection("lesson_progress")
        .where("studentId", "==", uid)
        .where("courseId", "==", course_id)
        .stream()
    )
    progress = {doc.to_dict().get("lessonId"): serialize(doc) for doc in progress_docs}

    total_lessons = sum(len(phase["lessons"]) for phase in course["phases"])
    completed_lessons = sum(
        1 for lesson_id, item in progress.items()
        if item.get("completed") is True
    )
    percentage = round((completed_lessons / total_lessons) * 100) if total_lessons else 0

    course["progress"] = percentage
    course["completedLessons"] = completed_lessons
    course["totalLessons"] = total_lessons

    for phase in course["phases"]:
        for lesson in phase["lessons"]:
            item = progress.get(lesson["id"], {})
            lesson["completed"] = item.get("completed", False)

    return jsonify({"course": course})


@app.post("/api/student/courses/<course_id>/lessons/<lesson_id>/complete")
@firebase_user_required("student")
def complete_student_lesson(course_id, lesson_id):
    uid = request.cwu_user["uid"]
    enrollment_doc = student_enrollment(course_id, uid)
    if not enrollment_doc:
        return jsonify({"error": "You must enroll in this course first"}), 403

    lesson_doc = db.collection("lessons").document(lesson_id).get()
    if not lesson_doc.exists:
        return jsonify({"error": "Lesson not found"}), 404

    lesson = lesson_doc.to_dict() or {}
    if lesson.get("status") != "published":
        return jsonify({"error": "Lesson not found"}), 404

    phase_doc = db.collection("course_phases").document(lesson.get("phaseId", "")).get()
    if not phase_doc.exists or phase_doc.to_dict().get("courseId") != course_id:
        return jsonify({"error": "Lesson does not belong to this course"}), 400

    progress_ref = (
        db.collection("lesson_progress")
        .document(f"{uid}_{course_id}_{lesson_id}")
    )
    progress_ref.set({
        "studentId": uid,
        "courseId": course_id,
        "lessonId": lesson_id,
        "completed": True,
        "completedAt": firestore.SERVER_TIMESTAMP,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }, merge=True)

    total = 0
    completed = 0
    phases = (
        db.collection("course_phases")
        .where("courseId", "==", course_id)
        .where("status", "==", "published")
        .stream()
    )
    for phase in phases:
        lessons = (
            db.collection("lessons")
            .where("phaseId", "==", phase.id)
            .where("status", "==", "published")
            .stream()
        )
        for lesson_item in lessons:
            total += 1
            progress_item = (
                db.collection("lesson_progress")
                .document(f"{uid}_{course_id}_{lesson_item.id}")
                .get()
            )
            if progress_item.exists and (progress_item.to_dict() or {}).get("completed") is True:
                completed += 1

    percentage = round((completed / total) * 100) if total else 0
    db.collection("enrollments").document(enrollment_doc.id).update({
        "progress": percentage,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    })

    return jsonify({
        "message": "Lesson marked complete",
        "progress": percentage,
        "completedLessons": completed,
        "totalLessons": total,
    })




def quiz_exists(quiz_id):
    return db.collection("quizzes").document(quiz_id).get()


def question_payload(data):
    text = required_text(data, "question")
    options = data.get("options") or []
    if not isinstance(options, list) or len(options) < 2:
        raise ValueError("At least two options are required")
    options = [str(item).strip() for item in options if str(item).strip()]
    if len(options) < 2:
        raise ValueError("At least two options are required")
    correct_index = int(data.get("correctIndex", 0))
    if correct_index < 0 or correct_index >= len(options):
        raise ValueError("Invalid correct option")
    question_type = str(data.get("type", "mcq")).strip().lower()
    if question_type not in {"mcq", "true_false"}:
        raise ValueError("Invalid question type")
    return {
        "quizId": required_text(data, "quizId"),
        "question": text,
        "options": options,
        "correctIndex": correct_index,
        "type": question_type,
        "points": int(data.get("points", 1) or 1),
        "status": str(data.get("status", "draft")).strip().lower(),
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }


@app.get("/api/admin/quizzes")
@firebase_user_required("admin")
def admin_quizzes():
    docs = db.collection("quizzes").order_by("createdAt", direction=firestore.Query.DESCENDING).stream()
    return jsonify({"quizzes": [serialize(doc) for doc in docs]})


@app.post("/api/admin/quizzes")
@firebase_user_required("admin")
def admin_create_quiz():
    data = admin_payload()
    try:
        title = required_text(data, "title")
        course_id = required_text(data, "courseId")
        payload = {
            "title": title,
            "courseId": course_id,
            "description": str(data.get("description", "")).strip(),
            "durationMinutes": int(data.get("durationMinutes", 10) or 10),
            "passingScore": int(data.get("passingScore", 50) or 50),
            "status": str(data.get("status", "draft")).strip().lower(),
            "createdAt": firestore.SERVER_TIMESTAMP,
            "updatedAt": firestore.SERVER_TIMESTAMP,
            "createdBy": request.cwu_user["uid"],
        }
        if payload["status"] not in {"draft", "published"}:
            raise ValueError("Invalid status")
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid quiz data"}), 400
    ref = db.collection("quizzes").document()
    ref.set(payload)
    return jsonify({"quiz": serialize(ref.get())}), 201


@app.get("/api/admin/quizzes/<quiz_id>/questions")
@firebase_user_required("admin")
def admin_quiz_questions(quiz_id):
    if not quiz_exists(quiz_id).exists:
        return jsonify({"error": "Quiz not found"}), 404
    docs = db.collection("questions").where("quizId", "==", quiz_id).order_by("createdAt").stream()
    return jsonify({"questions": [serialize(doc) for doc in docs]})


@app.post("/api/admin/questions")
@firebase_user_required("admin")
def admin_create_question():
    data = admin_payload()
    try:
        payload = question_payload(data)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid question data"}), 400
    if not quiz_exists(payload["quizId"]).exists:
        return jsonify({"error": "Quiz not found"}), 404
    payload["createdAt"] = firestore.SERVER_TIMESTAMP
    payload["createdBy"] = request.cwu_user["uid"]
    ref = db.collection("questions").document()
    ref.set(payload)
    return jsonify({"question": serialize(ref.get())}), 201


@app.delete("/api/admin/questions/<question_id>")
@firebase_user_required("admin")
def admin_delete_question(question_id):
    ref = db.collection("questions").document(question_id)
    if not ref.get().exists:
        return jsonify({"error": "Question not found"}), 404
    ref.delete()
    return jsonify({"message": "Question deleted"})


@app.get("/api/student/quizzes")
@firebase_user_required("student")
def student_quizzes():
    uid = request.cwu_user["uid"]
    enrolled_ids = {
        doc.to_dict().get("courseId")
        for doc in db.collection("enrollments").where("studentId", "==", uid).stream()
    }
    result = []
    for doc in db.collection("quizzes").where("status", "==", "published").stream():
        quiz = serialize(doc)
        if quiz.get("courseId") not in enrolled_ids:
            continue
        count = len(list(db.collection("questions").where("quizId", "==", doc.id).where("status", "==", "published").stream()))
        result.append({
            "id": quiz["id"],
            "title": quiz.get("title", ""),
            "description": quiz.get("description", ""),
            "courseId": quiz.get("courseId"),
            "durationMinutes": quiz.get("durationMinutes", 10),
            "passingScore": quiz.get("passingScore", 50),
            "questionCount": count,
        })
    return jsonify({"quizzes": result})


@app.get("/api/student/quizzes/<quiz_id>")
@firebase_user_required("student")
def student_quiz(quiz_id):
    uid = request.cwu_user["uid"]
    quiz_doc = quiz_exists(quiz_id)
    if not quiz_doc.exists or quiz_doc.to_dict().get("status") != "published":
        return jsonify({"error": "Quiz not found"}), 404
    quiz = serialize(quiz_doc)
    if not student_enrollment(quiz.get("courseId"), uid):
        return jsonify({"error": "You must enroll in the course first"}), 403
    questions = []
    for doc in db.collection("questions").where("quizId", "==", quiz_id).where("status", "==", "published").stream():
        item = serialize(doc)
        item.pop("correctIndex", None)
        questions.append(item)
    quiz["questions"] = questions
    return jsonify({"quiz": quiz})


@app.post("/api/student/quizzes/<quiz_id>/submit")
@firebase_user_required("student")
def student_submit_quiz(quiz_id):
    uid = request.cwu_user["uid"]
    quiz_doc = quiz_exists(quiz_id)
    if not quiz_doc.exists or quiz_doc.to_dict().get("status") != "published":
        return jsonify({"error": "Quiz not found"}), 404
    quiz = quiz_doc.to_dict() or {}
    if not student_enrollment(quiz.get("courseId"), uid):
        return jsonify({"error": "You must enroll in the course first"}), 403

    data = request.get_json(silent=True) or {}
    answers = data.get("answers") or {}
    question_docs = list(db.collection("questions").where("quizId", "==", quiz_id).where("status", "==", "published").stream())
    total_points = sum(int((d.to_dict() or {}).get("points", 1) or 1) for d in question_docs)
    earned = 0
    answered = 0
    for doc in question_docs:
        item = doc.to_dict() or {}
        raw = answers.get(doc.id)
        if raw is None:
            continue
        answered += 1
        try:
            selected = int(raw)
        except (TypeError, ValueError):
            continue
        if selected == int(item.get("correctIndex", -1)):
            earned += int(item.get("points", 1) or 1)
    score = round((earned / total_points) * 100) if total_points else 0
    passed = score >= int(quiz.get("passingScore", 50) or 50)

    attempt_ref = db.collection("quiz_attempts").document()
    attempt_ref.set({
        "studentId": uid,
        "quizId": quiz_id,
        "courseId": quiz.get("courseId"),
        "score": score,
        "earnedPoints": earned,
        "totalPoints": total_points,
        "answered": answered,
        "passed": passed,
        "submittedAt": firestore.SERVER_TIMESTAMP,
    })
    return jsonify({
        "message": "Quiz submitted",
        "score": score,
        "passed": passed,
        "earnedPoints": earned,
        "totalPoints": total_points,
        "answered": answered,
    })


def exam_exists(exam_id):
    return db.collection("exams").document(exam_id).get()

def exam_question_payload(data):
    text = required_text(data, "question")
    options = data.get("options") or []
    if not isinstance(options, list):
        raise ValueError("options must be a list")
    options = [str(item).strip() for item in options if str(item).strip()]
    if len(options) < 2:
        raise ValueError("At least two options are required")
    correct_index = int(data.get("correctIndex", 0))
    if correct_index < 0 or correct_index >= len(options):
        raise ValueError("Invalid correct option")
    return {"examId": required_text(data, "examId"), "question": text, "options": options,
            "correctIndex": correct_index, "points": max(1, int(data.get("points", 1) or 1)),
            "status": str(data.get("status", "draft")).strip().lower(), "updatedAt": firestore.SERVER_TIMESTAMP}

@app.get("/api/admin/exams")
@firebase_user_required("admin")
def admin_exams():
    docs = db.collection("exams").order_by("createdAt", direction=firestore.Query.DESCENDING).stream()
    return jsonify({"exams": [serialize(doc) for doc in docs]})

@app.post("/api/admin/exams")
@firebase_user_required("admin")
def admin_create_exam():
    data = admin_payload()
    try:
        course_id = required_text(data, "courseId")
        if not db.collection("courses").document(course_id).get().exists:
            return jsonify({"error": "Course not found"}), 404
        payload = {"title": required_text(data, "title"), "courseId": course_id,
                   "description": str(data.get("description", "")).strip(),
                   "durationMinutes": max(1, int(data.get("durationMinutes", 30) or 30)),
                   "passingScore": max(1, min(100, int(data.get("passingScore", 50) or 50))),
                   "eligibilityProgress": max(0, min(100, int(data.get("eligibilityProgress", 100) or 100))),
                   "status": str(data.get("status", "draft")).strip().lower(),
                   "createdAt": firestore.SERVER_TIMESTAMP, "updatedAt": firestore.SERVER_TIMESTAMP,
                   "createdBy": request.cwu_user["uid"]}
        if payload["status"] not in {"draft", "published"}: raise ValueError("Invalid status")
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid exam data"}), 400
    ref = db.collection("exams").document(); ref.set(payload)
    return jsonify({"exam": serialize(ref.get())}), 201

@app.get("/api/admin/exams/<exam_id>/questions")
@firebase_user_required("admin")
def admin_exam_questions(exam_id):
    if not exam_exists(exam_id).exists: return jsonify({"error": "Exam not found"}), 404
    docs = db.collection("exam_questions").where("examId", "==", exam_id).order_by("createdAt").stream()
    return jsonify({"questions": [serialize(doc) for doc in docs]})

@app.post("/api/admin/exam-questions")
@firebase_user_required("admin")
def admin_create_exam_question():
    try: payload = exam_question_payload(admin_payload())
    except (ValueError, TypeError): return jsonify({"error": "Invalid exam question data"}), 400
    if not exam_exists(payload["examId"]).exists: return jsonify({"error": "Exam not found"}), 404
    payload["createdAt"] = firestore.SERVER_TIMESTAMP; payload["createdBy"] = request.cwu_user["uid"]
    ref = db.collection("exam_questions").document(); ref.set(payload)
    return jsonify({"question": serialize(ref.get())}), 201

@app.delete("/api/admin/exam-questions/<question_id>")
@firebase_user_required("admin")
def admin_delete_exam_question(question_id):
    ref = db.collection("exam_questions").document(question_id)
    if not ref.get().exists: return jsonify({"error": "Question not found"}), 404
    ref.delete(); return jsonify({"message": "Question deleted"})

def certificate_number():
    import secrets
    from datetime import datetime
    return "CWU-" + str(datetime.utcnow().year) + "-" + secrets.token_hex(4).upper()

@app.get("/api/student/exams")
@firebase_user_required("student")
def student_exams():
    uid = request.cwu_user["uid"]
    enrolled_ids = {doc.to_dict().get("courseId") for doc in db.collection("enrollments").where("studentId", "==", uid).stream()}
    result = []
    for doc in db.collection("exams").where("status", "==", "published").stream():
        exam = serialize(doc)
        if exam.get("courseId") not in enrolled_ids: continue
        result.append({"id": exam["id"], "title": exam.get("title", ""), "description": exam.get("description", ""),
                       "courseId": exam.get("courseId"), "durationMinutes": exam.get("durationMinutes", 30),
                       "passingScore": exam.get("passingScore", 50), "eligibilityProgress": exam.get("eligibilityProgress", 100),
                       "questionCount": len(list(db.collection("exam_questions").where("examId", "==", doc.id).where("status", "==", "published").stream()))})
    return jsonify({"exams": result})

@app.get("/api/student/exams/<exam_id>")
@firebase_user_required("student")
def student_exam(exam_id):
    uid = request.cwu_user["uid"]; doc = exam_exists(exam_id)
    if not doc.exists or doc.to_dict().get("status") != "published": return jsonify({"error": "Exam not found"}), 404
    exam = serialize(doc); enrollment_doc = student_enrollment(exam.get("courseId"), uid)
    if not enrollment_doc: return jsonify({"error": "You must enroll in the course first"}), 403
    progress = int((enrollment_doc.to_dict() or {}).get("progress", 0) or 0); eligibility = int(exam.get("eligibilityProgress", 100) or 100)
    if progress < eligibility: return jsonify({"error": f"Complete at least {eligibility}% of the course before taking this exam", "progress": progress, "eligibilityProgress": eligibility}), 403
    questions = []
    for q in db.collection("exam_questions").where("examId", "==", exam_id).where("status", "==", "published").stream():
        item = serialize(q); item.pop("correctIndex", None); questions.append(item)
    if not questions:
        return jsonify({"error": "This examination has no published questions"}), 400
    attempt_ref = db.collection("exam_attempts").document(f"{uid}_{exam_id}")
    active = attempt_ref.get()
    if active.exists and (active.to_dict() or {}).get("status") == "in_progress":
        return jsonify({"error": "An examination attempt is already in progress"}), 409
    attempt_ref.set({
        "studentId": uid, "examId": exam_id, "courseId": exam.get("courseId"),
        "status": "in_progress", "startedAt": firestore.SERVER_TIMESTAMP
    })
    exam["questions"] = questions
    exam["serverStartedAt"] = datetime.now(timezone.utc).isoformat()
    return jsonify({"exam": exam})

@app.post("/api/student/exams/<exam_id>/submit")
@firebase_user_required("student")
def student_submit_exam(exam_id):
    uid = request.cwu_user["uid"]; doc = exam_exists(exam_id)
    if not doc.exists or doc.to_dict().get("status") != "published": return jsonify({"error": "Exam not found"}), 404
    exam = doc.to_dict() or {}; enrollment_doc = student_enrollment(exam.get("courseId"), uid)
    if not enrollment_doc: return jsonify({"error": "You must enroll in the course first"}), 403
    progress = int((enrollment_doc.to_dict() or {}).get("progress", 0) or 0); eligibility = int(exam.get("eligibilityProgress", 100) or 100)
    if progress < eligibility: return jsonify({"error": f"Complete at least {eligibility}% of the course before taking this exam"}), 403
    active_ref = db.collection("exam_attempts").document(f"{uid}_{exam_id}")
    active = active_ref.get()
    if not active.exists:
        return jsonify({"error": "No active examination attempt. Open the exam first."}), 409
    attempt = active.to_dict() or {}
    started = attempt.get("startedAt")
    if not started or not hasattr(started, "timestamp"):
        return jsonify({"error": "Examination start time is unavailable"}), 409
    elapsed = datetime.now(timezone.utc).timestamp() - started.timestamp()
    limit_seconds = max(1, int(exam.get("durationMinutes", 30) or 30)) * 60
    if elapsed > limit_seconds:
        active_ref.update({"status": "expired", "submittedAt": firestore.SERVER_TIMESTAMP})
        return jsonify({"error": "Examination time has expired", "expired": True}), 403
    answers = (request.get_json(silent=True) or {}).get("answers") or {}
    questions = list(db.collection("exam_questions").where("examId", "==", exam_id).where("status", "==", "published").stream())
    total_points = sum(int((q.to_dict() or {}).get("points", 1) or 1) for q in questions); earned = 0; answered = 0
    for q in questions:
        item = q.to_dict() or {}; raw = answers.get(q.id)
        if raw is None: continue
        answered += 1
        try: selected = int(raw)
        except (TypeError, ValueError): continue
        if selected == int(item.get("correctIndex", -1)): earned += int(item.get("points", 1) or 1)
    score = round((earned / total_points) * 100) if total_points else 0; passed = score >= int(exam.get("passingScore", 50) or 50)
    attempt_ref = db.collection("exam_attempts").document()
    attempt_ref.set({"studentId": uid, "examId": exam_id, "courseId": exam.get("courseId"), "score": score,
                     "earnedPoints": earned, "totalPoints": total_points, "answered": answered, "passed": passed,
                     "submittedAt": firestore.SERVER_TIMESTAMP})
    certificate = None
    if passed:
        existing = list(db.collection("certificates").where("studentId", "==", uid).where("courseId", "==", exam.get("courseId")).where("status", "==", "issued").limit(1).stream())
        if existing: certificate = serialize(existing[0])
        else:
            course = (db.collection("courses").document(exam.get("courseId")).get().to_dict() or {})
            ref = db.collection("certificates").document()
            ref.set({"certificateNumber": certificate_number(), "studentId": uid,
                     "studentName": request.cwu_user.get("name") or request.cwu_user.get("email", "CWU Student"),
                     "studentEmail": request.cwu_user.get("email", ""), "courseId": exam.get("courseId"),
                     "courseTitle": course.get("title", ""), "examId": exam_id, "score": score,
                     "status": "issued", "issuedAt": firestore.SERVER_TIMESTAMP, "verificationCode": ref.id})
            certificate = serialize(ref.get())
    return jsonify({"message": "Final examination submitted", "score": score, "passed": passed,
                    "earnedPoints": earned, "totalPoints": total_points, "answered": answered, "certificate": certificate})

@app.get("/api/student/certificates")
@firebase_user_required("student")
def student_certificates():
    uid = request.cwu_user["uid"]
    docs = db.collection("certificates").where("studentId", "==", uid).order_by("issuedAt", direction=firestore.Query.DESCENDING).stream()
    return jsonify({"certificates": [serialize(doc) for doc in docs]})

@app.get("/api/certificates/<certificate_number>")
def verify_certificate(certificate_number):
    docs = db.collection("certificates").where("certificateNumber", "==", certificate_number).where("status", "==", "issued").limit(1).stream()
    doc = next(docs, None)
    if not doc: return jsonify({"valid": False, "error": "Certificate not found"}), 404
    c = serialize(doc)
    return jsonify({"valid": True, "certificate": {"certificateNumber": c.get("certificateNumber"), "studentName": c.get("studentName"),
                                                   "courseTitle": c.get("courseTitle"), "score": c.get("score"),
                                                   "issuedAt": c.get("issuedAt"), "status": c.get("status")}})


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
