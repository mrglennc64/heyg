"use client";
import { useEffect, useRef, useState } from "react";
import CanvasStage from "@/components/CanvasStage";
import { generateVideo, getApiKey, jobStatus, setApiKey } from "@/lib/api";
import { newScene, type JobStatus, type Scene, type VideoRequest } from "@/lib/types";

export default function Studio() {
  const [title, setTitle] = useState("untitled");
  const [scenes, setScenes] = useState<Scene[]>([newScene()]);
  const [active, setActive] = useState(0);
  const [apiKey, setKey] = useState("");
  const [job, setJob] = useState<JobStatus | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => setKey(getApiKey()), []);
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const scene = scenes[active];
  const patch = (updater: (s: Scene) => Scene) =>
    setScenes((prev) => prev.map((s, i) => (i === active ? updater(structuredClone(s)) : s)));

  const render = async (testMode: boolean) => {
    setError(null);
    setSubmitting(true);
    const req: VideoRequest = {
      title,
      dimension: { width: 1920, height: 1080 },
      fps: 25,
      scenes,
      test_mode: testMode,
    };
    try {
      const { job_id } = await generateVideo(req);
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        try {
          const s = await jobStatus(job_id);
          setJob(s);
          if (s.status === "completed" || s.status === "failed") {
            if (pollRef.current) clearInterval(pollRef.current);
          }
        } catch { /* transient poll error — keep trying */ }
      }, 4000);
      setJob({ job_id, status: "queued", progress: 0 });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="studio">
      {/* ── left: scene list ── */}
      <div className="col">
        <h1>AVATARFORGE STUDIO</h1>
        <label>Project title</label>
        <input value={title} onChange={(e) => setTitle(e.target.value)} />

        <h2>Scenes</h2>
        {scenes.map((s, i) => (
          <div key={s.scene_id}
               className={`scene-item ${i === active ? "active" : ""}`}
               onClick={() => setActive(i)}>
            Scene {i + 1}
            <small>{s.voice.input_text.slice(0, 42) || "(no script)"} · {s.voice.language}</small>
          </div>
        ))}
        <div className="row">
          <button className="secondary"
                  onClick={() => { setScenes([...scenes, newScene()]); setActive(scenes.length); }}>
            + Add scene
          </button>
          <button className="secondary" disabled={scenes.length < 2}
                  onClick={() => { setScenes(scenes.filter((_, i) => i !== active)); setActive(0); }}>
            Delete
          </button>
        </div>

        <h2>Connection</h2>
        <label>API key</label>
        <input type="password" value={apiKey}
               onChange={(e) => { setKey(e.target.value); setApiKey(e.target.value); }} />
      </div>

      {/* ── center: canvas + render ── */}
      <div className="col stage-wrap">
        <CanvasStage
          scene={scene}
          onPosition={(x, y) => patch((s) => { s.avatar.position = { x, y }; return s; })}
        />
        <div className="row" style={{ width: "100%", maxWidth: 860 }}>
          <button onClick={() => render(true)} disabled={submitting}>
            {submitting ? "Submitting…" : "Preview (540p test)"}
          </button>
          <button className="secondary" onClick={() => render(false)} disabled={submitting}>
            Render final 1080p
          </button>
        </div>

        {error && <div className="status failed">⚠ {error}</div>}
        {job && (
          <div className={`status ${job.status}`}>
            <b>job {job.job_id}</b> — {job.status}
            {job.status === "completed" && job.video_url && (
              <> · <a href={job.video_url} target="_blank">download MP4</a></>
            )}
            {job.status === "failed" && <> · {job.error}</>}
            <div className="bar"><div style={{ width: `${job.progress * 100}%` }} /></div>
          </div>
        )}
      </div>

      {/* ── right: scene properties ── */}
      <div className="col">
        <h2>Script</h2>
        <textarea
          placeholder="Write for the ear — short sentences. ~150 words ≈ 1 min."
          value={scene.voice.input_text}
          onChange={(e) => patch((s) => { s.voice.input_text = e.target.value; return s; })}
        />

        <h2>Avatar</h2>
        <label>Avatar ID</label>
        <input value={scene.avatar.avatar_id}
               onChange={(e) => patch((s) => { s.avatar.avatar_id = e.target.value; return s; })} />
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
        <label>Voice ID</label>
        <input value={scene.voice.voice_id}
               onChange={(e) => patch((s) => { s.voice.voice_id = e.target.value; return s; })} />
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

        <h2>Transition (into this scene)</h2>
        <select value={scene.transition}
                onChange={(e) => patch((s) => { s.transition = e.target.value as Scene["transition"]; return s; })}>
          {["cut","fade","wipeleft","slideright"].map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>
    </div>
  );
}
