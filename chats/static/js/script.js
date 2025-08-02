// static/js/script.js

document.addEventListener("DOMContentLoaded", () => {
  // ————————— Sidebar Collapse —————————
  const collapseBtn = document.getElementById("collapse-btn");
  const container   = document.getElementById("container");
  collapseBtn?.addEventListener("click", () => {
    container.classList.toggle("collapsed");
  });

  // ————————— MCP Control —————————
  const connectBtn    = document.getElementById("mcp-connect-btn");
  const disconnectBtn = document.getElementById("mcp-disconnect-btn");
  const statusEl      = document.getElementById("mcp-status");
  async function refreshStatus() {
    const res  = await fetch("/status");
    const data = await res.json();
    const connected = Boolean(data.connected);
    statusEl.querySelector("strong").textContent = connected ? "Connected" : "Disconnected";
    connectBtn.disabled    = connected;
    disconnectBtn.disabled = !connected;
  }
  refreshStatus();
  connectBtn?.addEventListener("click", async () => {
    await fetch("/connect", { method: "POST" });
    await refreshStatus();
  });
  disconnectBtn?.addEventListener("click", async () => {
    await fetch("/disconnect", { method: "POST" });
    await refreshStatus();
  });

  // ————————— Chat Logic —————————
  const chatSection = document.querySelector("section.content");
  const chatFooter  = document.querySelector("footer");
  if (chatSection && chatFooter) {
    // append bubble helper
    function appendBubble(text, sender="assistant") {
      const bubble = document.createElement("div");
      bubble.classList.add("chat-bubble", sender);
      bubble.innerHTML = `<p>${text}</p>`;
      chatSection.appendChild(bubble);
      chatSection.scrollTop = chatSection.scrollHeight;
    }

    const inputArea = chatFooter.querySelector(".input-area");
    const inputEl   = inputArea.querySelector("input");
    inputEl.addEventListener("keydown", async e => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      const msg = inputEl.value.trim();
      if (!msg) return;
      appendBubble(msg, "user");
      inputEl.value = "";

      // typing indicator
      const typing = document.createElement("div");
      typing.classList.add("typing-indicator");
      typing.innerHTML = `<span></span><span></span><span></span>`;
      chatSection.appendChild(typing);
      chatSection.scrollTop = chatSection.scrollHeight;

      try {
        const res  = await fetch("/chat", {
          method: "POST",
          headers: {"Content-Type":"application/json"},
          body: JSON.stringify({ message: msg }),
        });
        const data = await res.json();
        typing.remove();
        if (res.ok && data.response) {
          appendBubble(data.response, "assistant");
        } else {
          appendBubble("Error: "+(data.error||res.statusText), "assistant");
        }
      } catch (err) {
        typing.remove();
        appendBubble("Connection error: "+err.message, "assistant");
      }
    });
  }

  // ————————— Upload KAK/TOR Logic —————————
  const docGenBtn = document.querySelector(".doc-generator");
  const modal     = document.getElementById("upload-modal");
  const closeBtn  = document.getElementById("close-upload-btn");
  const uploadForm= document.getElementById("upload-form");
  const uploadStatus = document.getElementById("upload-status");

  if (docGenBtn && modal && uploadForm) {
    docGenBtn.addEventListener("click", () => {
      uploadStatus.textContent = "";
      modal.classList.remove("hidden");
    });
    closeBtn?.addEventListener("click", () => modal.classList.add("hidden"));
    modal?.addEventListener("click", e => {
      if (e.target === modal) modal.classList.add("hidden");
    });

    uploadForm.addEventListener("submit", async e => {
      e.preventDefault();
      modal.classList.add("hidden");

      const submitBtn = uploadForm.querySelector("button[type=submit]");
      submitBtn.disabled = true;
      submitBtn.textContent = "Uploading…";

      uploadStatus.textContent = "✔️ Upload diterima, processing…";
      const formData = new FormData(uploadForm);

      try {
        const res  = await fetch("/upload", {
          method: "POST",
          body: formData,
        });
        const data = await res.json();
        submitBtn.disabled = false;
        submitBtn.textContent = "Kirim";

        if (res.ok && data.ingest) {
          // tampilkan hasil ingest
          appendBubble("Upload sukses. Hasil ingest:", "assistant");
          appendBubble(`<pre>${JSON.stringify(data.ingest,null,2)}</pre>`, "assistant");
        } else {
          appendBubble("Upload error: "+(data.error||res.statusText), "assistant");
        }
        uploadForm.reset();
      } catch (err) {
        submitBtn.disabled = false;
        submitBtn.textContent = "Kirim";
        appendBubble("Upload gagal: "+err.message, "assistant");
      }
    });
  }
});
