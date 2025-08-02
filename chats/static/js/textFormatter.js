/**
 * Escape HTML special characters to prevent XSS
 */
function escapeHtml(unsafe) {
  return unsafe
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/**
 * Process mustache {{…}} first, then code blocks, inline code, bold, italic.
 */
function applyInlineFormatting(text) {
  // 0. Handle literal {{ … }} → <code>{{ … }}</code>
  text = text.replace(
    /\{\{\s*([\s\S]+?)\s*\}\}/g,
    (_, expr) => `<code>{{ ${escapeHtml(expr)} }}</code>`
  );

  // 1. Code blocks: ```code``` → <pre><code>code</code></pre>
  text = text.replace(
    /```([\s\S]*?)```/g,
    (_, code) => `<pre><code>${escapeHtml(code)}</code></pre>`
  );

  // 2. Inline code: `code` → <code>code</code>
  text = text.replace(
    /`([^`\n]+?)`/g,
    (_, code) => `<code>${escapeHtml(code)}</code>`
  );

  // 3. Bold: **text** → <strong>text</strong>
  text = text.replace(
    /\*\*([^*\n]+?)\*\*/g,
    (_, bold) => `<strong>${bold}</strong>`
  );

  // 4. Italic: *text* → <em>text</em>
  text = text.replace(
    /\*([^*\n]+?)\*/g,
    (_, em) => `<em>${em}</em>`
  );

  return text;
}

/**
 * Format plain chat text into HTML:
 * - Mustache literals {{…}}
 * - Code blocks & inline code
 * - Bold & italic
 * - Bullet lists
 * - Numbered lists
 * - Blockquotes
 * - Line breaks & paragraphs
 */
function formatChatText(rawText) {
  // Escape & apply inline markdown-like formatting
  let safe = escapeHtml(rawText);
  safe = applyInlineFormatting(safe);

  const lines = safe.split("\n");
  let html = "";
  let inUl = false, inOl = false, inBlockquote = false;

  lines.forEach((line) => {
    const trimmed = line.trim();

    // Blockquote via Markdown ">" prefix
    if (/^&gt;\s+/.test(line)) {
      if (!inBlockquote) { html += "<blockquote>"; inBlockquote = true; }
      html += `<p>${trimmed.slice(1).trim()}</p>`;
      return;
    } else if (inBlockquote) {
      html += "</blockquote>";
      inBlockquote = false;
    }

    // Bullet list
    if (/^- /.test(trimmed)) {
      if (!inUl) { html += "<ul>"; inUl = true; }
      html += `<li>${trimmed.slice(2).trim()}</li>`;
      return;
    } else if (inUl) {
      html += "</ul>";
      inUl = false;
    }

    // Numbered list
    if (/^\d+\.\s+/.test(trimmed)) {
      if (!inOl) { html += "<ol>"; inOl = true; }
      html += `<li>${trimmed.replace(/^\d+\.\s+/, "").trim()}</li>`;
      return;
    } else if (inOl) {
      html += "</ol>";
      inOl = false;
    }

    // Empty → line break
    if (trimmed === "") {
      html += "<br>";
    } else {
      html += `<p>${trimmed}</p>`;
    }
  });

  // Close any open lists/blockquote
  if (inUl) html += "</ul>";
  if (inOl) html += "</ol>";
  if (inBlockquote) html += "</blockquote>";

  return html;
}

// Expose globally
window.formatChatText = formatChatText;
