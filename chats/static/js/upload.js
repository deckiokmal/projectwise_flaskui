// static/js/upload.js

document.addEventListener("DOMContentLoaded", () => {
  // Elemen-elemen UI
  const openBtn       = document.getElementById("open-upload-btn");
  const modal         = document.getElementById("upload-modal");
  const closeBtn      = document.getElementById("close-upload-btn");
  const form          = document.getElementById("upload-form");
  const statusEl      = document.getElementById("upload-status");
  const sendStatusBtn = document.getElementById("check-status-btn");
  const jobInput      = document.getElementById("job-id-input");
  const resultEl      = document.getElementById("status-result");
  const chatWindow    = document.getElementById("chat-window");

  /** Utility: append HTML directly ke chat window */
  function appendHtmlMessage(html, sender = "assistant") {
    const msgDiv = document.createElement("div");
    msgDiv.classList.add("message", sender);
    const bubble = document.createElement("div");
    bubble.classList.add("text");
    bubble.innerHTML = html;
    msgDiv.appendChild(bubble);
    chatWindow.appendChild(msgDiv);
    chatWindow.scrollTop = chatWindow.scrollHeight;
  }

  /** Close modal helper */
  function closeModal() {
    modal.classList.add("hidden");
  }

  /** Open modal helper */
  function openModal() {
    statusEl.textContent = "";
    modal.classList.remove("hidden");
  }

  // Buka/Tutup modal
  openBtn.addEventListener("click", openModal);
  closeBtn.addEventListener("click", closeModal);
  modal.addEventListener("click", e => { if (e.target === modal) closeModal(); });

  // ---------------------------
  // 1) Upload Handler
  // ---------------------------
  form.addEventListener("submit", async e => {
    e.preventDefault();
    closeModal();

    // Disable tombol dan tampilkan spinner
    const submitBtn = form.querySelector("button[type=submit]");
    submitBtn.disabled = true;
    submitBtn.innerHTML = `<span class="spinner"></span> Mengunggah...`;

    // Kirim form
    try {
      const formData = new FormData(form);
      statusEl.textContent = "✔️ Upload diterima, memulai proses...";

      const resp = await fetch("/upload-kak-tor", { method: "POST", body: formData });
      const text = await resp.text();
      let body;
      try { body = JSON.parse(text); } catch { throw new Error("Invalid JSON dari server"); }

      if (!resp.ok) {
        throw new Error(body.detail || resp.statusText);
      }

      const { job_id } = body;
      statusEl.innerHTML = `
        ✔️ File tersimpan.  
        <strong>Job ID:</strong> <code id="latest-job">${job_id}</code>
        <button id="copy-job-btn">Copy</button><br>
        Proses background berjalan...
      `;
      document.getElementById("copy-job-btn").addEventListener("click", () => {
        navigator.clipboard.writeText(job_id);
        statusEl.querySelector("#copy-job-btn").textContent = "Copied!";
      });

      // Reset form UI
      form.reset();
      submitBtn.disabled = false;
      submitBtn.innerHTML = "Kirim";

      // Mulai polling dengan exponential backoff
      (async function poll(delay = 5000) {
        await new Promise(r => setTimeout(r, delay));
        try {
          const r = await fetch(`/upload-kak-tor/check-status?job_id=${encodeURIComponent(job_id)}`);
          const j = await r.json();
          const info = j[job_id];
          if (info && info.status === "success") {
            // Render summary JSON
            const raw = info.result.summary.replace(/```json\s*([\s\S]*?)```/, "$1");
            const parsed = JSON.parse(raw);
            // Anda bisa menggunakan renderJsonAsList(parsed), tapi di sini kita tampil rapi
            appendHtmlMessage(`<pre>${JSON.stringify(parsed, null, 2)}</pre>`);
            return;
          } else if (info && info.status === "failure") {
            appendHtmlMessage(`<p><strong>Error:</strong> ${info.message}</p>`);
            return;
          }
          // belum selesai, lanjut polling dengan backoff hingga max ~60s
          poll(Math.min(delay * 1.5, 60000));
        } catch (err) {
          console.error("Polling error:", err);
          // retry dengan backoff
          poll(Math.min(delay * 1.5, 60000));
        }
      })();

    } catch (err) {
      console.error("Upload error:", err);
      statusEl.textContent = `❌ Upload gagal: ${err.message}`;
      // restore tombol
      const submitBtn = form.querySelector("button[type=submit]");
      submitBtn.disabled = false;
      submitBtn.innerHTML = "Kirim";
    }
  });

  // ---------------------------
  // 2) Manual Check Status
  // ---------------------------
  sendStatusBtn.addEventListener("click", async () => {
    const jobId = jobInput.value.trim();
    if (!jobId) return alert("Mohon masukkan Job ID.");

    resultEl.textContent = "Memeriksa status…";
    try {
      const res = await fetch(`/upload-kak-tor/check-status?job_id=${encodeURIComponent(jobId)}`);
      const data = await res.json();
      const info = data[jobId];
      if (!info) throw new Error("Job ID tidak ditemukan di respons.");

      if (info.status === "success") {
        const raw = info.result.summary.replace(/```json\s*([\s\S]*?)```/, "$1");
        const parsed = JSON.parse(raw);
        resultEl.innerHTML = `<pre>${JSON.stringify(parsed, null, 2)}</pre>`;
      } else {
        resultEl.innerHTML = `
          <p>Status: <strong>${info.status}</strong></p>
          <p>Pesan: ${info.message}</p>
        `;
      }
    } catch (err) {
      console.error(err);
      resultEl.textContent = `❌ Gagal cek status: ${err.message}`;
    }
  });
});
