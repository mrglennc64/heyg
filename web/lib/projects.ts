// Local project persistence (browser localStorage) — the self-hosted analog
// of HeyGen's project list until a projects table lands in the gateway.
import type { VideoRequest } from "./types";

export interface StoredProject {
  id: string;
  title: string;
  updated_at: string;          // ISO
  request: VideoRequest;
  last_job_id?: string;
  last_video_url?: string;
}

const KEY = "forge_projects";

export function listProjects(): StoredProject[] {
  if (typeof window === "undefined") return [];
  try {
    const all = JSON.parse(localStorage.getItem(KEY) ?? "[]") as StoredProject[];
    return all.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  } catch {
    return [];
  }
}

export function saveProject(p: StoredProject): void {
  const rest = listProjects().filter((x) => x.id !== p.id);
  localStorage.setItem(KEY, JSON.stringify([{ ...p, updated_at: new Date().toISOString() }, ...rest]));
}

export function getProject(id: string): StoredProject | undefined {
  return listProjects().find((p) => p.id === id);
}

export function deleteProject(id: string): void {
  localStorage.setItem(KEY, JSON.stringify(listProjects().filter((p) => p.id !== id)));
}
