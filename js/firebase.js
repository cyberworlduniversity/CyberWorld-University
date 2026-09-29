import { initializeApp } from "https://www.gstatic.com/firebasejs/12.19.0/firebase-app.js";
import {
  getAuth,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  signOut,
  onAuthStateChanged,
  updateProfile
} from "https://www.gstatic.com/firebasejs/12.19.0/firebase-auth.js";
import {
  getFirestore,
  doc,
  getDoc,
  setDoc,
  serverTimestamp
} from "https://www.gstatic.com/firebasejs/12.19.0/firebase-firestore.js";
import { firebaseConfig } from "../firebase-config.js";

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);
const API_BASE = "https://cyberworld-university.onrender.com/api";

async function currentUser() {
  if (auth.currentUser) return auth.currentUser;
  return new Promise(resolve => {
    const unsubscribe = onAuthStateChanged(auth, user => {
      unsubscribe();
      resolve(user);
    });
  });
}

async function apiRequest(path, options = {}) {
  const user = await currentUser();
  const token = user ? await user.getIdToken() : null;
  const response = await fetch(API_BASE + path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: "Bearer " + token } : {}),
      ...(options.headers || {})
    }
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || data.message || ("API request failed (" + response.status + ")"));
  }
  return data;
}

const api = {
  app,
  auth,
  db,
  apiBase: API_BASE,

  async register(name, email, password) {
    const credential = await createUserWithEmailAndPassword(auth, email, password);
    await updateProfile(credential.user, { displayName: name });
    await setDoc(doc(db, "users", credential.user.uid), {
      name,
      email,
      role: "student",
      createdAt: serverTimestamp()
    });
    return credential.user;
  },

  async login(email, password) {
    const credential = await signInWithEmailAndPassword(auth, email, password);
    return credential.user;
  },

  async logout() {
    await signOut(auth);
    localStorage.removeItem("cwu_user");
  },

  currentUser,

  async userProfile(uid) {
    const snapshot = await getDoc(doc(db, "users", uid));
    return snapshot.exists() ? { id: snapshot.id, ...snapshot.data() } : null;
  },

  async me() {
    return apiRequest("/auth/me");
  },

  async courses() {
    const data = await apiRequest("/courses");
    return data.courses || [];
  },

  async course(courseId) {
    return apiRequest("/courses/" + encodeURIComponent(courseId));
  },

  async enroll(courseId) {
    return apiRequest("/enrollments", {
      method: "POST",
      body: JSON.stringify({ course_id: courseId })
    });
  },

  async enrollments() {
    const data = await apiRequest("/student/enrollments");
    return data.enrollments || [];
  },

  async studentCourse(courseId) {
    return apiRequest("/student/courses/" + encodeURIComponent(courseId));
  },

  async completeLesson(courseId, lessonId) {
    return apiRequest(
      "/student/courses/" + encodeURIComponent(courseId) +
      "/lessons/" + encodeURIComponent(lessonId) + "/complete",
      { method: "POST", body: JSON.stringify({}) }
    );
  },

  async quizzes() {
    const data = await apiRequest("/student/quizzes");
    return data.quizzes || [];
  },

  async quiz(quizId) {
    return apiRequest("/student/quizzes/" + encodeURIComponent(quizId));
  },

  async exams() {
    const data = await apiRequest("/student/exams");
    return data.exams || [];
  },

  async exam(examId) {
    return apiRequest("/student/exams/" + encodeURIComponent(examId));
  },

  async submitExam(examId, answers) {
    return apiRequest("/student/exams/" + encodeURIComponent(examId) + "/submit", {
      method: "POST", body: JSON.stringify({ answers })
    });
  },

  async certificates() {
    const data = await apiRequest("/student/certificates");
    return data.certificates || [];
  },

  async submitQuiz(quizId, answers) {
    return apiRequest("/student/quizzes/" + encodeURIComponent(quizId) + "/submit", {
      method: "POST",
      body: JSON.stringify({ answers })
    });
  },

  async adminStats() {
    return apiRequest("/admin/stats");
  }
};

window.CWU = api;
