const OVERLAY_ROOT_ID = "__capcapocr_overlay_root__";
const OVERLAY_READER_ID = "__capcapocr_overlay_reader__";
const STORAGE_KEY = "capcapocr_test_settings";
const WIDGET_ID = "__capcapocr_quick_actions__";
const STYLE_ID = "__capcapocr_quick_actions_style__";

let activeWidget = null;

if (!window.__capcapocrQuickActionsInjected) {
  window.__capcapocrQuickActionsInjected = true;
  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type === "capcapocr_set_widget_enabled") {
      setWidgetEnabled(Boolean(message.enabled))
        .then(() => sendResponse({ ok: true }))
        .catch((error) => sendResponse({ ok: false, error: error.message || "Failed to update widget." }));
      return true;
    }
    return false;
  });

  initCapCapOCRQuickActions().catch((error) => {
    console.error("CapCapOCR quick actions failed to initialize", error);
  });
}

async function initCapCapOCRQuickActions() {
  injectStyles();
  const settings = await loadSettings();
  if (settings.widgetEnabled === false) {
    removeOverlay();
    return;
  }
  ensureWidget();
}

function ensureWidget() {
  if (activeWidget?.root && document.getElementById(WIDGET_ID)) {
    return activeWidget;
  }

  const widget = buildWidget();
  activeWidget = widget;
  document.documentElement.appendChild(widget.root);

  widget.runButton.addEventListener("click", async () => {
    await runPipeline(widget);
  });

  widget.clearButton.addEventListener("click", () => {
    removeOverlay();
    setStatus(widget.status, "Overlay removed.", "success");
  });

  return widget;
}

function destroyWidget() {
  activeWidget?.root?.remove();
  activeWidget = null;
}

async function setWidgetEnabled(enabled) {
  if (enabled) {
    ensureWidget();
    return;
  }
  destroyWidget();
  removeOverlay();
}

function injectStyles() {
  if (document.getElementById(STYLE_ID)) {
    return;
  }

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    #${WIDGET_ID} {
      position: fixed;
      right: 16px;
      bottom: 16px;
      z-index: 2147483647;
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px;
      border-radius: 999px;
      background: rgba(255, 250, 244, 0.96);
      border: 1px solid rgba(130, 98, 74, 0.24);
      box-shadow: 0 16px 40px rgba(0, 0, 0, 0.22);
      backdrop-filter: blur(14px);
      font: 13px/1.4 "Segoe UI", sans-serif;
      color: #2b211d;
    }
    #${WIDGET_ID} * { box-sizing: border-box; }
    .capcap-button {
      border: 0;
      border-radius: 999px;
      padding: 10px 14px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }
    .capcap-button.run {
      background: linear-gradient(135deg, #28503e, #3b6b56);
      color: #fff;
      min-width: 92px;
    }
    .capcap-button.clear {
      background: #efe4d6;
      color: #4b3427;
    }
    .capcap-button:disabled {
      cursor: wait;
      opacity: 0.72;
    }
    .capcap-status {
      max-width: 220px;
      font-size: 12px;
      color: #6d5343;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .capcap-status.error { color: #a63c2d; }
    .capcap-status.success { color: #2f6b40; }
    .capcap-status.loading { color: #6f4d1f; }
  `;
  document.documentElement.appendChild(style);
}

function buildWidget() {
  const root = document.createElement("div");
  root.id = WIDGET_ID;
  root.innerHTML = `
    <button class="capcap-button run" type="button">Execute</button>
    <button class="capcap-button clear" type="button">Remove Overlay</button>
    <div class="capcap-status">Ready.</div>
  `;
  return {
    root,
    runButton: root.querySelector(".capcap-button.run"),
    clearButton: root.querySelector(".capcap-button.clear"),
    status: root.querySelector(".capcap-status"),
  };
}

function defaultSettings() {
  return {
    apiUrl: "http://127.0.0.1:8000/api/ocr/base64",
    phase2Url: "http://127.0.0.1:8000/api/phase2",
    sourceLang: "ja",
    ocrEngine: "gguf",
    detectionEngine: "text",
    targetLang: "en",
    translatorEngine: "local",
    translateEnabled: true,
    overlayEnabled: true,
    widgetEnabled: true,
  };
}

async function loadSettings() {
  const stored = await chrome.storage.local.get(STORAGE_KEY);
  return { ...defaultSettings(), ...(stored[STORAGE_KEY] || {}) };
}

function setStatus(node, message, kind = "idle") {
  node.textContent = message;
  node.className = `capcap-status ${kind}`;
}

function scanCandidates() {
  const nextId = (() => {
    let counter = 1;
    return () => `capcapocr-${counter++}`;
  })();

  const getCandidateId = (element) => {
    if (!element.dataset.capcapocrId) {
      element.dataset.capcapocrId = nextId();
    }
    return element.dataset.capcapocrId;
  };

  const parseBackgroundUrl = (backgroundImage) => {
    const match = backgroundImage.match(/url\((['"]?)(.*?)\1\)/i);
    return match ? match[2] : "";
  };

  const toCandidate = (element, kind, src) => {
    const rect = element.getBoundingClientRect();
    const width = Math.round(rect.width);
    const height = Math.round(rect.height);
    if (width < 120 || height < 120) {
      return null;
    }

    const computed = window.getComputedStyle(element);
    if (computed.display === "none" || computed.visibility === "hidden" || computed.opacity === "0") {
      return null;
    }

    const visibleWidth = Math.max(0, Math.min(rect.right, window.innerWidth) - Math.max(rect.left, 0));
    const visibleHeight = Math.max(0, Math.min(rect.bottom, window.innerHeight) - Math.max(rect.top, 0));
    const visibleArea = visibleWidth * visibleHeight;
    const area = width * height;
    if (!area || visibleArea / area < 0.15) {
      return null;
    }

    return { id: getCandidateId(element), kind, src: src || "", width, height, area, visibleArea };
  };

  const candidates = [];
  for (const image of document.images) {
    const candidate = toCandidate(image, "img", image.currentSrc || image.src || "");
    if (candidate) candidates.push(candidate);
  }
  for (const canvas of document.querySelectorAll("canvas")) {
    const candidate = toCandidate(canvas, "canvas", "");
    if (candidate) candidates.push(candidate);
  }
  for (const element of document.querySelectorAll("div, section, article, figure, a")) {
    const backgroundImage = window.getComputedStyle(element).backgroundImage || "";
    if (!backgroundImage || backgroundImage === "none") continue;
    const candidate = toCandidate(element, "background", parseBackgroundUrl(backgroundImage));
    if (candidate) candidates.push(candidate);
  }

  candidates.sort((a, b) => b.visibleArea - a.visibleArea || b.area - a.area);
  return candidates.slice(0, 20);
}

function removeOverlay() {
  document.getElementById(OVERLAY_ROOT_ID)?.remove();
  document.getElementById(OVERLAY_READER_ID)?.remove();
}

function showOverlayReader(text) {
  let reader = document.getElementById(OVERLAY_READER_ID);
  if (!reader) {
    reader = document.createElement("div");
    reader.id = OVERLAY_READER_ID;
    reader.style.position = "fixed";
    reader.style.left = "50%";
    reader.style.bottom = "88px";
    reader.style.transform = "translateX(-50%)";
    reader.style.width = "min(680px, calc(100vw - 32px))";
    reader.style.maxHeight = "38vh";
    reader.style.padding = "14px 16px";
    reader.style.borderRadius = "18px";
    reader.style.background = "rgba(255, 251, 245, 0.98)";
    reader.style.border = "1px solid rgba(130, 98, 74, 0.24)";
    reader.style.boxShadow = "0 16px 40px rgba(0, 0, 0, 0.22)";
    reader.style.backdropFilter = "blur(14px)";
    reader.style.color = "#2b211d";
    reader.style.font = "600 15px/1.5 'Segoe UI', sans-serif";
    reader.style.whiteSpace = "pre-wrap";
    reader.style.wordBreak = "break-word";
    reader.style.overflow = "auto";
    reader.style.zIndex = "2147483647";
    reader.style.cursor = "pointer";
    reader.title = "Click to close";
    reader.addEventListener("click", () => {
      reader.remove();
    });
    document.documentElement.appendChild(reader);
  }
  reader.textContent = text;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function loadImage(dataUrl) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Failed to decode image data."));
    image.src = dataUrl;
  });
}

function blobToDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("Failed to encode image blob."));
    reader.readAsDataURL(blob);
  });
}

async function fetchImageAsDataUrl(src) {
  const response = await fetch(src);
  if (!response.ok) {
    throw new Error(`Image fetch failed with status ${response.status}.`);
  }
  const blob = await response.blob();
  return blobToDataUrl(blob);
}

async function captureVisibleTab() {
  const response = await chrome.runtime.sendMessage({ type: "capcapocr_capture_visible_tab" });
  if (!response?.ok) {
    throw new Error(response?.error || "Tab capture failed.");
  }
  return response.dataUrl;
}

async function cropVisibleTab(captureDataUrl, rect, viewport) {
  const image = await loadImage(captureDataUrl);
  const scaleX = image.width / viewport.width;
  const scaleY = image.height / viewport.height;
  const cropX = Math.max(0, Math.round(rect.left * scaleX));
  const cropY = Math.max(0, Math.round(rect.top * scaleY));
  const cropWidth = Math.max(1, Math.round(rect.width * scaleX));
  const cropHeight = Math.max(1, Math.round(rect.height * scaleY));
  const canvas = document.createElement("canvas");
  canvas.width = cropWidth;
  canvas.height = cropHeight;
  const context = canvas.getContext("2d");
  context.drawImage(image, cropX, cropY, cropWidth, cropHeight, 0, 0, cropWidth, cropHeight);
  return canvas.toDataURL("image/png");
}

async function getSelectedImageData(candidate) {
  const element = document.querySelector(`[data-capcapocr-id="${candidate.id}"]`);
  if (!element) {
    throw new Error("Selected image element was not found.");
  }

  element.scrollIntoView({ behavior: "auto", block: "center", inline: "center" });
  const rect = element.getBoundingClientRect();
  const src = element.tagName === "IMG"
    ? element.currentSrc || element.src || ""
    : (() => {
        const backgroundImage = window.getComputedStyle(element).backgroundImage || "";
        const match = backgroundImage.match(/url\((['"]?)(.*?)\1\)/i);
        return match ? match[2] : "";
      })();

  await delay(150);

  if (src && !src.startsWith("blob:")) {
    try {
      return { imageBase64: await fetchImageAsDataUrl(src), candidateId: candidate.id };
    } catch {}
  }

  const screenshot = await captureVisibleTab();
  return {
    imageBase64: await cropVisibleTab(screenshot, { left: rect.left, top: rect.top, width: rect.width, height: rect.height }, { width: window.innerWidth, height: window.innerHeight }),
    candidateId: candidate.id,
  };
}

async function requestJson(url, body, errorPrefix) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `${errorPrefix} failed.`);
  }
  return payload;
}

function renderOverlay(payload, selectedId) {
  const polygonBounds = (polygon) => {
    if (!polygon || polygon.length < 3) {
      return null;
    }
    const xs = polygon.map((point) => point[0]);
    const ys = polygon.map((point) => point[1]);
    return {
      x: Math.min(...xs),
      y: Math.min(...ys),
      width: Math.max(...xs) - Math.min(...xs),
      height: Math.max(...ys) - Math.min(...ys),
    };
  };

  const polygonClipPath = (polygon, bounds, inset) => {
    if (!polygon || polygon.length < 3 || !bounds) {
      return "";
    }
    const centerX = bounds.x + bounds.width / 2;
    const centerY = bounds.y + bounds.height / 2;
    const adjusted = polygon.map(([x, y]) => {
      const dx = x - centerX;
      const dy = y - centerY;
      const length = Math.hypot(dx, dy) || 1;
      const nextLength = Math.max(length - inset, 1);
      const nextX = centerX + (dx / length) * nextLength;
      const nextY = centerY + (dy / length) * nextLength;
      const px = ((nextX - bounds.x) / Math.max(bounds.width, 1)) * 100;
      const py = ((nextY - bounds.y) / Math.max(bounds.height, 1)) * 100;
      return `${px}% ${py}%`;
    });
    return `polygon(${adjusted.join(", ")})`;
  };

  const fitTextToBubble = (container, textNode, boxWidth, boxHeight) => {
    const minFontSize = 9;
    const maxFontSize = Math.max(
      minFontSize,
      Math.min(28, Math.floor(Math.min(boxWidth / 4.8, boxHeight / 1.95)))
    );
    let low = minFontSize;
    let high = maxFontSize;
    let best = minFontSize;

    while (low <= high) {
      const mid = Math.floor((low + high) / 2);
      textNode.style.fontSize = `${mid}px`;
      textNode.style.lineHeight = "1.16";
      if (textNode.scrollWidth <= container.clientWidth && textNode.scrollHeight <= container.clientHeight) {
        best = mid;
        low = mid + 1;
      } else {
        high = mid - 1;
      }
    }

    textNode.style.fontSize = `${best}px`;
    textNode.style.lineHeight = "1.16";
  };

  removeOverlay();
  const host = document.querySelector(`[data-capcapocr-id="${selectedId}"]`);
  if (!host) {
    throw new Error("Selected image element was not found for overlay.");
  }

  const rect = host.getBoundingClientRect();
  const root = document.createElement("div");
  root.id = OVERLAY_ROOT_ID;
  root.style.position = "absolute";
  root.style.left = `${Math.round(rect.left + window.scrollX)}px`;
  root.style.top = `${Math.round(rect.top + window.scrollY)}px`;
  root.style.width = `${Math.round(rect.width)}px`;
  root.style.height = `${Math.round(rect.height)}px`;
  root.style.zIndex = "2147483646";
  root.style.pointerEvents = "none";
  root.style.overflow = "hidden";

  const imageWidth = payload?.image?.width || rect.width || 1;
  const imageHeight = payload?.image?.height || rect.height || 1;
  const scaleX = rect.width / imageWidth;
  const scaleY = rect.height / imageHeight;

  for (const group of payload?.groups || []) {
    const text = (group.translated_text || group.corrected_text || group.source_text || "").trim();
    if (!text) continue;

    const bubble = document.createElement("div");
    const maskBounds = polygonBounds(group.mask);
    const rawX = maskBounds ? Math.round(maskBounds.x * scaleX) : Math.round((group.x || 0) * scaleX);
    const rawY = maskBounds ? Math.round(maskBounds.y * scaleY) : Math.round((group.y || 0) * scaleY);
    const rawWidth = Math.max(24, maskBounds ? Math.round(maskBounds.width * scaleX) : Math.round((group.width || 0) * scaleX));
    const rawHeight = Math.max(24, maskBounds ? Math.round(maskBounds.height * scaleY) : Math.round((group.height || 0) * scaleY));
    const inset = Math.max(2, Math.floor(Math.min(rawWidth, rawHeight) * 0.045));
    const boxWidth = Math.max(20, rawWidth - inset * 2);
    const boxHeight = Math.max(20, rawHeight - inset * 2);
    const padding = Math.max(4, Math.floor(Math.min(boxWidth, boxHeight) * 0.09));
    bubble.style.position = "absolute";
    bubble.style.left = `${rawX + inset}px`;
    bubble.style.top = `${rawY + inset}px`;
    bubble.style.width = `${boxWidth}px`;
    bubble.style.height = `${boxHeight}px`;
    bubble.style.display = "flex";
    bubble.style.alignItems = "center";
    bubble.style.justifyContent = "center";
    bubble.style.textAlign = "center";
    bubble.style.padding = `${padding}px`;
    bubble.style.background = "rgba(255, 255, 255, 0.98)";
    bubble.style.overflow = "hidden";
    bubble.style.borderRadius = `${Math.max(6, Math.floor(Math.min(boxWidth, boxHeight) * 0.22))}px`;
    bubble.style.pointerEvents = "auto";
    bubble.style.cursor = "pointer";
    if (maskBounds) {
      bubble.style.clipPath = polygonClipPath(
        group.mask.map(([x, y]) => [x * scaleX, y * scaleY]),
        { x: rawX, y: rawY, width: rawWidth, height: rawHeight },
        inset
      );
      bubble.style.borderRadius = "0";
    }

    const textNode = document.createElement("div");
    textNode.textContent = text;
    textNode.style.color = "#111111";
    textNode.style.fontFamily = "'Segoe UI', sans-serif";
    textNode.style.fontWeight = "700";
    textNode.style.lineHeight = "1.16";
    textNode.style.whiteSpace = "pre-wrap";
    textNode.style.overflowWrap = "break-word";
    textNode.style.wordBreak = "break-word";
    textNode.style.maxWidth = "100%";
    textNode.style.maxHeight = "100%";
    textNode.style.overflow = "hidden";
    textNode.style.textShadow = "0 0 2px rgba(255,255,255,0.95), 0 0 6px rgba(255,255,255,0.95), 0 1px 0 rgba(255,255,255,0.95)";

    bubble.appendChild(textNode);
    fitTextToBubble(bubble, textNode, boxWidth - padding * 2, boxHeight - padding * 2);
    bubble.title = text;
    bubble.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      showOverlayReader(text);
    });
    bubble.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      event.stopPropagation();
    });
    root.appendChild(bubble);
  }

  document.body.appendChild(root);
}

async function runPipeline(widget) {
  const settings = await loadSettings();
  const candidates = scanCandidates();
  const candidate = candidates[0];

  if (!candidate) {
    setStatus(widget.status, "No visible image candidate found.", "error");
    return;
  }

  if (!settings.apiUrl) {
    setStatus(widget.status, "OCR endpoint is missing.", "error");
    return;
  }

  widget.runButton.disabled = true;
  widget.clearButton.disabled = true;

  try {
    setStatus(widget.status, `Running on ${candidate.kind} ${candidate.width}x${candidate.height}...`, "loading");
    const selectedImage = await getSelectedImageData(candidate);

    const ocrPayload = await requestJson(
      settings.apiUrl,
      {
        image_base64: selectedImage.imageBase64,
        source_lang: settings.sourceLang,
        ocr_engine: settings.ocrEngine,
        detection_engine: settings.detectionEngine,
      },
      "OCR request"
    );

    if (!settings.translateEnabled) {
      removeOverlay();
      setStatus(widget.status, `Detected ${ocrPayload.blocks?.length || 0} text block(s).`, "success");
      return;
    }

    if (!settings.phase2Url) {
      throw new Error("Phase 2 endpoint is missing while translation is enabled.");
    }

    const phase2Payload = await requestJson(
      settings.phase2Url,
      {
        image: ocrPayload.image,
        blocks: ocrPayload.blocks || [],
        source_lang: settings.sourceLang,
        ocr_engine: settings.ocrEngine,
        detection_engine: settings.detectionEngine,
        translator_engine: settings.translatorEngine,
        target_lang: settings.targetLang,
        translate: true,
      },
      "Phase 2 request"
    );

    if (!settings.overlayEnabled) {
      removeOverlay();
      setStatus(widget.status, `Translated ${phase2Payload.groups?.length || 0} group(s).`, "success");
      return;
    }

    renderOverlay(phase2Payload, selectedImage.candidateId);
    setStatus(widget.status, `Overlayed ${phase2Payload.groups?.length || 0} bubble(s).`, "success");
  } catch (error) {
    setStatus(widget.status, error.message || "Pipeline run failed.", "error");
  } finally {
    widget.runButton.disabled = false;
    widget.clearButton.disabled = false;
  }
}
