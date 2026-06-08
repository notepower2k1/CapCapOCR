chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === "capcapocr_capture_visible_tab") {
    const windowId = sender.tab?.windowId;
    chrome.tabs.captureVisibleTab(windowId, { format: "png" }, (dataUrl) => {
      if (chrome.runtime.lastError) {
        sendResponse({ ok: false, error: chrome.runtime.lastError.message });
        return;
      }
      sendResponse({ ok: true, dataUrl });
    });

    return true;
  }

  if (message?.type === "capcapocr_fetch_image") {
    fetch(message.url)
      .then(async (response) => {
        if (!response.ok) {
          sendResponse({ ok: false, error: `Image fetch failed with status ${response.status}.` });
          return;
        }
        const blob = await response.blob();
        const buffer = await blob.arrayBuffer();
        const bytes = new Uint8Array(buffer);
        let binary = "";
        const chunkSize = 0x8000;
        for (let index = 0; index < bytes.length; index += chunkSize) {
          binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
        }
        const mimeType = blob.type || "image/png";
        sendResponse({ ok: true, dataUrl: `data:${mimeType};base64,${btoa(binary)}` });
      })
      .catch((error) => {
        sendResponse({ ok: false, error: error.message || "Background image fetch failed." });
      });

    return true;
  }

  return false;
});
