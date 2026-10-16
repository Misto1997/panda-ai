// Optional Firebase Auth (Google sign-in). Enabled only when all NEXT_PUBLIC_FIREBASE_* values are set at BUILD time.
import { initializeApp, getApps, type FirebaseApp } from "firebase/app";
import { getAuth, GoogleAuthProvider, onAuthStateChanged, signInWithPopup, signOut as fbSignOut, type User } from "firebase/auth";

const cfg = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

export const authEnabled = Boolean(cfg.apiKey && cfg.authDomain && cfg.projectId && cfg.appId);

function app(): FirebaseApp { return getApps()[0] ?? initializeApp(cfg); }

export const watchAuth = (cb: (u: User | null) => void) => onAuthStateChanged(getAuth(app()), cb);
export const signInGoogle = () => signInWithPopup(getAuth(app()), new GoogleAuthProvider());
export const signOutUser = () => fbSignOut(getAuth(app()));
export const currentIdToken = async (): Promise<string | undefined> => getAuth(app()).currentUser?.getIdToken();
