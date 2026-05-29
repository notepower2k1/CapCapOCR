const state = {
  imageFile: null,
  imageBitmap: null,
  blocks: [],
  groups: [],
  selectedBlockId: null,
  selectedGroupId: null,
  imageMeta: null,
  overlayVisible: false,
  overlayFontSize: 20,
  activeView: "blocks",
  zoom: 1,
  minZoom: 0.1,
  maxZoom: 8,
  offsetX: 0,
  offsetY: 0,
  isDragging: false,
  dragMoved: false,
  dragStartX: 0,
  dragStartY: 0,
  dragOriginX: 0,
  dragOriginY: 0,
};

const elements = {
  imageInput: document.getElementById("imageInput"),
  sourceLang: document.getElementById("sourceLang"),
  ocrEngine: document.getElementById("ocrEngine"),
  detectionEngine: document.getElementById("detectionEngine"),
  targetLang: document.getElementById("targetLang"),
  translatorEngine: document.getElementById("translatorEngine"),
  detectButton: document.getElementById("detectButton"),
  phase2Button: document.getElementById("phase2Button"),
  overlayButton: document.getElementById("overlayButton"),
  overlayFontSize: document.getElementById("overlayFontSize"),
  overlayFontSizeValue: document.getElementById("overlayFontSizeValue"),
  exportButton: document.getElementById("exportButton"),
  resetViewButton: document.getElementById("resetViewButton"),
  previewCanvas: document.getElementById("previewCanvas"),
  statusMessage: document.getElementById("statusMessage"),
  blockList: document.getElementById("blockList"),
  groupList: document.getElementById("groupList"),
  blockTemplate: document.getElementById("blockTemplate"),
  groupTemplate: document.getElementById("groupTemplate"),
  blockCount: document.getElementById("blockCount"),
  zoomLabel: document.getElementById("zoomLabel"),
  showBlocksButton: document.getElementById("showBlocksButton"),
  showGroupsButton: document.getElementById("showGroupsButton"),
};

const ctx = elements.previewCanvas.getContext("2d");

function setStatus(message, kind = "idle") {
  elements.statusMessage.textContent = message;
  elements.statusMessage.className = `status ${kind}`;
}

function updateBlockCount() {
  const count = state.blocks.length;
  elements.blockCount.textContent = `${count} block${count === 1 ? "" : "s"}`;
  elements.exportButton.disabled = count === 0;
  elements.phase2Button.disabled = count === 0;
  elements.overlayButton.disabled = state.groups.length === 0;
  elements.overlayButton.textContent = state.overlayVisible ? "Hide Overlay" : "Show Overlay";
}

function syncCanvasResolution() {
  const rect = elements.previewCanvas.getBoundingClientRect();
  const pixelRatio = window.devicePixelRatio || 1;
  elements.previewCanvas.width = Math.round(rect.width * pixelRatio);
  elements.previewCanvas.height = Math.round(rect.height * pixelRatio);
  ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  drawScene();
}

function fitImageToCanvas() {
  if (!state.imageBitmap) {
    return;
  }

  const rect = elements.previewCanvas.getBoundingClientRect();
  const scaleX = rect.width / state.imageBitmap.width;
  const scaleY = rect.height / state.imageBitmap.height;
  state.zoom = Math.min(scaleX, scaleY, 1);
  state.offsetX = (rect.width - state.imageBitmap.width * state.zoom) / 2;
  state.offsetY = (rect.height - state.imageBitmap.height * state.zoom) / 2;
  updateZoomLabel();
}

function updateZoomLabel() {
  elements.zoomLabel.textContent = `${Math.round(state.zoom * 100)}%`;
}

function updateOverlayFontSizeLabel() {
  elements.overlayFontSizeValue.textContent = `${state.overlayFontSize}`;
}

function syncOcrEngineOptions() {
  const sourceLang = elements.sourceLang.value;
  const ggufOption = elements.ocrEngine.querySelector('option[value="gguf"]');
  const hybridOption = elements.ocrEngine.querySelector('option[value="hybrid"]');
  const japaneseOnlyAllowed = sourceLang === "ja";

  if (ggufOption) {
    ggufOption.disabled = !japaneseOnlyAllowed;
  }
  if (hybridOption) {
    hybridOption.disabled = !japaneseOnlyAllowed;
  }

  if (!japaneseOnlyAllowed && ["gguf", "hybrid"].includes(elements.ocrEngine.value)) {
    elements.ocrEngine.value = "auto";
  }

  const bubbleAllowed = japaneseOnlyAllowed && elements.ocrEngine.value !== "paddle";
  const bubbleOption = elements.detectionEngine.querySelector('option[value="bubble"]');
  if (bubbleOption) {
    bubbleOption.disabled = !bubbleAllowed;
  }
  if (!bubbleAllowed && elements.detectionEngine.value === "bubble") {
    elements.detectionEngine.value = "text";
  }
}

function drawScene() {
  const rect = elements.previewCanvas.getBoundingClientRect();
  ctx.clearRect(0, 0, rect.width, rect.height);

  if (!state.imageBitmap) {
    drawEmptyState(rect.width, rect.height);
    return;
  }

  ctx.save();
  ctx.translate(state.offsetX, state.offsetY);
  ctx.scale(state.zoom, state.zoom);
  ctx.drawImage(state.imageBitmap, 0, 0);
  drawBlocks();
  ctx.restore();
}

function drawEmptyState(width, height) {
  ctx.save();
  ctx.fillStyle = "rgba(46, 32, 24, 0.55)";
  ctx.font = "600 18px Segoe UI";
  ctx.textAlign = "center";
  ctx.fillText("Upload an image to preview it here.", width / 2, height / 2);
  ctx.restore();
}

function drawBlocks() {
  state.blocks.forEach((block) => {
    const selected = block.id === state.selectedBlockId;
    ctx.beginPath();
    block.bbox.forEach(([x, y], index) => {
      if (index === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    });
    ctx.closePath();
    ctx.fillStyle = selected ? "rgba(255, 209, 92, 0.28)" : "rgba(201, 79, 51, 0.15)";
    ctx.strokeStyle = selected ? "#ffd15c" : "#c94f33";
    ctx.lineWidth = selected ? 3 / state.zoom : 2 / state.zoom;
    ctx.fill();
    ctx.stroke();
  });

  if (state.overlayVisible) {
    drawGroupOverlay();
  }
}

function drawGroupOverlay() {
  sortedGroups().forEach((group) => {
    if (!group.translated_text) {
      return;
    }

    const x = group.x || group.bbox?.[0]?.[0] || 0;
    const y = group.y || group.bbox?.[0]?.[1] || 0;
    const width = Math.max(group.width || 0, 24 / state.zoom);
    const height = Math.max(group.height || 0, 24 / state.zoom);
    const padding = 4 / state.zoom;
    const fontSize = Math.max(
      10 / state.zoom,
      Math.min(
        state.overlayFontSize / state.zoom,
        width / 5.2,
        height / 2.2,
      ),
    );
    const lineHeight = fontSize * 1.12;
    const maxWidth = Math.max(width - padding * 2, fontSize * 2);
    const maxLines = Math.max(Math.floor((height - padding * 2) / lineHeight), 1);
    const lines = wrapCanvasText(ctx, group.translated_text, maxWidth, maxLines);
    const textHeight = lines.length * lineHeight;
    const startY = y + Math.max((height - textHeight) / 2, 0);
    const radius = Math.min(width, height) * 0.16;

    ctx.save();
    drawRoundedRect(ctx, x, y, width, height, radius);
    ctx.fillStyle = "rgba(255, 255, 255, 0.98)";
    ctx.fill();
    ctx.fillStyle = "#111111";
    ctx.font = `${fontSize}px Segoe UI`;
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.shadowColor = "rgba(255, 255, 255, 0.96)";
    ctx.shadowBlur = 5 / state.zoom;
    ctx.shadowOffsetX = 0;
    ctx.shadowOffsetY = 0;
    lines.forEach((line, index) => {
      ctx.fillText(line, x + width / 2, startY + index * lineHeight);
    });
    ctx.restore();
  });
}

function wrapCanvasText(ctxRef, text, maxWidth, maxLines) {
  const words = text.split(/\s+/);
  if (words.length === 0) {
    return [];
  }

  let line = "";
  const lines = [];

  for (const word of words) {
    const testLine = line ? `${line} ${word}` : word;
    if (ctxRef.measureText(testLine).width > maxWidth && line) {
      lines.push(line);
      line = word;
      if (lines.length >= maxLines) {
        return lines;
      }
    } else {
      line = testLine;
    }
  }

  if (lines.length < maxLines && line) {
    lines.push(line);
  }

  return lines;
}

function drawRoundedRect(ctxRef, x, y, width, height, radius) {
  const safeRadius = Math.max(0, Math.min(radius, width / 2, height / 2));
  ctxRef.beginPath();
  ctxRef.moveTo(x + safeRadius, y);
  ctxRef.lineTo(x + width - safeRadius, y);
  ctxRef.quadraticCurveTo(x + width, y, x + width, y + safeRadius);
  ctxRef.lineTo(x + width, y + height - safeRadius);
  ctxRef.quadraticCurveTo(x + width, y + height, x + width - safeRadius, y + height);
  ctxRef.lineTo(x + safeRadius, y + height);
  ctxRef.quadraticCurveTo(x, y + height, x, y + height - safeRadius);
  ctxRef.lineTo(x, y + safeRadius);
  ctxRef.quadraticCurveTo(x, y, x + safeRadius, y);
  ctxRef.closePath();
}

async function handleFileChange(event) {
  const [file] = event.target.files;
  if (!file) {
    return;
  }

  state.imageFile = file;
  state.blocks = [];
  state.groups = [];
  state.selectedBlockId = null;
  state.selectedGroupId = null;
  state.overlayVisible = false;
  state.activeView = "blocks";
  updateBlockCount();
  renderBlockList();
  renderGroupList();
  setActiveView("blocks");

  state.imageBitmap = await createImageBitmap(file);
  fitImageToCanvas();
  drawScene();
  setStatus(`Loaded ${file.name}. Click Detect OCR when ready.`, "idle");
}

async function detectOCR() {
  if (!state.imageFile) {
    setStatus("Select an image before running OCR.", "error");
    return;
  }

  const formData = new FormData();
  formData.append("image", state.imageFile);
  formData.append("source_lang", elements.sourceLang.value);
  formData.append("ocr_engine", elements.ocrEngine.value);
  formData.append("detection_engine", elements.detectionEngine.value);

  setStatus("Running OCR. The first request may be slower while PaddleOCR initializes.", "loading");
  elements.detectButton.disabled = true;

  try {
    const response = await fetch("/api/ocr", {
      method: "POST",
      body: formData,
    });

    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "OCR request failed.");
    }

    state.imageMeta = payload.image;
    state.blocks = payload.blocks || [];
    state.groups = [];
    state.selectedBlockId = state.blocks[0]?.id ?? null;
    state.selectedGroupId = null;
    state.overlayVisible = false;
    state.activeView = "blocks";
    updateBlockCount();
    renderBlockList();
    renderGroupList();
    setActiveView("blocks");
    drawScene();
    setStatus(`OCR completed. Review ${state.blocks.length} block(s) and edit as needed.`, "success");
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    elements.detectButton.disabled = false;
  }
}

function renderBlockList() {
  elements.blockList.innerHTML = "";

  state.blocks.forEach((block) => {
    const fragment = elements.blockTemplate.content.cloneNode(true);
    const card = fragment.querySelector(".block-card");
    const idElement = fragment.querySelector(".block-id");
    const confidenceElement = fragment.querySelector(".block-confidence");
    const directionElement = fragment.querySelector(".block-direction");
    const textarea = fragment.querySelector(".block-text");

    idElement.textContent = `#${block.id}`;
    confidenceElement.textContent = `${Math.round((block.confidence || 0) * 100)}% confidence`;
    directionElement.textContent = block.direction || "horizontal";
    textarea.value = block.text || "";

    if (block.id === state.selectedBlockId) {
      card.classList.add("active");
    }

    card.addEventListener("click", () => {
      state.selectedBlockId = block.id;
      renderBlockList();
      drawScene();
      scrollSelectedBlockIntoView();
    });

    textarea.addEventListener("click", (event) => {
      event.stopPropagation();
    });

    textarea.addEventListener("input", (event) => {
      block.text = event.target.value;
    });

    elements.blockList.appendChild(fragment);
  });
}

function renderGroupList() {
  elements.groupList.innerHTML = "";

  sortedGroups().forEach((group) => {
    const fragment = elements.groupTemplate.content.cloneNode(true);
    const card = fragment.querySelector(".group-card");
    const idElement = fragment.querySelector(".group-id");
    const orderElement = fragment.querySelector(".group-order");
    const blocksElement = fragment.querySelector(".group-blocks");
    const orderInput = fragment.querySelector(".group-order-input");
    const moveEarlierButton = fragment.querySelector(".group-order-down");
    const moveLaterButton = fragment.querySelector(".group-order-up");
    const sourceTextarea = fragment.querySelector(".group-source");
    const correctedTextarea = fragment.querySelector(".group-corrected");
    const translationTextarea = fragment.querySelector(".group-translation");

    idElement.textContent = `Group #${group.id}`;
    orderElement.textContent = `Order ${group.reading_order}`;
    blocksElement.textContent = `Blocks: ${group.block_ids.join(", ")}`;
    orderInput.value = String(group.reading_order || 1);
    sourceTextarea.value = group.source_text || "";
    correctedTextarea.value = group.corrected_text || "";
    translationTextarea.value = group.translated_text || "";

    if (group.id === state.selectedGroupId) {
      card.classList.add("active");
    }

    card.addEventListener("click", () => {
      state.selectedGroupId = group.id;
      renderGroupList();
      drawScene();
    });

    moveEarlierButton.addEventListener("click", (event) => {
      event.stopPropagation();
      moveGroupOrder(group.id, -1);
    });

    moveLaterButton.addEventListener("click", (event) => {
      event.stopPropagation();
      moveGroupOrder(group.id, 1);
    });

    orderInput.addEventListener("click", (event) => {
      event.stopPropagation();
    });

    orderInput.addEventListener("input", (event) => {
      updateGroupOrder(group.id, event.target.value);
    });

    sourceTextarea.addEventListener("input", (event) => {
      group.source_text = event.target.value;
    });
    correctedTextarea.addEventListener("input", (event) => {
      group.corrected_text = event.target.value;
    });
    translationTextarea.addEventListener("input", (event) => {
      group.translated_text = event.target.value;
      drawScene();
    });

    elements.groupList.appendChild(fragment);
  });
  elements.overlayButton.disabled = state.groups.length === 0;
}

async function runPhase2() {
  if (state.blocks.length === 0) {
    setStatus("Run OCR before Phase 2.", "error");
    return;
  }

  setStatus("Grouping text, ordering for manga reading flow, and translating when available.", "loading");
  elements.phase2Button.disabled = true;

  try {
    const response = await fetch("/api/phase2", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        image: state.imageMeta,
        blocks: state.blocks,
        source_lang: elements.sourceLang.value,
        ocr_engine: elements.ocrEngine.value,
        detection_engine: elements.detectionEngine.value,
        translator_engine: elements.translatorEngine.value,
        target_lang: elements.targetLang.value,
        translate: true,
      }),
    });

    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Phase 2 request failed.");
    }

    state.groups = payload.groups || [];
    normalizeGroupOrder();
    state.selectedGroupId = state.groups[0]?.id ?? null;
    state.overlayVisible = payload.translation_enabled && state.groups.some((group) => group.translated_text);
    updateBlockCount();
    renderGroupList();
    setActiveView("groups");
    drawScene();
    setStatus(
      payload.translation_enabled
        ? `Phase 2 completed. ${state.groups.length} grouped text unit(s) translated.`
        : `Phase 2 completed. ${state.groups.length} grouped text unit(s) ordered locally. Configure the selected translator engine to enable translation.`,
      "success",
    );
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    elements.phase2Button.disabled = false;
  }
}

function setActiveView(view) {
  state.activeView = view;
  const showBlocks = view === "blocks";
  elements.blockList.classList.toggle("hidden", !showBlocks);
  elements.groupList.classList.toggle("hidden", showBlocks);
  elements.showBlocksButton.classList.toggle("active", showBlocks);
  elements.showGroupsButton.classList.toggle("active", !showBlocks);
}

function sortedGroups() {
  return [...state.groups].sort((a, b) => {
    const orderDiff = (a.reading_order || 0) - (b.reading_order || 0);
    if (orderDiff !== 0) {
      return orderDiff;
    }
    return a.id - b.id;
  });
}

function normalizeGroupOrder() {
  state.groups = sortedGroups().map((group, index) => ({
    ...group,
    reading_order: index + 1,
  }));
}

function updateGroupOrder(groupId, nextValue) {
  const parsed = Number.parseInt(nextValue, 10);
  if (Number.isNaN(parsed)) {
    return;
  }

  const ordered = sortedGroups();
  const currentIndex = ordered.findIndex((group) => group.id === groupId);
  if (currentIndex < 0) {
    return;
  }

  const bounded = Math.max(1, Math.min(parsed, Math.max(ordered.length, 1)));
  const [moved] = ordered.splice(currentIndex, 1);
  ordered.splice(bounded - 1, 0, moved);
  state.groups = ordered.map((group, index) => ({
    ...group,
    reading_order: index + 1,
  }));
  renderGroupList();
  drawScene();
}

function moveGroupOrder(groupId, delta) {
  const ordered = sortedGroups();
  const currentIndex = ordered.findIndex((group) => group.id === groupId);
  if (currentIndex < 0) {
    return;
  }

  const nextIndex = currentIndex + delta;
  if (nextIndex < 0 || nextIndex >= ordered.length) {
    return;
  }

  const [moved] = ordered.splice(currentIndex, 1);
  ordered.splice(nextIndex, 0, moved);
  state.groups = ordered.map((group, index) => ({
    ...group,
    reading_order: index + 1,
  }));
  renderGroupList();
  drawScene();
}

function scrollSelectedBlockIntoView() {
  const activeCard = elements.blockList.querySelector(".block-card.active");
  if (activeCard) {
    activeCard.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

function exportJSON() {
  const payload = {
    image: state.imageMeta || {
      width: state.imageBitmap?.width || 0,
      height: state.imageBitmap?.height || 0,
    },
    settings: {
      source_lang: elements.sourceLang.value,
      ocr_engine: elements.ocrEngine.value,
      detection_engine: elements.detectionEngine.value,
      translator_engine: elements.translatorEngine.value,
      target_lang: elements.targetLang.value,
      overlay_font_size: state.overlayFontSize,
    },
    blocks: state.blocks,
    groups: sortedGroups(),
  };

  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${(state.imageFile?.name || "ocr-result").replace(/\.[^.]+$/, "")}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function toImageSpace(clientX, clientY) {
  const rect = elements.previewCanvas.getBoundingClientRect();
  return {
    x: (clientX - rect.left - state.offsetX) / state.zoom,
    y: (clientY - rect.top - state.offsetY) / state.zoom,
  };
}

function isPointInPolygon(point, polygon) {
  let inside = false;

  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];
    const intersects =
      yi > point.y !== yj > point.y &&
      point.x < ((xj - xi) * (point.y - yi)) / ((yj - yi) || 1e-6) + xi;
    if (intersects) {
      inside = !inside;
    }
  }

  return inside;
}

function selectBlockAtPoint(clientX, clientY) {
  const point = toImageSpace(clientX, clientY);
  const hit = state.blocks.find((block) => isPointInPolygon(point, block.bbox));
  if (hit) {
    state.selectedBlockId = hit.id;
    renderBlockList();
    drawScene();
    scrollSelectedBlockIntoView();
  }
}

function handleCanvasPointerDown(event) {
  state.isDragging = true;
  state.dragMoved = false;
  state.dragStartX = event.clientX;
  state.dragStartY = event.clientY;
  state.dragOriginX = state.offsetX;
  state.dragOriginY = state.offsetY;
}

function handleCanvasPointerMove(event) {
  if (!state.isDragging) {
    return;
  }

  const dx = event.clientX - state.dragStartX;
  const dy = event.clientY - state.dragStartY;
  if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
    state.dragMoved = true;
  }

  state.offsetX = state.dragOriginX + dx;
  state.offsetY = state.dragOriginY + dy;
  drawScene();
}

function handleCanvasPointerUp(event) {
  if (!state.dragMoved) {
    selectBlockAtPoint(event.clientX, event.clientY);
  }

  state.isDragging = false;
}

function handleCanvasWheel(event) {
  if (!state.imageBitmap) {
    return;
  }

  event.preventDefault();

  const zoomFactor = event.deltaY < 0 ? 1.1 : 0.9;
  const nextZoom = Math.max(state.minZoom, Math.min(state.maxZoom, state.zoom * zoomFactor));
  const rect = elements.previewCanvas.getBoundingClientRect();
  const mouseX = event.clientX - rect.left;
  const mouseY = event.clientY - rect.top;
  const imageX = (mouseX - state.offsetX) / state.zoom;
  const imageY = (mouseY - state.offsetY) / state.zoom;

  state.zoom = nextZoom;
  state.offsetX = mouseX - imageX * state.zoom;
  state.offsetY = mouseY - imageY * state.zoom;
  updateZoomLabel();
  drawScene();
}

elements.imageInput.addEventListener("change", handleFileChange);
elements.sourceLang.addEventListener("change", syncOcrEngineOptions);
elements.ocrEngine.addEventListener("change", syncOcrEngineOptions);
elements.detectButton.addEventListener("click", detectOCR);
elements.phase2Button.addEventListener("click", runPhase2);
elements.overlayButton.addEventListener("click", () => {
  state.overlayVisible = !state.overlayVisible;
  elements.overlayButton.textContent = state.overlayVisible ? "Hide Overlay" : "Show Overlay";
  drawScene();
});
elements.overlayFontSize.addEventListener("input", (event) => {
  state.overlayFontSize = Number.parseInt(event.target.value, 10) || 20;
  updateOverlayFontSizeLabel();
  drawScene();
});
elements.exportButton.addEventListener("click", exportJSON);
elements.resetViewButton.addEventListener("click", () => {
  fitImageToCanvas();
  drawScene();
});
elements.showBlocksButton.addEventListener("click", () => setActiveView("blocks"));
elements.showGroupsButton.addEventListener("click", () => setActiveView("groups"));
elements.previewCanvas.addEventListener("pointerdown", handleCanvasPointerDown);
window.addEventListener("pointermove", handleCanvasPointerMove);
window.addEventListener("pointerup", handleCanvasPointerUp);
elements.previewCanvas.addEventListener("wheel", handleCanvasWheel, { passive: false });
window.addEventListener("resize", syncCanvasResolution);

syncCanvasResolution();
updateOverlayFontSizeLabel();
syncOcrEngineOptions();
