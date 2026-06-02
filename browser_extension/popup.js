const OVERLAY_ROOT_ID = "__capcapocr_overlay_root__";
const STORAGE_KEY = "capcapocr_test_settings";

const elements = {
  apiUrl: document.getElementById("apiUrl"),
  phase2Url: document.getElementById("phase2Url"),
  sourceLang: document.getElementById("sourceLang"),
  ocrEngine: document.getElementById("ocrEngine"),
  detectionEngine: document.getElementById("detectionEngine"),
  targetLang: document.getElementById("targetLang"),
  translatorEngine: document.getElementById("translatorEngine"),
  translateEnabled: document.getElementById("translateEnabled"),
  overlayEnabled: document.getElementById("overlayEnabled"),
  widgetEnabled: document.getElementById("widgetEnabled"),
  imageCandidate: document.getElementById("imageCandidate"),
  refreshImagesButton: document.getElementById("refreshImagesButton"),
  runButton: document.getElementById("runButton"),
  clearButton: document.getElementById("clearButton"),
  status: document.getElementById("status"),
  statusBadge: document.getElementById("statusBadge"),
  settingsToggle: document.getElementById("settingsToggle"),
  settingsBody: document.getElementById("settingsBody"),
  detailsToggle: document.getElementById("detailsToggle"),
  detailsBody: document.getElementById("detailsBody"),
  joinedText: document.getElementById("joinedText"),
  overlayText: document.getElementById("overlayText"),
  rawJson: document.getElementById("rawJson"),
};

const defaultUiState = {
  settingsCollapsed: false,
  detailsCollapsed: true,
};

let currentCandidates = [];
let uiState = { ...defaultUiState };

function setStatus(message, kind = "idle") {
  elements.status.textContent = message;
  elements.status.className = `status ${kind}`;
  elements.statusBadge.textContent = kind === "idle" ? "Ready" : kind === "loading" ? "Working" : kind === "success" ? "OK" : "Error";
  elements.statusBadge.className = `status-badge ${kind}`;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function applySectionState() {
  setSectionCollapsed("settings", uiState.settingsCollapsed);
  setSectionCollapsed("details", uiState.detailsCollapsed);
}

function setSectionCollapsed(section, collapsed) {
  const body = section === "settings" ? elements.settingsBody : elements.detailsBody;
  const toggle = section === "settings" ? elements.settingsToggle : elements.detailsToggle;
  body.classList.toggle("is-collapsed", collapsed);
  toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
  uiState[`${section}Collapsed`] = collapsed;
}

async function loadSettings() {
  const stored = await chrome.storage.local.get(STORAGE_KEY);
  const settings = stored[STORAGE_KEY];
  if (!settings) {
    applySectionState();
    return;
  }

  elements.apiUrl.value = settings.apiUrl || elements.apiUrl.value;
  elements.phase2Url.value = settings.phase2Url || elements.phase2Url.value;
  elements.sourceLang.value = settings.sourceLang || elements.sourceLang.value;
  elements.ocrEngine.value = settings.ocrEngine || elements.ocrEngine.value;
  elements.detectionEngine.value = settings.detectionEngine || elements.detectionEngine.value;
  elements.targetLang.value = settings.targetLang || elements.targetLang.value;
  elements.translatorEngine.value = settings.translatorEngine || elements.translatorEngine.value;
  elements.translateEnabled.checked = settings.translateEnabled ?? elements.translateEnabled.checked;
  elements.overlayEnabled.checked = settings.overlayEnabled ?? elements.overlayEnabled.checked;
  elements.widgetEnabled.checked = settings.widgetEnabled ?? elements.widgetEnabled.checked;
  uiState = {
    settingsCollapsed: settings.ui?.settingsCollapsed ?? defaultUiState.settingsCollapsed,
    detailsCollapsed: settings.ui?.detailsCollapsed ?? defaultUiState.detailsCollapsed,
  };
  applySectionState();
  syncPipelineOptions();
}

async function saveSettings() {
  await chrome.storage.local.set({
    [STORAGE_KEY]: {
      apiUrl: elements.apiUrl.value.trim(),
      phase2Url: elements.phase2Url.value.trim(),
      sourceLang: elements.sourceLang.value,
      ocrEngine: elements.ocrEngine.value,
      detectionEngine: elements.detectionEngine.value,
      targetLang: elements.targetLang.value,
      translatorEngine: elements.translatorEngine.value,
      translateEnabled: elements.translateEnabled.checked,
      overlayEnabled: elements.overlayEnabled.checked,
      widgetEnabled: elements.widgetEnabled.checked,
      ui: {
        settingsCollapsed: uiState.settingsCollapsed,
        detailsCollapsed: uiState.detailsCollapsed,
      },
    },
  });
}


async function persistSettingsSilently() {
  try {
    await saveSettings();
  } catch (error) {
    setStatus(error.message || "Failed to save settings.", "error");
  }
}

async function sendMessageToActiveTab(message) {
  const tab = await getActiveTab();
  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(tab.id, message, (response) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      resolve(response);
    });
  });
}

async function syncInjectedWidget() {
  try {
    await sendMessageToActiveTab({
      type: "capcapocr_set_widget_enabled",
      enabled: elements.widgetEnabled.checked,
    });
  } catch (error) {
    setStatus(error.message || "Failed to sync injected widget.", "error");
  }
}

function syncPipelineOptions() {
  const translateEnabled = elements.translateEnabled.checked;
  const overlayEnabled = elements.overlayEnabled.checked;

  elements.translatorEngine.disabled = !translateEnabled;
  elements.targetLang.disabled = !translateEnabled;

  if (overlayEnabled && !translateEnabled) {
    elements.translateEnabled.checked = true;
    elements.translatorEngine.disabled = false;
    elements.targetLang.disabled = false;
  }

  const effectiveTranslateEnabled = elements.translateEnabled.checked;
  const effectiveOverlayEnabled = elements.overlayEnabled.checked && effectiveTranslateEnabled;

  if (!effectiveTranslateEnabled) {
    elements.overlayEnabled.checked = false;
  }

  elements.runButton.textContent = effectiveOverlayEnabled
    ? "Detect, Translate, Overlay"
    : effectiveTranslateEnabled
      ? "Detect, Translate"
      : "Detect Only";
}

function syncEngineOptions() {
  const japaneseOnlyAllowed = elements.sourceLang.value === "ja";
  const ggufOption = elements.ocrEngine.querySelector('option[value="gguf"]');
  const hybridOption = elements.ocrEngine.querySelector('option[value="hybrid"]');
  if (ggufOption) {
    ggufOption.disabled = !japaneseOnlyAllowed;
  }
  if (hybridOption) {
    hybridOption.disabled = !japaneseOnlyAllowed;
  }
  if (!japaneseOnlyAllowed && ["gguf", "hybrid"].includes(elements.ocrEngine.value)) {
    elements.ocrEngine.value = "auto";
  }

  const bubbleOption = elements.detectionEngine.querySelector('option[value="bubble"]');
  const bubbleAllowed = japaneseOnlyAllowed && elements.ocrEngine.value !== "paddle";
  if (bubbleOption) {
    bubbleOption.disabled = !bubbleAllowed;
  }
  if (!bubbleAllowed && elements.detectionEngine.value === "bubble") {
    elements.detectionEngine.value = "text";
  }
}

function captureVisibleTab() {
  return new Promise((resolve, reject) => {
    chrome.tabs.captureVisibleTab(undefined, { format: "png" }, (dataUrl) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      if (!dataUrl) {
        reject(new Error("Tab capture returned no image data."));
        return;
      }
      resolve(dataUrl);
    });
  });
}

function getActiveTab() {
  return new Promise((resolve, reject) => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      if (!tabs.length || !tabs[0].id) {
        reject(new Error("No active tab found."));
        return;
      }
      resolve(tabs[0]);
    });
  });
}

function runInTab(tabId, func, args = []) {
  return new Promise((resolve, reject) => {
    chrome.scripting.executeScript(
      {
        target: { tabId },
        func,
        args,
      },
      (results) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
          return;
        }
        resolve(results?.[0]?.result);
      }
    );
  });
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

function joinBlockText(blocks) {
  return (blocks || [])
    .map((block) => (block.text || "").trim())
    .filter(Boolean)
    .join("\n");
}

function joinOverlayText(groups) {
  return (groups || [])
    .map((group) => (group.translated_text || group.corrected_text || group.source_text || "").trim())
    .filter(Boolean)
    .join("\n\n");
}

function imageSourceName(url) {
  try {
    if (url.startsWith("data:")) {
      return "data-url";
    }
    if (url.startsWith("blob:")) {
      return "blob-url";
    }
    return new URL(url).hostname;
  } catch {
    return "image";
  }
}

async function scanCandidates(tabId) {
  return runInTab(tabId, () => {
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
      if (
        computed.display === "none" ||
        computed.visibility === "hidden" ||
        computed.opacity === "0"
      ) {
        return null;
      }

      const visibleWidth = Math.max(
        0,
        Math.min(rect.right, window.innerWidth) - Math.max(rect.left, 0)
      );
      const visibleHeight = Math.max(
        0,
        Math.min(rect.bottom, window.innerHeight) - Math.max(rect.top, 0)
      );
      const visibleArea = visibleWidth * visibleHeight;
      const area = width * height;
      if (!area || visibleArea / area < 0.15) {
        return null;
      }

      return {
        id: getCandidateId(element),
        kind,
        src: src || "",
        width,
        height,
        area,
        visibleArea,
      };
    };

    const candidates = [];

    for (const image of document.images) {
      const src = image.currentSrc || image.src || "";
      const candidate = toCandidate(image, "img", src);
      if (candidate) {
        candidates.push(candidate);
      }
    }

    for (const canvas of document.querySelectorAll("canvas")) {
      const candidate = toCandidate(canvas, "canvas", "");
      if (candidate) {
        candidates.push(candidate);
      }
    }

    for (const element of document.querySelectorAll("div, section, article, figure, a")) {
      const backgroundImage = window.getComputedStyle(element).backgroundImage || "";
      if (!backgroundImage || backgroundImage === "none") {
        continue;
      }
      const src = parseBackgroundUrl(backgroundImage);
      const candidate = toCandidate(element, "background", src);
      if (candidate) {
        candidates.push(candidate);
      }
    }

    candidates.sort((a, b) => b.visibleArea - a.visibleArea || b.area - a.area);
    return candidates.slice(0, 20);
  });
}

function populateCandidates(candidates) {
  const previousValue = elements.imageCandidate.value;
  currentCandidates = candidates;
  elements.imageCandidate.innerHTML = "";

  if (!candidates.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No visible image candidates";
    elements.imageCandidate.appendChild(option);
    return { selectionChanged: previousValue !== "", selectionLost: previousValue !== "" };
  }

  for (const candidate of candidates) {
    const option = document.createElement("option");
    option.value = candidate.id;
    option.textContent = `${candidate.kind} ${candidate.width}x${candidate.height} ${imageSourceName(candidate.src)}`;
    elements.imageCandidate.appendChild(option);
  }

  const preserved = candidates.some((candidate) => candidate.id === previousValue);
  if (preserved) {
    elements.imageCandidate.value = previousValue;
  }

  return {
    selectionChanged: preserved ? false : previousValue !== elements.imageCandidate.value,
    selectionLost: previousValue !== "" && !preserved,
  };
}

async function refreshCandidates() {
  const tab = await getActiveTab();
  setStatus("Scanning page images...", "loading");
  const candidates = await scanCandidates(tab.id);
  const update = populateCandidates(candidates);
  if (update.selectionChanged || update.selectionLost) {
    await clearOverlay().catch(() => {});
  }
  setStatus(
    candidates.length ? `Found ${candidates.length} visible image candidate(s).` : "No visible page images found.",
    candidates.length ? "success" : "error"
  );
}

async function fetchImageAsDataUrl(src) {
  const response = await fetch(src);
  if (!response.ok) {
    throw new Error(`Image fetch failed with status ${response.status}.`);
  }
  const blob = await response.blob();
  return blobToDataUrl(blob);
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
  context.drawImage(
    image,
    cropX,
    cropY,
    cropWidth,
    cropHeight,
    0,
    0,
    cropWidth,
    cropHeight
  );
  return canvas.toDataURL("image/png");
}

async function prepareCandidateCapture(tabId, candidateId) {
  return runInTab(
    tabId,
    (id) => {
      const element = document.querySelector(`[data-capcapocr-id="${id}"]`);
      if (!element) {
        throw new Error("Selected image element was not found.");
      }

      element.scrollIntoView({ behavior: "auto", block: "center", inline: "center" });
      const rect = element.getBoundingClientRect();
      const src =
        element.tagName === "IMG"
          ? element.currentSrc || element.src || ""
          : (() => {
              const backgroundImage = window.getComputedStyle(element).backgroundImage || "";
              const match = backgroundImage.match(/url\((['"]?)(.*?)\1\)/i);
              return match ? match[2] : "";
            })();

      return {
        tagName: element.tagName,
        src,
        rect: {
          left: rect.left,
          top: rect.top,
          width: rect.width,
          height: rect.height,
        },
        viewport: {
          width: window.innerWidth,
          height: window.innerHeight,
        },
      };
    },
    [candidateId]
  );
}

async function getSelectedImageData(tabId) {
  const candidateId = elements.imageCandidate.value;
  if (!candidateId) {
    throw new Error("Select a page image first.");
  }

  const candidate = currentCandidates.find((item) => item.id === candidateId);
  if (!candidate) {
    throw new Error("Selected page image is stale. Refresh images and try again.");
  }

  const captureInfo = await prepareCandidateCapture(tabId, candidateId);
  await delay(150);

  if (captureInfo.src && !captureInfo.src.startsWith("blob:")) {
    try {
      return {
        imageBase64: await fetchImageAsDataUrl(captureInfo.src),
        candidateId,
      };
    } catch {
      // Fall back to visible-tab crop if direct fetch is blocked.
    }
  }

  const screenshot = await captureVisibleTab();
  return {
    imageBase64: await cropVisibleTab(screenshot, captureInfo.rect, captureInfo.viewport),
    candidateId,
  };
}

async function renderOverlay(tabId, phase2Payload, candidateId) {
  await runInTab(
    tabId,
    (payload, overlayRootId, selectedId) => {
      const fitTextToBubble = (container, textNode, boxWidth, boxHeight) => {
        const maxFontSize = Math.max(12, Math.min(28, Math.floor(Math.min(boxWidth / 5.2, boxHeight / 2.1))));
        const minFontSize = 8;

        textNode.style.fontSize = `${maxFontSize}px`;

        while (
          parseFloat(textNode.style.fontSize) > minFontSize &&
          (textNode.scrollWidth > container.clientWidth || textNode.scrollHeight > container.clientHeight)
        ) {
          const nextFontSize = parseFloat(textNode.style.fontSize) - 1;
          textNode.style.fontSize = `${nextFontSize}px`;
        }
      };

      const existing = document.getElementById(overlayRootId);
      if (existing) {
        existing.remove();
      }

      const host = document.querySelector(`[data-capcapocr-id="${selectedId}"]`);
      if (!host) {
        throw new Error("Selected image element was not found for overlay.");
      }

      const rect = host.getBoundingClientRect();
      const hostLeft = rect.left + window.scrollX;
      const hostTop = rect.top + window.scrollY;
      const root = document.createElement("div");
      root.id = overlayRootId;
      root.style.position = "absolute";
      root.style.left = `${Math.round(hostLeft)}px`;
      root.style.top = `${Math.round(hostTop)}px`;
      root.style.width = `${Math.round(rect.width)}px`;
      root.style.height = `${Math.round(rect.height)}px`;
      root.style.zIndex = "2147483647";
      root.style.pointerEvents = "none";
      root.style.overflow = "hidden";

      const imageWidth = payload?.image?.width || rect.width || 1;
      const imageHeight = payload?.image?.height || rect.height || 1;
      const scaleX = rect.width / imageWidth;
      const scaleY = rect.height / imageHeight;

      for (const group of payload?.groups || []) {
        const text = (group.translated_text || group.corrected_text || group.source_text || "").trim();
        if (!text) {
          continue;
        }

        const bubble = document.createElement("div");
        const boxWidth = Math.max(24, Math.round((group.width || 0) * scaleX));
        const boxHeight = Math.max(24, Math.round((group.height || 0) * scaleY));
        bubble.style.position = "absolute";
        bubble.style.left = `${Math.round((group.x || 0) * scaleX)}px`;
        bubble.style.top = `${Math.round((group.y || 0) * scaleY)}px`;
        bubble.style.width = `${boxWidth}px`;
        bubble.style.height = `${boxHeight}px`;
        bubble.style.display = "flex";
        bubble.style.alignItems = "center";
        bubble.style.justifyContent = "center";
        bubble.style.textAlign = "center";
        bubble.style.padding = "2px";
        bubble.style.background = "rgba(255, 255, 255, 0.98)";
        bubble.style.overflow = "hidden";
        bubble.style.borderRadius = `${Math.max(
          6,
          Math.floor(Math.min(boxWidth, boxHeight) * 0.18)
        )}px`;

        const textNode = document.createElement("div");
        textNode.textContent = text;
        textNode.style.color = "#111111";
        textNode.style.fontFamily = "'Segoe UI', sans-serif";
        textNode.style.fontWeight = "700";
        textNode.style.lineHeight = "1.15";
        textNode.style.whiteSpace = "pre-wrap";
        textNode.style.overflowWrap = "break-word";
        textNode.style.wordBreak = "break-word";
        textNode.style.maxWidth = "100%";
        textNode.style.maxHeight = "100%";
        textNode.style.overflow = "hidden";
        textNode.style.textShadow =
          "0 0 2px rgba(255,255,255,0.95), 0 0 6px rgba(255,255,255,0.95), 0 1px 0 rgba(255,255,255,0.95)";

        bubble.appendChild(textNode);
        fitTextToBubble(bubble, textNode, boxWidth - 4, boxHeight - 4);
        root.appendChild(bubble);
      }

      document.body.appendChild(root);
    },
    [phase2Payload, OVERLAY_ROOT_ID, candidateId]
  );
}

function resetOutputs() {
  elements.joinedText.value = "";
  elements.overlayText.value = "";
  elements.rawJson.value = "";
}

async function toggleSection(section) {
  setSectionCollapsed(section, !uiState[`${section}Collapsed`]);
  await saveSettings();
}

async function clearOverlay() {
  const tab = await getActiveTab();
  await runInTab(
    tab.id,
    (overlayRootId) => {
      document.getElementById(overlayRootId)?.remove();
    },
    [OVERLAY_ROOT_ID]
  );
}

async function runOverlayFlow() {
  const apiUrl = elements.apiUrl.value.trim();
  const phase2Url = elements.phase2Url.value.trim();
  const translateEnabled = elements.translateEnabled.checked;

  if (!apiUrl) {
    setStatus("OCR endpoint is required.", "error");
    return;
  }
  if (translateEnabled && !phase2Url) {
    setStatus("Phase 2 endpoint is required when Translator is enabled.", "error");
    return;
  }

  elements.runButton.disabled = true;
  elements.refreshImagesButton.disabled = true;
  elements.clearButton.disabled = true;
  resetOutputs();

  try {
    await saveSettings();
    const tab = await getActiveTab();

    setStatus("Reading selected page image...", "loading");
    const selectedImage = await getSelectedImageData(tab.id);

    setStatus("Running OCR...", "loading");
    const ocrPayload = await requestJson(
      apiUrl,
      {
        image_base64: selectedImage.imageBase64,
        source_lang: elements.sourceLang.value,
        ocr_engine: elements.ocrEngine.value,
        detection_engine: elements.detectionEngine.value,
      },
      "OCR request"
    );

    elements.joinedText.value = joinBlockText(ocrPayload.blocks);

    const overlayEnabled = elements.overlayEnabled.checked && translateEnabled;

    if (!translateEnabled) {
      elements.rawJson.value = JSON.stringify(ocrPayload, null, 2);
      await clearOverlay().catch(() => {});
      setStatus(`Detected ${ocrPayload.blocks?.length || 0} text block(s).`, "success");
      return;
    }

    setStatus("Grouping and translating...", "loading");
    const phase2Payload = await requestJson(
      phase2Url,
      {
        image: ocrPayload.image,
        blocks: ocrPayload.blocks || [],
        source_lang: elements.sourceLang.value,
        ocr_engine: elements.ocrEngine.value,
        detection_engine: elements.detectionEngine.value,
        translator_engine: elements.translatorEngine.value,
        target_lang: elements.targetLang.value,
        translate: true,
      },
      "Phase 2 request"
    );

    elements.overlayText.value = joinOverlayText(phase2Payload.groups);
    elements.rawJson.value = JSON.stringify(phase2Payload, null, 2);

    if (!overlayEnabled) {
      await clearOverlay().catch(() => {});
      setStatus(`Translated ${phase2Payload.groups?.length || 0} group(s) without overlay.`, "success");
      return;
    }

    setStatus("Drawing translated overlay...", "loading");
    await renderOverlay(tab.id, phase2Payload, selectedImage.candidateId);
    setStatus(
      `Overlayed ${phase2Payload.groups?.length || 0} bubble(s) on selected image.`,
      "success"
    );
  } catch (error) {
    setStatus(error.message || "Overlay run failed.", "error");
  } finally {
    elements.runButton.disabled = false;
    elements.refreshImagesButton.disabled = false;
    elements.clearButton.disabled = false;
  }
}

elements.refreshImagesButton.addEventListener("click", () => {
  refreshCandidates().catch((error) => setStatus(error.message || "Image scan failed.", "error"));
});

[elements.apiUrl, elements.phase2Url, elements.detectionEngine, elements.targetLang, elements.translatorEngine]
  .forEach((element) => {
    element.addEventListener("change", () => {
      persistSettingsSilently();
    });
  });

elements.sourceLang.addEventListener("change", () => {
  syncEngineOptions();
  persistSettingsSilently();
});

elements.ocrEngine.addEventListener("change", () => {
  syncEngineOptions();
  persistSettingsSilently();
});

elements.translateEnabled.addEventListener("change", () => {
  syncPipelineOptions();
  persistSettingsSilently();
});

elements.overlayEnabled.addEventListener("change", () => {
  syncPipelineOptions();
  persistSettingsSilently();
});

elements.widgetEnabled.addEventListener("change", () => {
  persistSettingsSilently();
  syncInjectedWidget();
});

elements.imageCandidate.addEventListener("change", () => {
  clearOverlay().catch(() => {});
});

elements.settingsToggle.addEventListener("click", () => {
  toggleSection("settings").catch((error) => setStatus(error.message || "Failed to save section state.", "error"));
});
elements.detailsToggle.addEventListener("click", () => {
  toggleSection("details").catch((error) => setStatus(error.message || "Failed to save section state.", "error"));
});
elements.runButton.addEventListener("click", runOverlayFlow);

elements.clearButton.addEventListener("click", async () => {
  elements.clearButton.disabled = true;
  try {
    await clearOverlay();
    setStatus("Overlay cleared.", "success");
  } catch (error) {
    setStatus(error.message || "Clear failed.", "error");
  } finally {
    elements.clearButton.disabled = false;
  }
});

Promise.all([loadSettings(), refreshCandidates()])
  .then(() => syncInjectedWidget())
  .catch((error) => {
    setStatus(error.message || "Failed to initialize popup.", "error");
  });

syncEngineOptions();
syncPipelineOptions();
