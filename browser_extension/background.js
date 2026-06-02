chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== "capcapocr_capture_visible_tab") {
    return false;
  }

  const windowId = sender.tab?.windowId;
  chrome.tabs.captureVisibleTab(windowId, { format: "png" }, (dataUrl) => {
    if (chrome.runtime.lastError) {
      sendResponse({ ok: false, error: chrome.runtime.lastError.message });
      return;
    }
    sendResponse({ ok: true, dataUrl });
  });

  return true;
});
