"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import CanvasStage from "@/components/CanvasStage";
import {
  generateVideo, jobStatus, listAvatars, listVoices,
  type AvatarInfo, type VoiceInfo,
} from "@/lib/api";
import { getProject, saveProject } from "@/lib/projects";
import { newScene, type JobStatus, type Scene, type VideoRequest } from "@/lib/types";

function Editor() {
  const params = useSearchParams();
  const projectId = params.get("project") ?? Math.random().toString(36).slice(2, 10);

  const [title, setTitle] = useState("untitled");
  const [scenes, setScenes] = useState<Scene[]>([newScene()]);
  const [active, setActive] = useState(0);
  const [avatars, setAvatars] = useState<AvatarInfo[]>([]);
  const [voices, setVoices] = useState<VoiceInfo[]>([]);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const p = getProject(projectId);
    if (p) { setTitle(p.title); setScenes(p.request.scenes); }
    listAvatars().then(setAvatars).catch(() => {});
    listVoices().then(setVoices).catch(() => {});
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const scene = scenes[active];
  const patch = (updater: (s: Scene) => Scene) =>
    setScenes((prev) => prev.map((s, i) => (i === active ? updater(structuredClone(s)) : s)));

  const buildRequest = (testMode: boolean): VideoRequest => ({
    title, dimension: { width: 1920, height: 1080 }, fps: 25, scenes, test_mode: testMode,
  });

  const persist = (extra?: { last_job_id?: string; last_video_url?: string }) =>
    saveProject({
      id: projectId, title, updated_at: new Date().toISOString(),
      request: buildRequest(false), ...extra,
    });

  const render = async (testMode: boolean) => {
    setError(null); setSubmitting(true);
    try {
      const { job_id } = await generateVideo(buildRequest(testMode));
      persist({ last_job_id: job_id });
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        try {
          const s = await jobStatus(job_id);
          setJob(s);
          if (s.status === "completed" || s.status === "failed") {
            if (pollRef.current) clearInterval(pollRef.current);
            if (s.status === "completed") persist({ last_job_id: job_id, last_video_url: s.video_url ?? undefined });
          }
        } catch { /* transient poll error */ }
      }, 3000);
      setJob({ job_id, status: "queued", progress: 0 });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setSubmitting(false); }
  };

  return (
    <div className="editor">
      {/* ── scenes ── */}
      <div className="pane">
        <Link href="/" className="nav-item">← Back to home</Link>
        <h2>Scenes</h2>
        {scenes.map((s, i) => (
          <div key={s.scene_id} className={`scene-item ${i === active ? "active" : ""}`}
               onClick={() => setActive(i)}>
            Scene {i + 1}
            <small>{s.voice.input_text.slice(0, 40) || "(no script)"} · {s.voice.language}</small>
          </div>
        ))}
        <div className="row">
          <button className="secondary"
                  onClick={() => { setScenes([...scenes, newScene()]); setActive(scenes.length); }}>
            + Add
          </button>
          <button className="secondary" disabled={scenes.length < 2}
                  onClick={() => { setScenes(scenes.filter((_, i) => i !== active)); setActive(0); }}>
            Delete
          </button>
        </div>
      </div>

      {/* ── canvas ── */}
      <div className="center">
        <div className="topbar">
          <input value={title} onChange={(e) => { setTitle(e.target.value); }} onBlur={() => persist()} />
          <button onClick={() => render(true)} disabled={submitting}>
            {submitting ? "Submitting…" : "▶ Preview (test)"}
          </button>
          <button className="secondary" onClick={() => render(false)} disabled={submitting}>
            Render 1080p
          </button>
        </div>

        <CanvasStage
          scene={scene}
          onPosition={(x, y) => patch((s) => { s.avatar.position = { x, y }; return s; })}
        />

        {error && <div className="status failed">⚠ {error}</div>}
        {job && (
          <div className={`status ${job.status}`}>
            <b>{job.status === "completed" ? "✔ Ready" : job.status}</b>
            {job.status === "completed" && job.video_url && (
              <> — <a href={job.video_url} target="_blank">watch / download MP4</a></>
            )}
            {job.status === "failed" && <> — {job.error}</>}
            <div className="bar"><div style={{ width: `${job.progress * 100}%` }} /></div>
          </div>
        )}
      </div>

      {/* ── properties ── */}
      <div className="pane">
        <h2>Script</h2>
        <textarea
          placeholder="Write for the ear — short sentences. ~150 words ≈ 1 min."
          value={scene.voice.input_text}
          onChange={(e) => patch((s) => { s.voice.input_text = e.target.value; return s; })}
          onBlur={() => persist()}
        />

        <h2>Avatar</h2>
        <label>Avatar</label>
        <select value={scene.avatar.avatar_id}
                onChange={(e) => patch((s) => { s.avatar.avatar_id = e.target.value; return s; })}>
          <option value="">— choose —</option>
          {avatars.map((a) => <option key={a.avatar_id} value={a.avatar_id}>{a.name}</option>)}
        </select>
        <label>Scale ({scene.avatar.scale.toFixed(2)})</label>
        <input type="range" min={0.2} max={1.6} step={0.05} value={scene.avatar.scale}
               onChange={(e) => patch((s) => { s.avatar.scale = Number(e.target.value); return s; })} />
        <label>Matting</label>
        <select value={scene.avatar.matting}
                onChange={(e) => patch((s) => { s.avatar.matting = e.target.value as Scene["avatar"]["matting"]; return s; })}>
          <option value="none">none</option>
          <option value="greenscreen">greenscreen key</option>
        </select>

        <h2>Voice</h2>
        <label>Voice</label>
        <select value={scene.voice.voice_id}
                onChange={(e) => patch((s) => { s.voice.voice_id = e.target.value; return s; })}>
          <option value="">— choose —</option>
          {voices.map((v) => <option key={v.voice_id} value={v.voice_id}>{v.name}</option>)}
        </select>
        <div className="row">
          <div>
            <label>Language</label>
            <select value={scene.voice.language}
                    onChange={(e) => patch((s) => { s.voice.language = e.target.value; return s; })}>
              {["en","es","fr","de","it","pt","pl","tr","ru","nl","cs","ar","zh","ja","hu","ko","hi"]
                .map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </div>
          <div>
            <label>Emotion</label>
            <select value={scene.voice.emotion}
                    onChange={(e) => patch((s) => { s.voice.emotion = e.target.value as Scene["voice"]["emotion"]; return s; })}>
              {["neutral","friendly","serious","excited","sad"]
                .map((em) => <option key={em} value={em}>{em}</option>)}
            </select>
          </div>
        </div>
        <label>Speed ({scene.voice.speed.toFixed(2)}×)</label>
        <input type="range" min={0.5} max={2} step={0.05} value={scene.voice.speed}
               onChange={(e) => patch((s) => { s.voice.speed = Number(e.target.value); return s; })} />
        <label>Pitch ({scene.voice.pitch_semitones} st)</label>
        <input type="range" min={-6} max={6} step={0.5} value={scene.voice.pitch_semitones}
               onChange={(e) => patch((s) => { s.voice.pitch_semitones = Number(e.target.value); return s; })} />

        <h2>Background</h2>
        <div className="row">
          <div>
            <label>Type</label>
            <select value={scene.background.type}
                    onChange={(e) => patch((s) => { s.background.type = e.target.value as Scene["background"]["type"]; return s; })}>
              <option value="color">color</option>
              <option value="image">image</option>
              <option value="video">video</option>
            </select>
          </div>
          <div>
            <label>{scene.background.type === "color" ? "Hex" : "S3 key / URL"}</label>
            <input value={scene.background.value}
                   onChange={(e) => patch((s) => { s.background.value = e.target.value; return s; })} />
          </div>
        </div>

        <h2>Transition</h2>
        <select value={scene.transition}
                onChange={(e) => patch((s) => { s.transition = e.target.value as Scene["transition"]; return s; })}>
          {["cut","fade","wipeleft","slideright"].map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>
    </div>
  );
}

export default function EditorPage() {
  return (
    <Suspense>
      <Editor />
    </Suspense>
  );
}
