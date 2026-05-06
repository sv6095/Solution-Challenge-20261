/**
 * Option 3 (Firebase redirect best practices): proxy /__/auth and /__/firebase to
 * https://<project>.firebaseapp.com so auth helpers run same-site as the SPA.
 * Project id from env only — no hardcoded hosts.
 */

function projectId(): string | null {
  const v = (
    process.env.VITE_FIREBASE_PROJECT_ID ||
    process.env.FIREBASE_PROJECT_ID ||
    ""
  ).trim();
  return v || null;
}

const FB_SEG = "__fb_seg";
const FB_PATH = "__fb_path";

export default async function handler(request: Request): Promise<Response> {
  const incoming = new URL(request.url);
  if (incoming.pathname !== "/api/firebase-host") {
    return new Response("Not Found", { status: 404 });
  }

  const project = projectId();
  if (!project) {
    return new Response(
      JSON.stringify({
        error: "Set VITE_FIREBASE_PROJECT_ID or FIREBASE_PROJECT_ID for this deployment.",
      }),
      { status: 501, headers: { "Content-Type": "application/json" } },
    );
  }

  const seg = incoming.searchParams.get(FB_SEG);
  if (seg !== "auth" && seg !== "firebase") {
    return new Response(JSON.stringify({ error: "Invalid proxy segment." }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const rel = (incoming.searchParams.get(FB_PATH) ?? "").replace(/^\/+/, "");
  const params = new URLSearchParams(incoming.searchParams);
  params.delete(FB_SEG);
  params.delete(FB_PATH);
  const qs = params.toString();

  const pathPart = rel ? `/${rel}` : "";
  const target = `https://${project}.firebaseapp.com/__/${seg}${pathPart}${qs ? `?${qs}` : ""}`;

  return fetch(new Request(target, request));
}
