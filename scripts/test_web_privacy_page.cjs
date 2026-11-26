"use strict";
// Offline checks for the privacy policy page (/privacy).
// Usage (repository root): node --test scripts/test_web_privacy_page.cjs

const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const { build, splitPair, REQUIRED_ANCHORS, SOURCE, TARGET } = require("./build_privacy_page.cjs");

const ROOT = path.join(__dirname, "..");
const WEB = path.join(ROOT, "web");
const markdown = fs.readFileSync(SOURCE, "utf8");
const page = fs.readFileSync(TARGET, "utf8");
const HAN = /[㐀-鿿]/;

// The smallest policy that exercises the anchor rules: a bilingual heading, a table, and list items
// with the anchor written on both the Chinese and the English item, as the published policy does.
const FIXTURE = `# 隐私政策 / Privacy Policy

<!-- 起草说明：这一句不应出现在页面上。 -->

- 中英文如有不一致，以中文版为准。/ If the Chinese and English versions differ, the Chinese version prevails.

## 1. 我们是谁 / Who we are

我们是 **Go2China**。

We are **Go2China**.

## 2. 存放地点与跨境 / Where data is stored and cross-border transfers {#cross-border}

| 接收方 / Recipient | 所在地 / Location |
|---|---|
| 阿里云（香港）/ Alibaba Cloud (Hong Kong) | 中国香港 / Hong Kong, China |

## 3. 开放后适用 / Applies once launched

- **真人服务**：由真人提供。 {#in-person-services}
- **官网请求表**：提交到我们自己的后端 \`/api/service-request\`。 {#website-requests}

- **In-person services**: provided by real people. {#in-person-services}
- **Website request form**: goes to our own backend \`/api/service-request\`. {#website-requests}
`;

const articleOf = (html, lang) => {
  const start = html.indexOf(`<article class="policy-text" lang="${lang}"`);
  return html.slice(html.indexOf(">", start) + 1, html.indexOf("</article>", start));
};
const text = (html) => html.replace(/<\/?(strong|code)>/g, "").replace(/<[^>]+>/g, " ")
  .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"');

// Every line of the policy is on the page, Chinese lines in the Chinese article and English lines in
// the English one, and no drafting note in an HTML comment gets through.
function assertFaithful(md, html) {
  const zh = text(articleOf(html, "zh-CN")), en = text(articleOf(html, "en"));
  assert.doesNotMatch(en, HAN, "the English article has no Chinese");
  const body = md.replace(/<!--[\s\S]*?-->/g, "").split("\n")
    .filter((l) => l.trim() && !l.startsWith("# ") && !/^\|[\s|:-]+\|$/.test(l));
  for (const line of body) {
    const pieces = line.startsWith("|")
      ? line.replace(/^\||\|$/g, "").split("|").flatMap((c) => splitPair(c.trim()) || [c.trim()])
      : line.startsWith("## ") ? splitPair(line.slice(3).replace(/\s*\{#[a-z0-9-]+\}\s*$/, "").replace(/^\d+\.\s+/, ""))
        : (() => { const item = line.replace(/^- /, "").replace(/\s*\{#[a-z0-9-]+\}\s*$/, ""); return splitPair(item) || [item]; })();
    for (const piece of pieces) {
      const plain = piece.replace(/\*\*/g, "").replace(/`/g, "").replace(/\s*\{#[a-z0-9-]+\}\s*$/, "").trim();
      assert.ok((HAN.test(plain) ? zh : en).includes(plain), plain.slice(0, 80));
      // The English half of a "中文 / English" line is not left on the Chinese page.
      if (!HAN.test(plain) && pieces.length === 2) assert.ok(!zh.includes(plain), `on the Chinese page: ${plain.slice(0, 60)}`);
    }
  }
  for (const [, note] of md.matchAll(/<!--([\s\S]*?)-->/g)) {
    for (const line of note.split("\n").map((l) => l.trim()).filter((l) => l.length > 12)) {
      assert.ok(!text(html).includes(line), line.slice(0, 60));
    }
  }
  assert.equal((articleOf(html, "zh-CN").match(/<h2/g) || []).length, (articleOf(html, "en").match(/<h2/g) || []).length);
  assert.doesNotMatch(html, /\{#[a-z0-9-]+\}/, "anchor markers are not shown");
}

function loadCopy() {
  const w = {};
  new Function("window", fs.readFileSync(path.join(WEB, "i18n.js"), "utf8"))(w);
  return w.G2C;
}

// Runs web/privacy.js on just enough of a page: the two articles with the elements that carry an id
// or a data-anchor, the note and the language picker. Returns what the script scrolled to.
function openPage(html, lang, hash) {
  const nodes = [];
  const articles = {};
  for (const [key, attr] of [["en", "en"], ["zh", "zh-CN"]]) {
    const own = [...articleOf(html, attr).matchAll(/ (id|data-anchor)="([^"]+)"/g)].map(([, kind, value]) => {
      const node = {
        article: key, dataset: {},
        removeAttribute(name) { if (name === "id") delete this.id; else delete this.dataset.anchor; },
        scrollIntoView() { scrolled.push(this); }
      };
      if (kind === "id") node.id = value; else node.dataset.anchor = value;
      return node;
    });
    nodes.push(...own);
    articles[key] = {
      hidden: key === "zh",
      querySelectorAll(selector) { return own.filter((n) => (selector === "[id]" ? n.id !== undefined : n.dataset.anchor !== undefined)); }
    };
  }
  const scrolled = [];
  const known = { "#policy-en": articles.en, "#policy-zh": articles.zh, "#policy-note": { hidden: true, textContent: "" },
    "#lang-select": { value: "", addEventListener() {} } };
  const document = {
    documentElement: {}, title: "", readyState: "complete",
    querySelector: (selector) => known[selector],
    querySelectorAll: () => [],
    getElementById: (id) => nodes.find((n) => n.id === id) || null
  };
  new Function("window", "document", "location", "navigator", "localStorage", fs.readFileSync(path.join(WEB, "privacy.js"), "utf8"))(
    { G2C: loadCopy() }, document, { hash }, { language: "en-US" }, { getItem: () => lang, setItem() {} });
  return { nodes, articles, scrolled, note: known["#policy-note"] };
}

test("web/privacy.html is what the script builds from the current policy", () => {
  assert.equal(page, build(markdown).html, "run: node scripts/build_privacy_page.cjs");
  execFileSync(process.execPath, [path.join(ROOT, "scripts/build_privacy_page.cjs"), "--check"], { cwd: ROOT, stdio: "pipe" });
});

test("the page carries the current policy faithfully", () => {
  assertFaithful(markdown, page);
});

test("a change to the policy changes the page", () => {
  assert.notEqual(build(FIXTURE.replace("我们是", "我们就是")).html, build(FIXTURE).html);
});

test("the fixture policy builds cleanly and faithfully", () => {
  const result = build(FIXTURE);
  assert.deepEqual(result.warnings, []);
  assert.deepEqual(result.anchors.sort(), [...REQUIRED_ANCHORS].sort());
  assertFaithful(FIXTURE, result.html);
  assert.doesNotMatch(result.html, /起草说明/);
});

test("a paragraph or list item written as \"中文 / English\" in one line is split between the two pages", () => {
  const html = build(FIXTURE).html;
  const zh = text(articleOf(html, "zh-CN")), en = text(articleOf(html, "en"));
  assert.ok(zh.includes("中英文如有不一致，以中文版为准。"));
  assert.ok(!zh.includes("prevails"), "no English half on the Chinese page");
  assert.ok(en.includes("If the Chinese and English versions differ, the Chinese version prevails."));
  assert.doesNotMatch(en, HAN);
  // Paths in code do not split a line.
  assert.ok(zh.includes("提交到我们自己的后端 /api/service-request。"));
});

test("a Chinese line that still mixes in English fails --strict and names the line", () => {
  const unsplit = "- 中英文如有不一致，以中文版为准 If the Chinese and English versions differ, the Chinese version prevails.";
  const warnings = build(FIXTURE.replace(/^- 中英文如有不一致.*$/m, unsplit)).warnings;
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /^line mixes Chinese and English and cannot be split; .*: 中英文如有不一致，以中文版为准 If the Chinese/);
  assert.match(build(FIXTURE.replace(/^- 中英文如有不一致.*$/m, "- 以中文版为准。/ The Chinese text（中文版）prevails.")).warnings[0], /line mixes Chinese and English/);
  // Without a space after the slash the line is not split, only reported: the English stays off both pages' halves.
  const noSpace = build(FIXTURE.replace(/^- 中英文如有不一致.*$/m, "- 中英文如有不一致，以中文版为准。/If the Chinese and English versions differ, the Chinese version prevails."));
  assert.equal(noSpace.warnings.length, 1);
  assert.match(noSpace.warnings[0], /^line mixes Chinese and English and cannot be split; .*: 中英文如有不一致，以中文版为准。\/If the Chinese/);
  // Brand names in a Chinese sentence are fine.
  assert.deepEqual(build(FIXTURE.replace("我们是 **Go2China**。", "我们是 Go2China iOS App 和网站。")).warnings, []);
});

// Runs the real script with --strict against a policy in a scratch copy of the repository layout.
function strict(md) {
  const dir = fs.mkdtempSync(path.join(require("node:os").tmpdir(), "privacy-page-"));
  try {
    fs.mkdirSync(path.join(dir, "scripts"));
    fs.mkdirSync(path.join(dir, "docs/privacy"), { recursive: true });
    fs.mkdirSync(path.join(dir, "web"));
    fs.copyFileSync(path.join(ROOT, "scripts/build_privacy_page.cjs"), path.join(dir, "scripts/build_privacy_page.cjs"));
    fs.writeFileSync(path.join(dir, "docs/privacy/privacy-policy.md"), md);
    fs.writeFileSync(path.join(dir, "web/privacy.html"), build(md).html);
    try {
      execFileSync(process.execPath, ["scripts/build_privacy_page.cjs", "--strict"], { cwd: dir, stdio: "pipe" });
      return { code: 0, stderr: "" };
    } catch (error) {
      return { code: error.status, stderr: String(error.stderr) };
    }
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

test("--strict passes a clean policy and fails, naming the line, on a mixed line it cannot split", () => {
  assert.deepEqual(strict(FIXTURE), { code: 0, stderr: "" });
  const noSpace = strict(FIXTURE.replace(/^- 中英文如有不一致.*$/m, "- 中英文如有不一致，以中文版为准。/If the versions differ, Chinese prevails."));
  assert.equal(noSpace.code, 1);
  assert.ok(noSpace.stderr.includes("以中文版为准。/If the versions differ, Chinese prevails."), noSpace.stderr);
  const line = "中英文如有不一致，以中文版为准 If the Chinese and English versions differ, the Chinese version prevails.";
  const result = strict(FIXTURE.replace(/^- 中英文如有不一致.*$/m, `- ${line}`));
  assert.equal(result.code, 1);
  assert.ok(result.stderr.includes(`line mixes Chinese and English and cannot be split`), result.stderr);
  assert.ok(result.stderr.includes(line), "the line is named");
  // A missing anchor the service request form needs fails --strict too.
  const anchor = strict(FIXTURE.replace(/ \{#cross-border\}/g, ""));
  assert.equal(anchor.code, 1);
  assert.match(anchor.stderr, /#cross-border is missing/);
});

test("anchors come only from the policy, once in each language", () => {
  const html = build(FIXTURE).html;
  const en = articleOf(html, "en"), zh = articleOf(html, "zh-CN");
  for (const anchor of REQUIRED_ANCHORS) {
    assert.equal(en.match(new RegExp(` id="${anchor}"`, "g")).length, 1, anchor);
    assert.equal(zh.match(new RegExp(` data-anchor="${anchor}"`, "g")).length, 1, anchor);
  }
  assert.match(en, /<h2 id="cross-border">2\. Where data is stored and cross-border transfers<\/h2>/);
  assert.match(zh, /<h2 data-anchor="cross-border">2\. 存放地点与跨境<\/h2>/);
  assert.match(en, /<li id="in-person-services"><strong>In-person services<\/strong>: provided by real people\.<\/li>/);
  // No anchor the policy did not write: plain headings get none.
  assert.match(en, /<h2>1\. Who we are<\/h2>/);
  const ids = [...html.matchAll(/ id="([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(ids, [...new Set(ids)], "no id twice in the page");
});

test("anchor problems are reported clearly", () => {
  const missing = build(FIXTURE.replace(/ \{#website-requests\}/g, "")).warnings;
  assert.equal(missing.length, 1);
  assert.match(missing[0], /#website-requests is missing: the service request form \(#1862\) links to \/privacy#website-requests/);
  for (const anchor of REQUIRED_ANCHORS) {
    const warnings = build(FIXTURE.replace(new RegExp(` \\{#${anchor}\\}`, "g"), "")).warnings;
    assert.ok(warnings.some((w) => w.includes(`#${anchor} is missing`)), anchor);
  }
  const englishOnly = build(FIXTURE.replace("由真人提供。 {#in-person-services}", "由真人提供。")).warnings;
  assert.deepEqual(englishOnly, ["anchor #in-person-services is only on the English text: add {#in-person-services} to the Chinese one too"]);
  const twice = build(FIXTURE.replace("We are **Go2China**.", "We are **Go2China**. {#cross-border}")).warnings;
  assert.deepEqual(twice, ["anchor #cross-border is used more than once in one language"]);
  // The current policy is reported too until it has the anchors.
  const current = build(markdown).warnings;
  for (const anchor of REQUIRED_ANCHORS) {
    assert.equal(current.some((w) => w.includes(`#${anchor} is missing`)), !new RegExp(`\\{#${anchor}\\}`).test(markdown), anchor);
  }
});

test("a link to an anchor lands on the text in the language shown, Chinese or English", () => {
  const html = build(FIXTURE).html;
  for (const [lang, article] of [["zh", "zh"], ["en", "en"], ["ar", "en"]]) {
    for (const anchor of REQUIRED_ANCHORS) {
      const { nodes, articles, scrolled } = openPage(html, lang, `#${anchor}`);
      assert.equal(scrolled.length, 1, `${lang} #${anchor}`);
      assert.equal(scrolled[0].article, article, `${lang} #${anchor}`);
      assert.equal(scrolled[0].id, anchor);
      assert.equal(articles[article].hidden, false);
      assert.equal(articles[article === "zh" ? "en" : "zh"].hidden, true);
      // Only the article on screen has ids, so none is duplicated.
      const ids = nodes.filter((n) => n.id !== undefined);
      assert.ok(ids.every((n) => n.article === article), `${lang}: ids only in the shown article`);
      assert.equal(new Set(ids.map((n) => n.id)).size, ids.length);
    }
  }
});

test("a malformed anchor in the address is ignored", () => {
  const { scrolled, articles } = openPage(build(FIXTURE).html, "zh", "#%E0%A4%A");
  assert.deepEqual(scrolled, []);
  assert.equal(articles.zh.hidden, false);
});

test("the published policy carries the anchors the website links to", () => {
  // Policy 1.0 (#1877): section 5 is #recipients, section 6 is #cross-border, and the launch section's
  // items on in-person services and the website form carry the form's other two anchors, in both languages.
  assert.deepEqual(build(markdown).warnings, []);
  const en = articleOf(page, "en"), zh = articleOf(page, "zh-CN");
  assert.match(en, /<h2 id="recipients">5\. Who we share with<\/h2>/);
  assert.match(zh, /<h2 data-anchor="recipients">5\. 我们与谁共享<\/h2>/);
  assert.match(en, /<h2 id="cross-border">6\. Where data is stored and cross-border transfers<\/h2>/);
  assert.match(zh, /<h2 data-anchor="cross-border">6\. 存放地点与跨境<\/h2>/);
  for (const anchor of ["in-person-services", "website-requests"]) {
    assert.match(en, new RegExp(`<li id="${anchor}">`), anchor);
    assert.match(zh, new RegExp(`<li data-anchor="${anchor}">`), anchor);
  }
  // The language clause is on both pages, each in its own language.
  assert.ok(text(en).includes("If the Chinese and English versions differ, the Chinese version prevails."));
  assert.ok(text(zh).includes("中英文如有不一致，以中文版为准。") && !text(zh).includes("prevails"));
});

test("the page is in Chinese and English only; other languages fall back to English and say why", () => {
  const G2C = loadCopy();
  for (const [lang, d] of Object.entries(G2C.T)) {
    assert.ok(d.privacyPage.title.trim() && d.privacyPage.back.trim() && d.privacyLink.trim(), lang);
    const { note, articles } = openPage(build(FIXTURE).html, lang, "");
    assert.equal(articles.zh.hidden, lang !== "zh", lang);
    if (lang === "en" || lang === "zh") assert.equal(note.hidden, true, lang);
    else {
      assert.ok(d.privacyPage.fallback.trim(), `${lang} explains the fallback to English`);
      assert.equal(note.textContent, d.privacyPage.fallback);
      assert.equal(note.hidden, false, lang);
    }
  }
});

test("the home page footer links to the privacy policy", () => {
  const html = fs.readFileSync(path.join(WEB, "index.html"), "utf8");
  const footer = html.slice(html.indexOf('<footer class="foot">'));
  assert.match(footer, /<a href="\/privacy" data-i18n="privacyLink">Privacy policy<\/a>/);
  assert.match(page, /<a href="\/privacy" data-i18n="privacyLink">Privacy policy<\/a>/);
});
