"use client";
import { useEffect, useRef, useState } from "react";
import Shell from "@/components/Shell";
import { listAvatars, registerAvatar, type AvatarInfo } from "@/lib/api";

export default function Avatars() {
  const [avatars, setAvatars] = useState<AvatarInfo[]>([]);
  const [name, setName] = useState("");
  const [kind, setKind] = useState("base_video");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = () => listAvatars().then(setAvatars).catch((e) => setMsg(String(e.message ?? e)));
  useEffect(() => { refresh(); }, []);

  const submit = async () => {
    const file = fileRef.current?.files?.[0];
    if (!name || !file) { setMsg("Name and a media file are required."); return; }
    setBusy(true); setMsg(null);
    try {
      await registerAvatar(name, kind, file);
      setName(""); if (fileRef.current) fileRef.current.value = "";
      setMsg("Avatar registered ✔");
      refresh();
    } catch (e) { setMsg(String((e as Error).message)); }
    finally { setBusy(false); }
  };

  return (
    <Shell>
      <h1>Avatars</h1>
      <p className="sub">Your digital twins — a 15 s base video gives the most realistic result.</p>

      <div className="form-card">
        <label>Name</label>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Glenn — office" />
        <label>Type</label>
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="base_video">Base video (~15 s, facing camera, neutral idle motion)</option>
          <option value="still_portrait">Photo avatar (single portrait image)</option>
        </select>
        <label>Media file</label>
        <input ref={fileRef} type="file" accept={kind === "base_video" ? "video/mp4" : "image/*"} />
        <div className="row" style={{ marginTop: 16 }}>
          <button onClick={submit} disabled={busy}>{busy ? "Uploading…" : "Create avatar"}</button>
        </div>
        {msg && <div className="notice">{msg}</div>}
      </div>

      <h2>Your avatars</h2>
      <div className="asset-list">
        {avatars.map((a) => (
          <div key={a.avatar_id} className="asset">
            <div className="badge">{a.name.slice(0, 1).toUpperCase()}</div>
            <div>
              <b>{a.name}</b>
              <small>{a.kind === "base_video" ? "video twin" : "photo avatar"} · {a.avatar_id}</small>
            </div>
          </div>
        ))}
        {avatars.length === 0 && <div className="empty">No avatars yet.</div>}
      </div>
    </Shell>
  );
}
