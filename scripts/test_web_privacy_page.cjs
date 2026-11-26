"use strict";
// Offline checks for the privacy policy page (/privacy).
// Usage (repository root): node --test scripts/test_web_privacy_page.cjs

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const { build, splitPair, SOURCE, TARGET } = require("./build_privacy_page.cjs");

const WEB = path.join(__dirname, "..", "web");
const markdown = fs.readFileSync(SOURCE, "utf8");
const page = fs.readFileSync(TARGET, "utf8");
const HAN = /[㐀-鿿]/;
const article = (lang) => page.slice(page.indexOf(`<article class="policy-text" lang="${lang}"`), page.indexOf("</article>", page.indexOf(`lang="${lang}"`)));
const text = (html) => html.replace(/<\/?(strong|code)>/g, "").replace(/<[^>]+>/g, " ").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"');

test("web/privacy.html is what the script builds from the policy", () => {
  assert.equal(page, build(markdown).html, "run: node scripts/build_privacy_page.cjs");
});

test("a change to the policy changes the page", () => {
  const changed = markdown.replace("我们不出售你的个人信息", "我们从不出售你的个人信息");
  assert.notEqual(changed, markdown);
  assert.notEqual(build(changed).html, page);
});

test("drafting notes in HTML comments never reach the page", () => {
  const notes = [...markdown.matchAll(/<!--([\s\S]*?)-->/g)].map((m) => m[1].trim()).filter(Boolean);
  assert.ok(notes.length > 0);
  for (const note of notes) {
    for (const line of note.split("\n").map((l) => l.trim()).filter((l) => l.length > 12)) {
      assert.ok(!text(page).includes(line), line.slice(0, 60));
    }
  }
  assert.doesNotMatch(page, /发布前提|状态：草稿/);
});

test("every sentence of the policy is on the page, Chinese in one article and English in the other", () => {
  const zh = text(article("zh-CN")), en = text(article("en"));
  assert.doesNotMatch(en, HAN, "the English article has no Chinese");
  const body = markdown.replace(/<!--[\s\S]*?-->/g, "").split("\n").filter((l) => l.trim() && !l.startsWith("# ") && !/^\|[\s|:-]+\|$/.test(l));
  for (const line of body) {
    const pieces = line.startsWith("|")
      ? line.replace(/^\||\|$/g, "").split("|").flatMap((c) => splitPair(c.trim()) || [c.trim()])
      : line.startsWith("## ") ? splitPair(line.slice(3)) : [line.replace(/^- /, "")];
    for (const piece of pieces) {
      const plain = piece.replace(/\*\*/g, "").replace(/`/g, "").replace(/\s*\{#[a-z0-9-]+\}\s*$/, "").trim();
      assert.ok((HAN.test(plain) ? zh : en).includes(plain), plain.slice(0, 80));
    }
  }
  // Both articles have the same sections.
  assert.equal((article("zh-CN").match(/<h2/g) || []).length, (article("en").match(/<h2/g) || []).length);
});

test("the anchors the website links to are in place", () => {
  const en = article("en"), zh = article("zh-CN");
  for (const anchor of ["cross-border", "in-person-services"]) {
    assert.equal(en.match(new RegExp(` id="${anchor}"`, "g")).length, 1, anchor);
    assert.equal(zh.match(new RegExp(` data-anchor="${anchor}"`, "g")).length, 1, anchor);
  }
  assert.match(en, /<h2 id="cross-border">5\. Where data is stored and cross-border transfers<\/h2>/);
  assert.match(en, /<h2 id="in-person-services">6\. In-person services<\/h2>/);
  // #website-requests needs the policy's paragraph on requests from the website (compliance docs lane).
  assert.equal(/ id="website-requests"/.test(en), /\{#website-requests\}/.test(markdown));
  // No id appears twice.
  const ids = [...page.matchAll(/ id="([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(ids, [...new Set(ids)]);
});

test("the page is in Chinese and English only; other languages fall back to English and say why", () => {
  const script = fs.readFileSync(path.join(WEB, "privacy.js"), "utf8");
  assert.match(script, /const view = lang === "zh" \? "zh" : "en";/);
  assert.match(script, /view === "en" && lang !== "en" \? d\.privacyPage\.fallback : ""/);
  const w = {};
  new Function("window", fs.readFileSync(path.join(WEB, "i18n.js"), "utf8"))(w);
  for (const [lang, d] of Object.entries(w.G2C.T)) {
    assert.ok(d.privacyPage.title.trim() && d.privacyPage.back.trim() && d.privacyLink.trim(), lang);
    if (lang === "en" || lang === "zh") assert.equal(d.privacyPage.fallback, "", lang);
    else assert.ok(d.privacyPage.fallback.trim(), `${lang} explains the fallback to English`);
  }
});

test("the home page footer links to the privacy policy", () => {
  const html = fs.readFileSync(path.join(WEB, "index.html"), "utf8");
  const footer = html.slice(html.indexOf('<footer class="foot">'));
  assert.match(footer, /<a href="\/privacy" data-i18n="privacyLink">Privacy policy<\/a>/);
  assert.match(page, /<a href="\/privacy" data-i18n="privacyLink">Privacy policy<\/a>/);
});
