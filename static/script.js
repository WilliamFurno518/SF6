const chatWindow = document.getElementById('chatWindow');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function renderMarkdown(text) {
  let html = escapeHtml(text);

  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  html = html.replace(/(?:^|\n)-\s+(.*?)(?=\n|$)/g, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>)/g, '<ul>$1</ul>');

  html = html.replace(/\n\n+/g, '</p><p>');
  html = `<p>${html}</p>`;

  return html;
}

function scrollBottom() {
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function addUserBubble(text) {
  const div = document.createElement('div');
  div.className = 'bubble user';
  div.textContent = text;
  chatWindow.appendChild(div);
  scrollBottom();
}

function getGroundingLabel(meta) {
  if (meta.used_combo_db || meta.used_local_docs || meta.frame_found) {
    return { text: "Verified", color: "green" };
  }
  if (meta.source && meta.source.includes("wiki")) {
    return { text: "Estimated", color: "yellow" };
  }
  return { text: "Low certainty", color: "red" };
}

function createAssistantBubble(payload, question) {
  const wrap = document.createElement('div');
  wrap.className = 'bubble assistant';

  const content = document.createElement('div');
  content.innerHTML = renderMarkdown(payload.reply || '');
  wrap.appendChild(content);

  // ===== 核心改动：Verified / Estimated =====
  const meta = document.createElement('div');
  meta.className = 'meta-row';

  const grounding = getGroundingLabel(payload.tool_meta || {});

  meta.innerHTML = `
    <span class="chip ${grounding.color}">${grounding.text}</span>
    <span class="chip">Source: ${payload.source || "-"}</span>
    <span class="chip">Confidence: ${payload.confidence || "-"}</span>
  `;

  wrap.appendChild(meta);

  // ===== 轻量反馈区 =====
  const feedback = document.createElement('div');
  feedback.className = 'feedback-mini';

  feedback.innerHTML = `
    <button class="fb-btn" data-type="like">👍</button>
    <button class="fb-btn" data-type="dislike">👎</button>

    <select class="fb-rating">
      <option value="">Rate</option>
      <option>1</option>
      <option>2</option>
      <option>3</option>
      <option>4</option>
      <option>5</option>
    </select>

    <input class="fb-input" placeholder="correction..." />

    <button class="fb-submit">✓</button>
  `;

  let selected = "neutral";

  feedback.querySelectorAll('.fb-btn').forEach(btn => {
    btn.onclick = () => {
      selected = btn.dataset.type;
      feedback.querySelectorAll('.fb-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    };
  });

  feedback.querySelector('.fb-submit').onclick = async () => {
    const rating = feedback.querySelector('.fb-rating').value;
    const comment = feedback.querySelector('.fb-input').value;

    await fetch('/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        answer_id: payload.answer_id,
        question,
        answer: payload.reply,
        feedback_type: selected,
        rating: rating ? Number(rating) : null,
        comment,
        source: payload.source,
        confidence: payload.confidence,
        question_type: payload.question_type
      })
    });

    feedback.innerHTML = "✔";
  };

  wrap.appendChild(feedback);

  chatWindow.appendChild(wrap);
  scrollBottom();
}

function addLoading() {
  const div = document.createElement('div');
  div.id = "loading";
  div.className = "bubble assistant";
  div.innerHTML = "Thinking...";
  chatWindow.appendChild(div);
  scrollBottom();
}

function toggleCard(id) {
  const el = document.getElementById(id);
  if (!el) return;

  el.classList.toggle("open");

  const btn = document.querySelector(`button[onclick="toggleCard('${id}')"]`);
  if (btn) {
    btn.textContent = el.classList.contains("open")
      ? "Hide Stats ▲"
      : "Show Stats ▼";
  }
}

function removeLoading() {
  const el = document.getElementById("loading");
  if (el) el.remove();
}

async function sendMessage() {
  const text = messageInput.value.trim();
  if (!text) return;

  addUserBubble(text);
  messageInput.value = "";
  addLoading();

  try {
    const res = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text })
    });

    const data = await res.json();
    removeLoading();

    createAssistantBubble(data, text);

  } catch (err) {
    removeLoading();
    createAssistantBubble({
      reply: "Error: " + err.message,
      source: "error",
      confidence: "low",
      answer_id: "local"
    }, text);
  }
}

sendBtn.onclick = sendMessage;

messageInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});