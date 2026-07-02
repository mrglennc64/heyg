"use client";
import { useCallback, useRef } from "react";
import type { Scene } from "@/lib/types";

/**
 * 16:9 stage with a drag-to-position avatar proxy box.
 * Position is stored normalized (0..1 center coords) — exactly what the
 * compositor's overlay expression consumes, so WYSIWYG holds at any res.
 */
export default function CanvasStage({
  scene,
  onPosition,
}: {
  scene: Scene;
  onPosition: (x: number, y: number) => void;
}) {
  const stageRef = useRef<HTMLDivElement>(null);

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      const stage = stageRef.current;
      if (!stage) return;
      (e.target as HTMLElement).setPointerCapture(e.pointerId);

      const move = (ev: PointerEvent) => {
        const r = stage.getBoundingClientRect();
        const x = Math.min(1, Math.max(0, (ev.clientX - r.left) / r.width));
        const y = Math.min(1, Math.max(0, (ev.clientY - r.top) / r.height));
        onPosition(Number(x.toFixed(4)), Number(y.toFixed(4)));
      };
      const up = () => {
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    },
    [onPosition],
  );

  const bg = scene.background;
  const stageStyle =
    bg.type === "color"
      ? { background: bg.value }
      : { backgroundImage: `url(${bg.value})` };

  // avatar proxy height as % of stage height, mirroring compositor scaling
  const heightPct = scene.avatar.scale * 62;

  return (
    <div className="stage" ref={stageRef} style={stageStyle}>
      <div
        className="avatar-box"
        onPointerDown={handlePointerDown}
        style={{
          left: `${scene.avatar.position.x * 100}%`,
          top: `${scene.avatar.position.y * 100}%`,
          height: `${heightPct}%`,
        }}
      >
        {scene.avatar.avatar_id ? `avatar ${scene.avatar.avatar_id.slice(0, 6)}…` : "avatar"}
      </div>
    </div>
  );
}
