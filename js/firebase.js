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
  collection,
  doc,
  getDoc,
  getDocs,
  addDoc,
  query,
  where,
  orderBy,
  limit,
  serverTimestamp
} from "https://www.gstatic.com/firebasejs/12.19.0/firebase-firestore.js";
import { firebaseConfig } from "../firebase-config.js";

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);

const api = {
  app,
  auth,
  db,

  async register(name, email, password) {
    const credential = await createUserWithEmailAndPassword(auth, email, password);
    await updateProfile(credential.user, { displayName: name });
    await setUserProfile(credential.user, name, email);
    return credential.user;
  },

  async login(email, password) {
    const credential = await signInWithEmailAndPassword(auth, email, password);
    return credential.user;
  },

  async logout() {
    await signOut(auth);
  },

  async currentUser() {
    if (auth.currentUser) return auth.currentUser;
    return new Promise(resolve => {
      const unsubscribe = onAuthStateChanged(auth, user => {
        unsubscribe();
        resolve(user);
      });
    });
  },

  async userProfile(uid) {
    const snapshot = await getDoc(doc(db, "users", uid));
    return snapshot.exists() ? { id: snapshot.id, ...snapshot.data() } : null;
  },

  async courses() {
    const q = query(
      collection(db, "courses"),
      where("status", "==", "published"),
      orderBy("createdAt", "desc")
    );
    const snapshot = await getDocs(q);
    return snapshot.docs.map(item => ({ id: item.id, ...item.data() }));
  },

  async course(courseId) {
    const courseSnapshot = await getDoc(doc(db, "courses", courseId));
    if (!courseSnapshot.exists() || courseSnapshot.data().status !== "published") {
      throw new Error("Course not found");
    }

    const phaseQuery = query(
      collection(db, "course_phases"),
      where("courseId", "==", courseId),
      where("status", "==", "published"),
      orderBy("sortOrder", "asc")
    );
    const phases = await getDocs(phaseQuery);
    return {
      course: { id: courseSnapshot.id, ...courseSnapshot.data() },
      phases: phases.docs.map(item => ({ id: item.id, ...item.data() }))
    };
  },

  async enroll(courseId) {
    const user = await this.currentUser();
    if (!user) throw new Error("Please login before enrolling.");
    if ((await this.userProfile(user.uid))?.role !== "student") {
      throw new Error("Only student accounts can enroll.");
    }

    const existing = await getDocs(query(
      collection(db, "enrollments"),
      where("studentId", "==", user.uid),
      where("courseId", "==", courseId),
      limit(1)
    ));
    if (!existing.empty) return { alreadyEnrolled: true, id: existing.docs[0].id };

    const ref = await addDoc(collection(db, "enrollments"), {
      studentId: user.uid,
      courseId,
      progress: 0,
      status: "active",
      enrolledAt: serverTimestamp()
    });
    return { alreadyEnrolled: false, id: ref.id };
  },

  async enrollments() {
    const user = await this.currentUser();
    if (!user) throw new Error("Authentication required.");
    const snapshot = await getDocs(query(
      collection(db, "enrollments"),
      where("studentId", "==", user.uid),
      orderBy("enrolledAt", "desc")
    ));

    const results = [];
    for (const item of snapshot.docs) {
      const enrollment = { id: item.id, ...item.data() };
      const courseSnapshot = await getDoc(doc(db, "courses", enrollment.courseId));
      if (!courseSnapshot.exists()) continue;
      const course = courseSnapshot.data();
      results.push({
        enrollmentId: item.id,
        courseId: enrollment.courseId,
        title: course.title || "Course",
        thumbnail: course.thumbnail || "",
        level: course.level || "",
        progress: Number(enrollment.progress || 0),
        status: enrollment.status || "active"
      });
    }
    return results;
  }
};

async function setUserProfile(user, name, email) {
  await import("https://www.gstatic.com/firebasejs/12.19.0/firebase-firestore.js").then(async firestore => {
    await firestore.setDoc(doc(db, "users", user.uid), {
      name,
      email,
      role: "student",
      createdAt: serverTimestamp()
    });
  });
}

window.CWU = api;
