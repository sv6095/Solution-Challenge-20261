/**
 * Firebase Auth "Option 4" — self-host the sign-in helper assets under your SPA origin.
 * Run automatically before `vite build` when VITE_FIREBASE_PROJECT_ID is set (e.g. on Vercel).
 *
 * With VITE_FIREBASE_AUTH_DOMAIN set to the hostname that serves THIS app (not *.firebaseapp.com),
 * signInWithRedirect works in storage-partitioned browsers (Chrome 115+, Safari 16.1+, etc.).
 *
 * @see https://firebase.google.com/docs/auth/web/redirect-best-practices
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.join(__dirname, "..");
const publicDir = path.join(frontendRoot, "public");

const projectId = (process.env.VITE_FIREBASE_PROJECT_ID || "").trim();

if (!projectId) {
  console.warn(
    "[sync-firebase-auth-assets] VITE_FIREBASE_PROJECT_ID unset — skipping (OK for builds without Firebase web auth).",
  );
  process.exit(0);
}

const base = `https://${projectId}.firebaseapp.com`;

/** @type {Array<[string, string]>} */
const files = [
  ["__/auth/handler", "__/auth/handler"],
  ["__/auth/handler.js", "__/auth/handler.js"],
  ["__/auth/experiments.js", "__/auth/experiments.js"],
  ["__/auth/iframe", "__/auth/iframe"],
  ["__/auth/iframe.js", "__/auth/iframe.js"],
  ["__/auth/links", "__/auth/links"],
  ["__/auth/links.js", "__/auth/links.js"],
  ["__/firebase/init.json", "__/firebase/init.json"],
];

async function main() {
  for (const [urlPath, relOut] of files) {
    const url = `${base}/${urlPath}`;
    const outPath = path.join(publicDir, ...relOut.split("/"));
    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    const res = await fetch(url, { redirect: "follow" });
    if (!res.ok) {
      if (urlPath.includes("experiments.js")) {
        console.warn(`[sync-firebase-auth-assets] Optional ${urlPath} missing (${res.status}), skipping.`);
        continue;
      }
      console.error(`[sync-firebase-auth-assets] ${url} → HTTP ${res.status}`);
      process.exit(1);
    }
    const buf = Buffer.from(await res.arrayBuffer());
    fs.writeFileSync(outPath, buf);
    console.log(`[sync-firebase-auth-assets] ${relOut} (${buf.length} bytes)`);
  }
}

main().catch((err) => {
  console.error("[sync-firebase-auth-assets]", err);
  process.exit(1);
});
