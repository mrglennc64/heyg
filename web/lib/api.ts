import type { JobStatus, VideoRequest } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

// Dev-tool convention: the key lives in localStorage, entered once in the UI.
// For anything internet-facing, put a real auth proxy in front instead.
export const getApiKey = () =>
  typeof window === "undefined" ? "" : localStorage.getItem("forge_api_key") ?? "";
export const setApiKey = (k: string) => localStorage.setItem("forge_api_key", k);

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "X-Api-Key": getApiKey(),
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...init?.headers,
    },
  });
  if (!res.ok) {
    const detail = await res.json().then((j) => j.detail).catch(() => res.statusText);
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json();
}

export const generateVideo = (req: VideoRequest) =>
  call<{ job_id: string }>("/api/v1/generate-avatar-video", {
    method: "POST",
    body: JSON.stringify(req),
  });

export const jobStatus = (jobId: string) => call<JobStatus>(`/api/v1/jobs/${jobId}`);

// ── asset registry ──────────────────────────────────────────
export interface AvatarInfo { avatar_id: string; name: string; kind: string }
export interface VoiceInfo { voice_id: string; name: string }

export const listAvatars = () => call<AvatarInfo[]>("/api/v1/avatars");
export const listVoices = () => call<VoiceInfo[]>("/api/v1/voices");

export const registerAvatar = (name: string, kind: string, media: File) => {
  const fd = new FormData();
  fd.set("name", name); fd.set("kind", kind); fd.set("media", media);
  return call<AvatarInfo>("/api/v1/avatars", { method: "POST", body: fd });
};

export const registerVoice = (name: string, sample: File, consent: File) => {
  const fd = new FormData();
  fd.set("name", name); fd.set("sample", sample); fd.set("consent", consent);
  return call<VoiceInfo>("/api/v1/voices", { method: "POST", body: fd });
};
