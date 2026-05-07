from __future__ import annotations

import base64
from html import escape
import mimetypes
from pathlib import Path
import re

import streamlit as st


def resolve_photo_path(photo_value: object, *, project_root: Path) -> Path | None:
    if photo_value is None:
        return None

    photo_text = str(photo_value).strip().strip('"')
    if not photo_text:
        return None

    photo_path = Path(photo_text).expanduser()
    if photo_path.is_file():
        return photo_path

    if not photo_path.is_absolute():
        project_relative_path = (project_root / photo_path).resolve()
        if project_relative_path.is_file():
            return project_relative_path

    return None


def build_photo_data_uri(photo_path: Path | None) -> str | None:
    if photo_path is None or not photo_path.is_file():
        return None

    mime_type, _ = mimetypes.guess_type(photo_path.name)
    if not mime_type or not mime_type.startswith("image/"):
        mime_type = "image/jpeg"

    encoded = base64.b64encode(photo_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _slugify_dom_id(value: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", value.casefold()).strip("-") or "photo"


def _build_clickable_photo_html(
    photo_data_uri: str,
    caption: str,
    *,
    element_key: str,
    aria_label: str,
    preview_width: int,
    preview_height: int,
) -> str:
    safe_src = escape(photo_data_uri, quote=True)
    safe_caption = escape(caption)
    safe_aria_label = escape(aria_label)
    safe_key = _slugify_dom_id(element_key)
    root_id = f"device-photo-root-{safe_key}"
    thumb_id = f"device-photo-thumb-{safe_key}"
    overlay_id = f"device-photo-overlay-{safe_key}"
    viewer_id = f"device-photo-viewer-{safe_key}"
    image_id = f"device-photo-image-{safe_key}"
    zoom_out_id = f"device-photo-zoom-out-{safe_key}"
    zoom_in_id = f"device-photo-zoom-in-{safe_key}"
    reset_id = f"device-photo-reset-{safe_key}"
    close_id = f"device-photo-close-{safe_key}"
    return f"""
    <style>
      #{root_id} {{
        width: 100%;
        min-height: {preview_height}px;
        display: flex;
        align-items: flex-end;
        justify-content: center;
      }}
      #{thumb_id} {{
        display: flex;
        align-items: flex-end;
        justify-content: center;
        width: {preview_width}px;
        cursor: zoom-in;
        user-select: none;
      }}
      #{thumb_id} .preview-frame {{
        width: {preview_width}px;
        height: {preview_height}px;
        overflow: hidden;
        border-radius: 10px;
        border: 1px solid #d1d5db;
        background: #0f172a;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.12);
      }}
      #{thumb_id} img {{
        display: block;
        width: 100%;
        height: 100%;
        object-fit: cover;
        object-position: center center;
      }}
      #{overlay_id} {{
        position: fixed;
        inset: 0;
        display: none;
        align-items: center;
        justify-content: center;
        background: rgba(15, 23, 42, 0.82);
        z-index: 999999;
        padding: 2rem;
        box-sizing: border-box;
      }}
      #{overlay_id}.open {{
        display: flex;
      }}
      #{overlay_id} .panel {{
        width: min(1200px, 92vw);
        background: #ffffff;
        border-radius: 14px;
        box-shadow: 0 20px 50px rgba(15, 23, 42, 0.35);
        padding: 1rem;
        box-sizing: border-box;
        font-family: "Segoe UI", Arial, sans-serif;
      }}
      #{overlay_id} .toolbar {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 0.75rem;
        margin-bottom: 0.75rem;
      }}
      #{overlay_id} .toolbar-group {{
        display: flex;
        gap: 0.5rem;
      }}
      #{overlay_id} .toolbar button {{
        border: 1px solid #d1d5db;
        background: #ffffff;
        border-radius: 6px;
        min-width: 40px;
        height: 40px;
        font-size: 1rem;
        cursor: pointer;
      }}
      #{overlay_id} .caption {{
        font-size: 0.95rem;
        color: #4b5563;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }}
      #{viewer_id} {{
        position: relative;
        width: 100%;
        height: min(72vh, 780px);
        overflow: hidden;
        border: 1px solid #d1d5db;
        border-radius: 10px;
        background: #111827;
        touch-action: none;
        cursor: grab;
      }}
      #{viewer_id}.dragging {{
        cursor: grabbing;
      }}
      #{viewer_id} img {{
        position: absolute;
        top: 50%;
        left: 50%;
        transform-origin: center center;
        user-select: none;
        -webkit-user-drag: none;
        max-width: none;
        max-height: none;
      }}
    </style>
    <div id="{root_id}">
      <div id="{thumb_id}" role="button" tabindex="0" aria-label="{safe_aria_label}">
        <div class="preview-frame">
          <img src="{safe_src}" alt="{safe_caption}" />
        </div>
      </div>
    </div>
    <div id="{overlay_id}" aria-hidden="true">
      <div class="panel">
        <div class="toolbar">
          <div class="toolbar-group">
            <button id="{zoom_out_id}" type="button" aria-label="Oddálit">−</button>
            <button id="{zoom_in_id}" type="button" aria-label="Přiblížit">+</button>
            <button id="{reset_id}" type="button" aria-label="Reset">Reset</button>
          </div>
          <div class="toolbar-group">
            <div class="caption">{safe_caption}</div>
            <button id="{close_id}" type="button" aria-label="Zavřít">×</button>
          </div>
        </div>
        <div id="{viewer_id}">
          <img id="{image_id}" src="{safe_src}" alt="{safe_caption}" />
        </div>
      </div>
    </div>
    <script>
          const thumb = document.getElementById("{thumb_id}");
          const overlay = document.getElementById("{overlay_id}");
          const viewer = document.getElementById("{viewer_id}");
          const img = document.getElementById("{image_id}");
          const zoomInButton = document.getElementById("{zoom_in_id}");
          const zoomOutButton = document.getElementById("{zoom_out_id}");
          const resetButton = document.getElementById("{reset_id}");
          const closeButton = document.getElementById("{close_id}");

          let baseScale = 1;
          let scale = 1;
          let translateX = 0;
          let translateY = 0;
          let dragging = false;
          let lastX = 0;
          let lastY = 0;

          function clamp(value, min, max) {{
            return Math.min(Math.max(value, min), max);
          }}

          function applyTransform() {{
            img.style.transform =
              `translate(-50%, -50%) translate(${{translateX}}px, ${{translateY}}px) scale(${{scale}})`;
          }}

          function fitImage() {{
            const viewerRect = viewer.getBoundingClientRect();
            if (!img.naturalWidth || !img.naturalHeight || !viewerRect.width || !viewerRect.height) {{
              return;
            }}
            baseScale = Math.min(
              viewerRect.width / img.naturalWidth,
              viewerRect.height / img.naturalHeight,
              1
            );
            scale = baseScale;
            translateX = 0;
            translateY = 0;
            applyTransform();
          }}

          function openOverlay() {{
            overlay.classList.add("open");
            overlay.setAttribute("aria-hidden", "false");
            document.body.style.overflow = "hidden";
            fitImage();
          }}

          function closeOverlay() {{
            overlay.classList.remove("open");
            overlay.setAttribute("aria-hidden", "true");
            document.body.style.overflow = "";
            dragging = false;
            viewer.classList.remove("dragging");
          }}

          function zoom(step) {{
            const minScale = Math.max(baseScale * 0.75, 0.1);
            const maxScale = Math.max(baseScale, 1) * 8;
            scale = clamp(scale * step, minScale, maxScale);
            applyTransform();
          }}

          img.addEventListener("load", fitImage);
          window.addEventListener("resize", fitImage);
          thumb.addEventListener("click", openOverlay);
          thumb.addEventListener("keydown", (event) => {{
            if (event.key === "Enter" || event.key === " ") {{
              event.preventDefault();
              openOverlay();
            }}
          }});
          closeButton.addEventListener("click", closeOverlay);
          overlay.addEventListener("click", (event) => {{
            if (event.target === overlay) {{
              closeOverlay();
            }}
          }});
          document.addEventListener("keydown", (event) => {{
            if (event.key === "Escape" && overlay.classList.contains("open")) {{
              closeOverlay();
            }}
          }});

          viewer.addEventListener("wheel", (event) => {{
            event.preventDefault();
            zoom(event.deltaY < 0 ? 1.12 : 1 / 1.12);
          }}, {{ passive: false }});

          viewer.addEventListener("pointerdown", (event) => {{
            dragging = true;
            lastX = event.clientX;
            lastY = event.clientY;
            viewer.classList.add("dragging");
            viewer.setPointerCapture(event.pointerId);
          }});

          viewer.addEventListener("pointermove", (event) => {{
            if (!dragging) {{
              return;
            }}
            translateX += event.clientX - lastX;
            translateY += event.clientY - lastY;
            lastX = event.clientX;
            lastY = event.clientY;
            applyTransform();
          }});

          function stopDragging(event) {{
            dragging = false;
            viewer.classList.remove("dragging");
            if (event) {{
              viewer.releasePointerCapture(event.pointerId);
            }}
          }}

          viewer.addEventListener("pointerup", stopDragging);
          viewer.addEventListener("pointercancel", stopDragging);
          viewer.addEventListener("pointerleave", (event) => {{
            if (dragging && event.buttons === 0) {{
              stopDragging(event);
            }}
          }});

          zoomInButton.addEventListener("click", () => zoom(1.2));
          zoomOutButton.addEventListener("click", () => zoom(1 / 1.2));
          resetButton.addEventListener("click", fitImage);
    </script>
    """


def render_clickable_device_photo(
    device_detail: dict[str, object] | None,
    *,
    project_root: Path,
    aria_label: str,
    ident_key: str = "identifikace",
    photo_key: str = "foto",
    preview_width: int = 300,
    preview_height: int = 128,
) -> bool:
    if device_detail is None:
        return False

    photo_path = resolve_photo_path(device_detail.get(photo_key), project_root=project_root)
    if photo_path is None:
        return False

    photo_data_uri = build_photo_data_uri(photo_path)
    if photo_data_uri is None:
        return False

    element_key = str(device_detail.get(ident_key, photo_path.name))
    st.html(
        _build_clickable_photo_html(
            photo_data_uri,
            photo_path.name,
            element_key=element_key,
            aria_label=aria_label,
            preview_width=preview_width,
            preview_height=preview_height,
        ),
        width="stretch",
        unsafe_allow_javascript=True,
    )
    return True
