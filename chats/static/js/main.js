document.addEventListener("DOMContentLoaded", () => {
  // Elemen utama
  const form       = document.getElementById("chat-form");
  const chatInput  = document.getElementById("chat-input");
  const chatArea   = document.querySelector(".main__chat");
  const uploadBtn  = document.getElementById("upload-btn");
  const uploadMenu = document.getElementById("upload-menu");
  const fileInput  = document.getElementById("file-input");
  const sendBtn    = form.querySelector("button[type=submit]");

  // Utility: scroll chat ke bawah
  function scrollToBottom() {
    chatArea.scrollTop = chatArea.scrollHeight;
  }

  // Tambah pesan ke chatArea
  function appendMessage(text, sender = "assistant") {
    const msg = document.createElement("div");
    msg.classList.add("message", sender);
    msg.innerHTML = window.formatChatText(text);
    chatArea.appendChild(msg);
    scrollToBottom();
    return msg;
  }

  // Auto-resize textarea
  function initAutoResize() {
    if (!chatInput) return;
    const adjust = () => {
      chatInput.style.height = "auto";
      chatInput.style.height = chatInput.scrollHeight + "px";
      chatInput.classList.toggle(
        "scrolled",
        chatInput.scrollHeight > parseInt(getComputedStyle(chatInput).maxHeight)
      );
    };
    chatInput.addEventListener("input", adjust);
    adjust();
  }

  // Kirim chat ke backend
  async function sendMessage(msg) {
    const typing = appendMessage("…", "assistant");
    try {
      const res = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg }),
      });
      const data = await res.json();
      typing.remove();
      if (res.ok && data.response) {
        appendMessage(data.response, "assistant");
      } else {
        appendMessage("Error: " + (data.error || res.statusText), "assistant");
      }
    } catch (err) {
      typing.remove();
      appendMessage("Connection error", "assistant");
    }
  }

  // Handler form submit
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = chatInput.value.trim();
    if (!text) return;
    appendMessage(text, "user");
    chatInput.value = "";
    initAutoResize();  // reset height after clear
    sendMessage(text);
  });

  // Upload dropdown toggle & close
  uploadBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    uploadMenu.classList.toggle("hidden");
  });
  document.addEventListener("click", () => uploadMenu.classList.add("hidden"));

  // Pilih jenis file (kak/product) via data-type
  uploadMenu.addEventListener("click", (e) => {
    const btn = e.target.closest(".upload-menu__item");
    if (!btn) return;
    fileInput.accept = btn.dataset.type === "product" ? "image/*" : ".pdf,.doc,.docx,.txt";
    fileInput.click();
    uploadMenu.classList.add("hidden");
  });

  // Handle file upload
  fileInput.addEventListener("change", async () => {
    const files = Array.from(fileInput.files);
    if (!files.length) return;
    appendMessage(`Uploading ${files.length} file(s)...`, "assistant");

    const formData = new FormData();
    files.forEach((f) => formData.append("files", f));

    try {
      const res = await fetch("/upload-files", { method: "POST", body: formData });
      const data = await res.json();
      if (res.ok) {
        appendMessage("Files uploaded successfully.", "assistant");
      } else {
        appendMessage("Upload error: " + (data.error || res.statusText), "assistant");
      }
    } catch (err) {
      appendMessage("Upload failed: " + err.message, "assistant");
    } finally {
      fileInput.value = "";
    }
  });

  // Inisialisasi
  initAutoResize();
});
