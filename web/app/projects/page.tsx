"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { deleteProject, listProjects, type StoredProject } from "@/lib/projects";

const THUMB_COLORS = ["#6440fb", "#0ea5e9", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6"];

export default function Projects() {
  const router = useRouter();
  const [projects, setProjects] = useState<StoredProject[]>([]);
  useEffect(() => setProjects(listProjects()), []);

  return (
    <Shell>
      <h1>Projects</h1>
      <p className="sub">All your videos. Projects are stored in this browser.</p>
      {projects.length === 0 ? (
        <div className="empty">Nothing here yet — hit “Create video” in the sidebar.</div>
      ) : (
        <div className="projects">
          {projects.map((p, i) => (
            <div key={p.id} className="project">
              <div className="thumb" style={{ background: THUMB_COLORS[i % THUMB_COLORS.length] }}
                   onClick={() => router.push(`/editor?project=${p.id}`)}>
                {p.last_video_url ? "▶" : p.title.slice(0, 1).toUpperCase()}
              </div>
              <div className="meta">
                <b>{p.title}</b>
                <small>{p.request.scenes.length} scene(s) · {new Date(p.updated_at).toLocaleString()}</small>
                <div className="row" style={{ marginTop: 8 }}>
                  <button className="secondary" onClick={() => router.push(`/editor?project=${p.id}`)}>Edit</button>
                  {p.last_video_url && (
                    <button className="secondary" onClick={() => window.open(p.last_video_url)}>Watch</button>
                  )}
                  <button className="ghost" onClick={() => { deleteProject(p.id); setProjects(listProjects()); }}>🗑</button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </Shell>
  );
}
