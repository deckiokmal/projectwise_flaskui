document.addEventListener("DOMContentLoaded", () => {
  const connectBtn    = document.getElementById("mcp-connect-btn");
  const disconnectBtn = document.getElementById("mcp-disconnect-btn");
  const statusEl      = document.getElementById("mcp-status");
  const sendBtn       = document.getElementById("send-btn");
  const messageInput  = document.getElementById("user-message");
  const chatWindow    = document.getElementById("chat-window");

  let connected = false;

  function appendMessage(text, sender) {
    const msgDiv = document.createElement("div");
    msgDiv.classList.add("message", sender);
    const bubble = document.createElement("div");
    bubble.classList.add("text");
    bubble.textContent = text;
    msgDiv.appendChild(bubble);
    chatWindow.appendChild(msgDiv);
    chatWindow.scrollTop = chatWindow.scrollHeight;
  }

  function setStatus(state) {
    connected = state;
    statusEl.querySelector("strong").textContent = state ? "Connected" : "Disconnected";
    connectBtn.disabled    = state;
    disconnectBtn.disabled = !state;
    sendBtn.disabled       = !state;
  }

  function isConnected() {
    return connected;
  }

  // Ambil status awal dari server
  (async function initStatus() {
    try {
      const res  = await fetch("/status");
      const data = await res.json();
      setStatus(Boolean(data.connected));
    } catch (err) {
      console.error("Failed to fetch status:", err);
      setStatus(false);
    }
  })();

  // Connect MCP
  connectBtn.addEventListener("click", async () => {
    try {
      const res  = await fetch("/connect", { method: "POST" });
      const data = await res.json();
      if (res.ok) {
        setStatus(true);
      } else {
        alert("Connect error: " + (data.error||res.statusText));
      }
    } catch (err) {
      console.error(err);
      alert("Gagal menghubungi server untuk connect.");
    }
  });

  // Disconnect MCP
  disconnectBtn.addEventListener("click", async () => {
    try {
      const res  = await fetch("/disconnect", { method: "POST" });
      const data = await res.json();
      if (res.ok) {
        setStatus(false);
        appendMessage("Sesi MCP telah ditutup. Sampai jumpa!", "bot");
      } else {
        alert("Disconnect error: " + (data.error||res.statusText));
      }
    } catch (err) {
      console.error(err);
      alert("Gagal menghubungi server untuk disconnect.");
    }
  });

  // Kirim chat
  sendBtn.addEventListener("click", async () => {
    const text = messageInput.value.trim();
    if (!text) return;

    if (!isConnected()) {
      alert("MCP belum terhubung. Silakan klik Connect terlebih dahulu.");
      return;
    }

    appendMessage(text, "user");
    messageInput.value = "";

    try {
      const res = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text })
      });
      const data = await res.json();

      if (res.ok) {
        appendMessage(data.response, "bot");
      } else {
        appendMessage("Error: " + (data.error||res.statusText), "bot");
        setStatus(false);
        alert("MCP disconnected. Silakan reconnect.");
      }
    } catch (err) {
      console.error(err);
      appendMessage("Gagal menghubungi server.", "bot");
      setStatus(false);
      alert("Koneksi MCP terputus. Silakan klik Connect.");
    }
  });
  
  // tidak perlu setStatus(false) di sini karena sudah di-init via initStatus()
});
