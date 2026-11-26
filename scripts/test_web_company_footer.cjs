// The site footer names the operating company exactly as its business licence does (JT, 2026-11-26).
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const WEB = path.join(__dirname, "..", "web");
const NAME_ZH = "广州创竞科技有限公司";
const NAME_EN = "Guangzhou Chuangjing Technology Co., Ltd.";
const ADDRESS_ZH = "广州市天河区黄埔大道西100号富力盈泰广场A座410A室";
const ADDRESS_EN = "Room 410A, Tower A, R&F Yingtai Plaza, No. 100 Huangpu Avenue West, Tianhe District, Guangzhou, China";

function copy() {
  global.window = {};
  delete require.cache[require.resolve(path.join(WEB, "i18n.js"))];
  require(path.join(WEB, "i18n.js"));
  return global.window.G2C.T;
}

test("every language carries the licensed name and address", () => {
  const T = copy();
  assert.deepStrictEqual(Object.keys(T).sort(), ["ar", "en", "es", "fr", "ru", "zh"]);
  for (const [lang, t] of Object.entries(T)) {
    const zh = lang === "zh";
    assert.strictEqual(t.companyName, zh ? NAME_ZH : NAME_EN, lang);
    assert.strictEqual(t.companyAddress, zh ? ADDRESS_ZH : ADDRESS_EN, lang);
  }
});

test("the static footer in index.html matches the English copy", () => {
  const html = fs.readFileSync(path.join(WEB, "index.html"), "utf8");
  const amp = (s) => s.replace(/&/g, "&amp;");
  assert.strictEqual(html.split(`data-i18n="companyName">${NAME_EN}<`).length - 1, 2);
  assert.ok(html.includes(`data-i18n="companyAddress">${amp(ADDRESS_EN)}<`));
  assert.ok(!/Huangpu Avenue,|Room 410,|Co\., Ltd</.test(html), "old wording left in index.html");
});
