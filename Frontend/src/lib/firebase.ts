import { initializeApp, type FirebaseApp } from "firebase/app";
import { getAuth, type Auth } from "firebase/auth";
import { getFirestore, type Firestore } from "firebase/firestore";

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

/** Firestore + config sanity (maps etc.). */
export const hasFirebaseConfig = Boolean(
  firebaseConfig.apiKey && firebaseConfig.projectId && firebaseConfig.appId,
);

/**
 * Google / OAuth sign-in requires `authDomain` (e.g. `your-project.firebaseapp.com`).
 * Without it, `signInWithPopup` fails early or returns opaque errors.
 */
export const hasFirebaseAuthConfig = Boolean(
  hasFirebaseConfig && String(firebaseConfig.authDomain ?? "").trim().length > 0,
);

let app: FirebaseApp | null = null;
let db: Firestore | null = null;
let auth: Auth | null = null;

if (hasFirebaseConfig) {
  app = initializeApp(firebaseConfig);
  db = getFirestore(app);
  if (hasFirebaseAuthConfig) {
    auth = getAuth(app);
  }
}

export function getFirebaseApp(): FirebaseApp | null {
  return app;
}

/** Singleton Auth instance; required for Google sign-in. */
export function getFirebaseAuth(): Auth | null {
  return auth;
}

export { db };
