"use client";
import { useEffect, useRef, useState } from "react";
import Shell from "@/components/Shell";
import { listVoices, registerVoice, type VoiceInfo } from "@/lib/api";

export default function Voices() {
  const [voices, setVoices] = useState<VoiceInfo[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const sampleRef = useRef<HTMLInputElement>(null);
  const consentRef = useRef<HTMLInputElement>(null);

  const refresh = () => listVoices().then(setVoices).catch((e) => setMsg(String(e.message ?? e)));
  useEffect(() => { refresh(); }, []);

  const submit = async () => {
    const sample = sampleRef.current?.files?.[0];
    const consent = consentRef.current?.files?.[0];
    if (!name || !sample || !consent) { setMsg("Name, voice sample, and consent clip are all required."); return; }
    setBusy(true); setMsg(null);
    try {
      await registerVoice(name, sample, consent);
      setName("");
      if (sampleRef.current) sampleRef.current.value = "";
      if (consentRef.current) consentRef.current.value = "";
      setMsg("Voice cloned ✔ — it now speaks all 17 supported languages.");
      refresh();
    } catch (e) { setMsg(String((e as Error).message)); }
    finally { setBusy(false); }
  };

  return (
    <Shell>
      <h1>Voices</h1>
      <p className="sub">Clone a voice from a 30 s – 3 min sample. A recorded consent clip is mandatory.</p>

      <div className="form-card">
        <label>Name</label>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Glenn" />
        <label>Voice sample (30 s – 3 min clean speech, wav/flac)</label>
        <input ref={sampleRef} type="file" accept="audio/*" />
        <label>Consent clip — the speaker saying: “I consent to my voice being cloned for video generation on this system.”</label>
        <input ref={consentRef} type="file" accept="audio/*" />
        <div className="row" style={{ marginTop: 16 }}>
          <button onClick={submit} disabled={busy}>{busy ? "Uploading…" : "Clone voice"}</button>
        </div>
        {msg && <div className="notice">{msg}</div>}
      </div>

      <h2>Your voices</h2>
      <div className="asset-list">
        {voices.map((v) => (
          <div key={v.voice_id} className="asset">
            <div className="badge">🎙️</div>
            <div>
              <b>{v.name}</b>
              <small>{v.voice_id}</small>
            </div>
          </div>
        ))}
        {voices.length === 0 && <div className="empty">No voices yet.</div>}
      </div>
    </Shell>
  );
}
