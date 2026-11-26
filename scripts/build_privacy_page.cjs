#!/usr/bin/env node
"use strict";
// Builds web/privacy.html from docs/privacy/privacy-policy.md, the single source of the privacy policy.
//
// Usage (repository root):
//   node scripts/build_privacy_page.cjs            write web/privacy.html
//   node scripts/build_privacy_page.cjs --check    exit 1 if web/privacy.html is out of date
//   node scripts/build_privacy_page.cjs --strict   also exit 1 while the policy still has placeholders
//
// The policy gives each section in Chinese, then in English. The page shows one of the two: Chinese for
// visitors who chose Chinese, English for everyone else (see web/privacy.js). Blocks are sorted by script:
// a paragraph or list item with Chinese characters is Chinese, otherwise English. Headings and tables
// written as "中文 / English" are split at the slash after which no Chinese follows.
// HTML comments in the Markdown are drafting notes and never reach the page; the H1 is replaced by the
// page title. Anchors: "## 5." is #cross-border and "## 6." is #in-person-services unless the policy sets
// them itself; any heading, paragraph or list item can set its own with a trailing {#anchor}.
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.join(__dirname, "..");
const SOURCE = path.join(ROOT, "docs/privacy/privacy-policy.md");
const TARGET = path.join(ROOT, "web/privacy.html");
// Anchors the website links to (#1777) when the policy does not set them itself, by section number.
const SECTION_ANCHORS = { 5: "cross-border", 6: "in-person-services" };
const HAN = /[㐀-鿿]/;
const PLACEHOLDER = /【[^】]*】|\[(?:JT|To verify|Pending|In-app)[^\]]*\]/g;

const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const hasHan = (s) => HAN.test(s);

function inline(text) {
  return text.split(/(`[^`]*`)/).map((part) => (part.startsWith("`") && part.endsWith("`") && part.length > 1
    ? `<code>${esc(part.slice(1, -1))}</code>`
    : esc(part).replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>"))).join("");
}

// "中文 / English" -> [zh, en]; null when the text is not written that way.
function splitPair(text) {
  for (let i = text.indexOf("/"); i !== -1; i = text.indexOf("/", i + 1)) {
    const zh = text.slice(0, i).trim(), en = text.slice(i + 1).trim();
    if (hasHan(zh) && en && !hasHan(en)) return [zh, en];
  }
  return null;
}

function takeAnchor(text) {
  const m = text.match(/\s*\{#([a-z0-9-]+)\}\s*$/);
  return m ? [text.slice(0, m.index), m[1]] : [text, null];
}

const cells = (line) => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());

// Markdown (the subset the policy uses) -> blocks.
function parse(markdown) {
  const lines = markdown.replace(/<!--[\s\S]*?-->/g, "").split("\n");
  const blocks = [];
  let para = null;
  const flush = () => { if (para) { blocks.push({ type: "p", text: para.join(" ") }); para = null; } };
  for (const raw of lines) {
    const line = raw.trimEnd();
    const last = blocks[blocks.length - 1];
    if (!line.trim()) { flush(); if (last) last.open = false; continue; }
    if (/^#{1,6} /.test(line)) { flush(); blocks.push({ type: "h", level: line.match(/^#+/)[0].length, text: line.replace(/^#+ /, "") }); continue; }
    if (line.startsWith("|")) {
      flush();
      if (/^\|[\s|:-]+\|$/.test(line)) continue;
      if (last && last.type === "table" && last.open) last.rows.push(cells(line));
      else blocks.push({ type: "table", open: true, rows: [cells(line)] });
      continue;
    }
    if (line.startsWith("- ")) {
      flush();
      if (last && last.type === "ul" && last.open) last.items.push(line.slice(2));
      else blocks.push({ type: "ul", open: true, items: [line.slice(2)] });
      continue;
    }
    if (last && last.open) last.open = false;
    (para ||= []).push(line.trim());
  }
  flush();
  blocks.forEach((b) => { if (b.open) b.open = false; });
  return blocks;
}

// Splits the blocks into the Chinese and the English page.
function split(blocks) {
  const out = { zh: [], en: [] };
  const warnings = [];
  const set = new Set();
  for (const block of blocks) {
    if (block.type === "h") {
      if (block.level === 1) continue;
      const [full, own] = takeAnchor(block.text);
      // "5. 中文 / English": the section number goes in front of both titles.
      const [, prefix = "", number, text] = full.match(/^((\d+)\.\s+)?(.*)$/);
      const pair = (splitPair(text) || (warnings.push(`heading not written as "中文 / English": ${text}`), [text, text]))
        .map((t) => prefix + t);
      const anchor = own || SECTION_ANCHORS[number] || (number ? `section-${number}` : null);
      if (anchor) set.add(anchor);
      out.zh.push({ type: "h", level: block.level, text: pair[0], anchor });
      out.en.push({ type: "h", level: block.level, text: pair[1], anchor });
    } else if (block.type === "p") {
      const [text, anchor] = takeAnchor(block.text);
      if (anchor) set.add(anchor);
      out[hasHan(text) ? "zh" : "en"].push({ type: "p", text, anchor });
    } else if (block.type === "ul") {
      for (const lang of ["zh", "en"]) {
        const items = block.items.map(takeAnchor).filter(([text]) => hasHan(text) === (lang === "zh"));
        if (items.length) out[lang].push({ type: "ul", items });
      }
      block.items.forEach((item) => { const a = takeAnchor(item)[1]; if (a) set.add(a); });
    } else if (block.type === "table") {
      const header = block.rows[0];
      if (header.every((c) => !hasHan(c))) out.en.push({ type: "table", rows: block.rows });
      else if (header.every((c) => splitPair(c))) {
        // Written as "中文 / English" cell by cell: one table for each language.
        for (const [lang, i] of [["zh", 0], ["en", 1]]) {
          out[lang].push({ type: "table", rows: block.rows.map((row) => row.map((c) => {
            const pair = splitPair(c);
            if (!pair && hasHan(c)) warnings.push(`table cell not written as "中文 / English": ${c}`);
            return pair ? pair[i] : c;
          })) });
        }
      } else out.zh.push({ type: "table", rows: block.rows });
    }
  }
  for (const anchor of Object.values(SECTION_ANCHORS)) {
    if (!set.has(anchor)) warnings.push(`anchor #${anchor} is missing`);
  }
  return { ...out, anchors: [...set], warnings };
}

// The English article carries the real ids; the Chinese one carries them as data-anchor until
// web/privacy.js shows it, so the page never has two elements with the same id.
function render(items, lang) {
  const attr = (anchor) => (!anchor ? "" : lang === "en" ? ` id="${anchor}"` : ` data-anchor="${anchor}"`);
  return items.map((b) => {
    if (b.type === "h") return `<h${b.level}${attr(b.anchor)}>${inline(b.text)}</h${b.level}>`;
    if (b.type === "p") return `<p${attr(b.anchor)}>${inline(b.text)}</p>`;
    if (b.type === "ul") return `<ul>${b.items.map(([t, a]) => `<li${attr(a)}>${inline(t)}</li>`).join("")}</ul>`;
    const [head, ...body] = b.rows;
    return `<div class="table"><table><thead><tr>${head.map((c) => `<th>${inline(c)}</th>`).join("")}</tr></thead>` +
      `<tbody>${body.map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  }).join("\n");
}

function build(markdown) {
  const page = split(parse(markdown));
  const digest = crypto.createHash("sha256").update(markdown).digest("hex");
  const html = `<!doctype html>
<!-- Generated by scripts/build_privacy_page.cjs from docs/privacy/privacy-policy.md (sha256 ${digest}). Do not edit; change the policy and run the script. -->
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>Privacy policy — go2china.space</title>
  <meta name="description" content="How go2china.space and the Go2China app handle your personal information.">
  <meta name="theme-color" content="#FFFFFF">
  <link rel="canonical" href="https://go2china.space/privacy">
  <link rel="icon" type="image/png" href="assets/g2c-logo.png">
  <link rel="stylesheet" href="styles.css">
</head>
<body class="policy-page">
  <header class="top">
    <div class="top-in">
      <a class="brand" href="/" aria-label="go2china.space">
        <img src="assets/g2c-logo.png" width="40" height="40" alt="G2C">
        <span>go2china.space</span>
      </a>
      <div class="top-actions">
        <label class="sr" for="lang-select">Language / 语言</label>
        <select class="lang" id="lang-select">
          <option value="en">English</option><option value="zh">简体中文</option>
          <option value="ru">Русский</option><option value="es">Español</option>
          <option value="ar">العربية</option><option value="fr">Français</option>
        </select>
      </div>
    </div>
  </header>

  <main class="policy">
    <h1 data-i18n="privacyPage.title">Privacy policy</h1>
    <p class="policy-note" id="policy-note" hidden></p>
    <article class="policy-text" lang="en" dir="ltr" id="policy-en">
${render(page.en, "en")}
    </article>
    <article class="policy-text" lang="zh-CN" dir="ltr" id="policy-zh" hidden>
${render(page.zh, "zh")}
    </article>
    <p class="policy-back"><a href="/" data-i18n="privacyPage.back">Back to go2china.space</a></p>
  </main>

  <footer class="foot">
    <div class="foot-in">
      <div class="foot-brand">
        <img src="assets/g2c-logo.png" width="44" height="44" alt="" loading="lazy">
        <div><strong>go2china.space</strong><span data-i18n="footTag">Your personal agent for China.</span></div>
      </div>
      <address>
        <strong data-i18n="companyName">Guangzhou Chuangjing Technology Co., Ltd</strong>
        <span data-i18n="companyAddress">Room 410, Tower A, R&amp;F Yingtai Plaza, No. 100 Huangpu Avenue, Tianhe District, Guangzhou, China</span>
        <a href="mailto:hello@go2china.space">hello@go2china.space</a>
      </address>
      <p class="copy">© 2026 <span data-i18n="companyName">Guangzhou Chuangjing Technology Co., Ltd</span> · <a href="credits.html" data-i18n="credits">Photo credits</a> · <a href="/privacy" data-i18n="privacyLink">Privacy policy</a></p>
    </div>
  </footer>

  <script src="i18n.js" defer></script>
  <script src="privacy.js" defer></script>
</body>
</html>
`;
  return { html, ...page, placeholders: markdown.replace(/<!--[\s\S]*?-->/g, "").match(PLACEHOLDER) || [] };
}

function main() {
  const args = new Set(process.argv.slice(2));
  const result = build(fs.readFileSync(SOURCE, "utf8"));
  result.warnings.forEach((w) => console.error(`warning: ${w}`));
  if (result.placeholders.length) {
    console.error(`${result.placeholders.length} placeholder(s) still in the policy, e.g. ${result.placeholders.slice(0, 3).join(" ")}`);
  }
  if (args.has("--check") || args.has("--strict")) {
    const current = fs.existsSync(TARGET) ? fs.readFileSync(TARGET, "utf8") : "";
    if (current !== result.html) { console.error("web/privacy.html is out of date: run node scripts/build_privacy_page.cjs"); process.exit(1); }
    if (args.has("--strict") && (result.placeholders.length || result.warnings.length)) process.exit(1);
    console.log("web/privacy.html is up to date");
    return;
  }
  fs.writeFileSync(TARGET, result.html);
  console.log("wrote web/privacy.html");
}

if (require.main === module) main();
module.exports = { build, parse, split, splitPair, SOURCE, TARGET };
