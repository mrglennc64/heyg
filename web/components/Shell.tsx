"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getApiKey, setApiKey } from "@/lib/api";

const NAV = [
  { href: "/", icon: "🏠", label: "Home" },
  { href: "/projects", icon: "🎬", label: "Projects" },
  { href: "/avatars", icon: "👤", label: "Avatars" },
  { href: "/voices", icon: "🎙️", label: "Voices" },
];

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [key, setKey] = useState("");
  useEffect(() => setKey(getApiKey()), []);

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="logo">Avatar<span>Forge</span></div>
        {NAV.map((n) => (
          <Link key={n.href} href={n.href}
                className={`nav-item ${path === n.href ? "active" : ""}`}>
            <span className="icon">{n.icon}</span> {n.label}
          </Link>
        ))}
        <Link href="/editor" className="nav-item" style={{ marginTop: 10 }}>
          <span className="icon">＋</span> Create video
        </Link>
        <div className="spacer" />
        <div className="conn">
          <label>API key</label>
          <input type="password" value={key} placeholder="paste key…"
                 onChange={(e) => { setKey(e.target.value); setApiKey(e.target.value); }} />
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
