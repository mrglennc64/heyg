"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { listProjects, saveProject, type StoredProject } from "@/lib/projects";
import { newScene } from "@/lib/types";

const CREATE_CARDS = [
  { emoji: "🧑‍💻", title: "Avatar video", desc: "Script → talking-head video", href: "/editor" },
  { emoji: "🌍", title: "Translate video", desc: "Re-dub a project in 17 languages", href: "/editor?mode=translate" },
  { emoji: "🖼️", title: "Photo avatar", desc: "Animate a single portrait", href: "/avatars" },
  { emoji: "🎙️", title: "Clone a voice", desc: "30 s sample → your voice, any language", href: "/voices" },
];

const THUMB_COLORS = ["#6440fb", "#0ea5e9", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6"];

export default function Home() {
  const router = useRouter();
  const [projects, setProjects] = useState<StoredProject[]>([]);
  const [prompt, setPrompt] = useState("");
  const [greeting, setGreeting] = useState("Welcome back");

  useEffect(() => {
    setProjects(listProjects());
    const h = new Date().getHours();
    setGreeting(h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening");
  }, []);

  const startFromPrompt = () => {
    const scene = newScene();
    scene.voice.input_text = prompt;
    const id = Math.random().toString(36).slice(2, 10);
    saveProject({
      id,
      title: prompt.slice(0, 48) || "untitled",
      updated_at: new Date().toISOString(),
      request: {
        title: prompt.slice(0, 48) || "untitled",
        dimension: { width: 1920, height: 1080 },
        fps: 25, scenes: [scene], test_mode: true,
      },
    });
    router.push(`/editor?project=${id}`);
  };

  return (
    <Shell>
      <div className="hero">
        <h1>{greeting}, Glenn 👋</h1>
        <p>Turn a script into an avatar video — your face, your voice, any language.</p>
        <div className="prompt">
          <input
            placeholder="What will your video say today?"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && startFromPrompt()}
          />
          <button onClick={startFromPrompt}>Create video →</button>
        </div>
      </div>

      <h2>Create</h2>
      <div className="cards">
        {CREATE_CARDS.map((c) => (
          <div key={c.title} className="card" onClick={() => router.push(c.href)}>
            <span className="emoji">{c.emoji}</span>
            <b>{c.title}</b>
            <small>{c.desc}</small>
          </div>
        ))}
      </div>

      <h2>Recent projects</h2>
      {projects.length === 0 ? (
        <div className="empty">No projects yet — create your first video above.</div>
      ) : (
        <div className="projects">
          {projects.slice(0, 8).map((p, i) => (
            <div key={p.id} className="project" onClick={() => router.push(`/editor?project=${p.id}`)}>
              <div className="thumb" style={{ background: THUMB_COLORS[i % THUMB_COLORS.length] }}>
                {p.title.slice(0, 1).toUpperCase()}
              </div>
              <div className="meta">
                <b>{p.title}</b>
                <small>
                  {p.request.scenes.length} scene{p.request.scenes.length > 1 ? "s" : ""} ·{" "}
                  {new Date(p.updated_at).toLocaleDateString()}
                </small>
              </div>
            </div>
          ))}
        </div>
      )}
    </Shell>
  );
}
