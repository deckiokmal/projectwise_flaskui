const chatWindow = document.getElementById('chat-window');
const input = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const uploadForm = document.getElementById('upload-form');

sendBtn.addEventListener('click', async () => {
  const msg = input.value.trim(); if(!msg) return;
  appendMessage(msg, 'user'); input.value = '';
  const res = await fetch('/chat', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({message: msg}) });
  const data = await res.json(); appendMessage(data.response, 'bot');
});

function appendMessage(text, sender) {
  const div = document.createElement('div');
  div.classList.add('message', sender);
  div.textContent = text;
  chatWindow.appendChild(div); chatWindow.scrollTop = chatWindow.scrollHeight;
}

uploadForm.addEventListener('submit', async e => {
  e.preventDefault();
  const formData = new FormData(uploadForm);
  const res = await fetch('/upload', {method:'POST', body: formData});
  const data = await res.json();
  alert(data.status === 'success' ? 'Upload & ingest berhasil' : 'Error: '+(data.error||JSON.stringify(data)));
});