// Mirrors services/gateway/app/schemas.py — keep in sync.

export type Emotion = "neutral" | "friendly" | "serious" | "excited" | "sad";
export type Transition = "cut" | "fade" | "wipeleft" | "slideright";

export interface Scene {
  scene_id: string;
  avatar: {
    avatar_id: string;
    mode: "base_video" | "still_portrait";
    scale: number;
    position: { x: number; y: number };
    matting: "none" | "greenscreen" | "alpha";
  };
  voice: {
    voice_id: string;
    input_text: string;
    language: string;
    speed: number;
    pitch_semitones: number;
    emotion: Emotion;
  };
  background: { type: "color" | "image" | "video"; value: string; fit: "cover" | "contain" };
  overlays: unknown[];
  transition: Transition;
  captions: boolean;
}

export interface VideoRequest {
  title: string;
  dimension: { width: number; height: number };
  fps: number;
  scenes: Scene[];
  test_mode: boolean;
}

export interface JobStatus {
  job_id: string;
  status: "queued" | "synthesizing" | "rendering" | "compositing" | "completed" | "failed";
  progress: number;
  video_url?: string | null;
  error?: string | null;
}

export const newScene = (): Scene => ({
  scene_id: Math.random().toString(36).slice(2, 14),
  avatar: {
    avatar_id: "",
    mode: "base_video",
    scale: 1.0,
    position: { x: 0.5, y: 0.5 },
    matting: "none",
  },
  voice: {
    voice_id: "",
    input_text: "",
    language: "en",
    speed: 1.0,
    pitch_semitones: 0,
    emotion: "neutral",
  },
  background: { type: "color", value: "#0b0f19", fit: "cover" },
  overlays: [],
  transition: "cut",
  captions: false,
});
