"""Dynamic alpha masking around the jaw/mouth region.

MuseTalk (and Wav2Lip-class models) regenerate a rectangular lower-face crop.
Pasting that crop back verbatim causes the classic "floating jaw" seam:
lighting mismatch, lost skin texture, clothing/collar corruption.

Fix: per-frame landmark-tracked polygon mask, feathered, plus LAB color
transfer so the generated pixels inherit the ORIGINAL frame's lighting.

Per frame:
  1. mediapipe FaceMesh → jaw contour + nose-base landmarks
  2. convex hull polygon over the mouth/jaw region only
  3. dilate (mask_dilate_px) then Gaussian-feather (mask_feather_px) → soft α
  4. LAB mean/std transfer inside the mask: generated → original statistics
  5. composite: out = α·generated + (1-α)·original
Clothing, hair, background, and 80 % of the face are untouched originals.
"""
from __future__ import annotations

import cv2
import mediapipe as mp
import numpy as np

# FaceMesh indices: jawline sweep + upper-lip/nose-base closure
_JAW_IDX = [93, 132, 58, 172, 136, 150, 149, 176, 148, 152,
            377, 400, 378, 379, 365, 397, 288, 361, 323]
_TOP_IDX = [2, 97, 164, 326]   # under-nose closure line

_face_mesh = mp.solutions.face_mesh.FaceMesh(
    static_image_mode=False, max_num_faces=1, refine_landmarks=True,
    min_detection_confidence=0.5, min_tracking_confidence=0.5,
)


def mouth_region_alpha(
    frame: np.ndarray, dilate_px: int = 12, feather_px: int = 21
) -> np.ndarray | None:
    """float32 HxW alpha in [0,1], or None if no face found this frame."""
    h, w = frame.shape[:2]
    res = _face_mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    if not res.multi_face_landmarks:
        return None

    lm = res.multi_face_landmarks[0].landmark
    pts = np.array(
        [(int(lm[i].x * w), int(lm[i].y * h)) for i in _JAW_IDX + _TOP_IDX],
        dtype=np.int32,
    )
    mask = np.zeros((h, w), np.uint8)
    cv2.fillConvexPoly(mask, cv2.convexHull(pts), 255)

    if dilate_px > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate_px * 2 + 1,) * 2)
        mask = cv2.dilate(mask, k)

    feather = feather_px | 1            # gaussian kernel must be odd
    alpha = cv2.GaussianBlur(mask, (feather, feather), 0).astype(np.float32) / 255.0
    return alpha


def lab_color_transfer(
    generated: np.ndarray, original: np.ndarray, alpha: np.ndarray
) -> np.ndarray:
    """Match generated pixels to the original frame's lighting inside the mask."""
    region = alpha > 0.05
    if not region.any():
        return generated

    gen_lab = cv2.cvtColor(generated, cv2.COLOR_BGR2LAB).astype(np.float32)
    org_lab = cv2.cvtColor(original, cv2.COLOR_BGR2LAB).astype(np.float32)

    for c in range(3):
        g, o = gen_lab[..., c][region], org_lab[..., c][region]
        g_std = g.std() + 1e-6
        gen_lab[..., c][region] = (g - g.mean()) / g_std * o.std() + o.mean()

    return cv2.cvtColor(np.clip(gen_lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


def composite(
    original: np.ndarray,
    generated: np.ndarray,
    dilate_px: int = 12,
    feather_px: int = 21,
    color_transfer: bool = True,
) -> np.ndarray:
    """Blend the generated mouth region into the original frame."""
    alpha = mouth_region_alpha(original, dilate_px, feather_px)
    if alpha is None:                   # face lost this frame → keep original
        return original
    if color_transfer:
        generated = lab_color_transfer(generated, original, alpha)
    a = alpha[..., None]
    return (a * generated.astype(np.float32)
            + (1.0 - a) * original.astype(np.float32)).astype(np.uint8)
