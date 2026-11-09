#!/usr/bin/env node
// 把程式碼檔案排成好讀的 HTML：Shiki 語法高亮、亮／暗雙主題、粗體與斜體、行號、可調字級。
//
// 用法：
//   node render.mjs <檔案...> [-o out.html] [--title "標題"] [--lang python]
//                   [--light github-light] [--dark one-dark-pro] [--fragment]
//
//   --lang      指定語言，套用到所有輸入檔（檔案沒有副檔名或副檔名猜錯時用）
//   --light     亮色主題名稱（Shiki 內建主題），預設 github-light
//   --dark      暗色主題名稱，預設 one-dark-pro
//   --fragment  只輸出 <style> + 程式碼區塊 + <script>，給要嵌進既有頁面的情況
import { readFile, writeFile } from 'node:fs/promises';
import { basename, extname } from 'node:path';

let shiki;
try {
  shiki = await import('shiki');
} catch {
  console.error('找不到 shiki。請先在這支腳本所在的目錄執行一次：npm install');
  process.exit(2);
}
const { createHighlighter, bundledThemes, bundledLanguages } = shiki;

// ---- 參數 ----
const opts = { out: 'code.html', title: '程式碼', lang: null, light: 'github-light', dark: 'one-dark-pro', fragment: false };
const files = [];
const argv = process.argv.slice(2);
for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a === '-o') opts.out = argv[++i];
  else if (a === '--title') opts.title = argv[++i];
  else if (a === '--lang') opts.lang = argv[++i];
  else if (a === '--light') opts.light = argv[++i];
  else if (a === '--dark') opts.dark = argv[++i];
  else if (a === '--fragment') opts.fragment = true;
  else if (a.startsWith('-')) { console.error(`不認得的參數：${a}`); process.exit(1); }
  else files.push(a);
}
if (!files.length) {
  console.error('用法：node render.mjs <檔案...> [-o out.html] [--title "標題"] [--lang 語言] [--light 主題] [--dark 主題] [--fragment]');
  process.exit(1);
}
for (const t of [opts.light, opts.dark]) {
  if (!(t in bundledThemes)) {
    console.error(`沒有這個主題：${t}。可用的主題：\n${Object.keys(bundledThemes).join(', ')}`);
    process.exit(1);
  }
}
if (opts.lang && !(opts.lang in bundledLanguages)) {
  console.error(`Shiki 不支援這個語言：${opts.lang}`);
  process.exit(1);
}

// ---- 副檔名對應語言 ----
const EXT = {
  py: 'python', js: 'javascript', mjs: 'javascript', cjs: 'javascript', ts: 'typescript',
  tsx: 'tsx', jsx: 'jsx', sh: 'bash', zsh: 'bash', yml: 'yaml', md: 'markdown',
  rs: 'rust', rb: 'ruby', kt: 'kotlin', cs: 'csharp', h: 'c', hpp: 'cpp', cc: 'cpp',
};
function langOf(file) {
  if (opts.lang) return opts.lang;
  const ext = extname(file).slice(1).toLowerCase();
  const lang = EXT[ext] ?? ext;
  return lang in bundledLanguages ? lang : 'text';
}

// ---- 字形規則：在現成主題上補粗體與斜體，顏色沿用原主題 ----
const STYLE_RULES = [
  // 斜體：不會執行、或屬於「說明」的部分
  { scope: ['comment', 'punctuation.definition.comment', 'string.quoted.docstring',
            'string.quoted.docstring.multi.python', 'comment.block.documentation'], fontStyle: 'italic' },
  // 粗體：決定程式流程與結構的關鍵字（不含 = + < 這類運算子，加粗運算子會讓畫面太雜）
  { scope: ['keyword.control', 'keyword.other', 'keyword.declaration', 'storage.type', 'storage.modifier',
            'keyword.operator.new', 'keyword.operator.expression', 'keyword.operator.logical.python'],
    fontStyle: 'bold' },
  // 粗體：函式名、類別名、型別名
  { scope: ['entity.name.function', 'support.function', 'meta.function-call entity.name.function'], fontStyle: 'bold' },
  { scope: ['entity.name.type', 'entity.name.class', 'support.class', 'entity.other.inherited-class'], fontStyle: 'bold' },
  // 斜體：參數、self／this、裝飾器
  { scope: ['variable.parameter', 'variable.parameter.function.language.python',
            'meta.function.parameters variable'], fontStyle: 'italic' },
  { scope: ['variable.language', 'variable.language.special.self.python', 'variable.language.this'],
    fontStyle: 'italic' },
  { scope: ['meta.decorator', 'entity.name.function.decorator', 'punctuation.definition.decorator'],
    fontStyle: 'italic' },
  // 粗斜體：True／False／None／null 這類語言常數
  { scope: ['constant.language'], fontStyle: 'bold italic' },
];

async function styled(baseName, newName) {
  const base = structuredClone((await bundledThemes[baseName]()).default);
  base.name = newName;
  // TextMate 主題的規則格式是 { scope, settings: { fontStyle } }；
  // 只給 fontStyle 不給 foreground，顏色會沿用原主題對同一個 scope 的設定。
  const extra = STYLE_RULES.map(r => ({ scope: r.scope, settings: { fontStyle: r.fontStyle } }));
  base.tokenColors = [...(base.tokenColors ?? base.settings ?? []), ...extra];
  return base;
}

// ---- 高亮 ----
const sources = await Promise.all(files.map(async f => ({
  name: basename(f), lang: langOf(f), code: (await readFile(f, 'utf8')).replace(/\n$/, ''),
})));
const hl = await createHighlighter({
  themes: [await styled(opts.light, 'cv-light'), await styled(opts.dark, 'cv-dark')],
  langs: [...new Set(sources.map(s => s.lang).filter(l => l !== 'text'))],
});

const esc = s => s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const uid = Math.random().toString(36).slice(2, 7);
const blocks = sources.map((s, i) => {
  const html = hl.codeToHtml(s.code, { lang: s.lang, themes: { light: 'cv-light', dark: 'cv-dark' }, defaultColor: false });
  const lines = s.code.split('\n').length;
  return `<figure class="cv-block" id="cv-${uid}-${i}">
  <figcaption class="cv-bar">
    <span class="cv-dots" aria-hidden="true"><i></i><i></i><i></i></span>
    <span class="cv-name">${esc(s.name)}</span>
    <span class="cv-meta">${esc(s.lang)} · ${lines} 行</span>
    <button class="cv-copy" type="button">複製</button>
  </figcaption>
  ${html}
</figure>`;
}).join('\n');

// ---- 樣式：程式碼區塊本身（--fragment 也會帶） ----
// 顏色變數依 :root 的 data-theme 切換；沒設 data-theme 時跟系統的亮／暗設定走。
const DARK_VARS = `--cv-ink:#e6e6e6;--cv-muted:#9aa3ad;--cv-line:#2c313a;--cv-chrome:#21252b;--cv-gutter:#5c6370;--cv-hover:rgba(255,255,255,.05);`;
const DARK_CODE = sel => `
${sel} .shiki, ${sel} .shiki span {
  color: var(--shiki-dark); font-style: var(--shiki-dark-font-style);
  font-weight: var(--shiki-dark-font-weight); text-decoration: var(--shiki-dark-text-decoration);
}
${sel} .shiki { background-color: var(--shiki-dark-bg); }`;
const CODE_CSS = `
:root {
  --cv-ink:#1f2328; --cv-muted:#656d76; --cv-line:#d8dee4; --cv-chrome:#eef1f4;
  --cv-gutter:#8c959f; --cv-hover:rgba(9,105,218,.07); --cv-size:15px;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { ${DARK_VARS} } }
:root[data-theme="dark"] { ${DARK_VARS} }

.cv-block { margin: 18px 0; border: 1px solid var(--cv-line); border-radius: 10px; overflow: hidden; }
.cv-bar {
  display: flex; align-items: center; gap: 10px; padding: 8px 12px; font-size: 13px;
  color: var(--cv-ink); background: var(--cv-chrome); border-bottom: 1px solid var(--cv-line);
}
.cv-dots i { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 5px; background: #ff5f57; }
.cv-dots i:nth-child(2) { background: #febc2e; } .cv-dots i:nth-child(3) { background: #28c840; }
.cv-name { font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace; font-weight: 700; }
.cv-meta { color: var(--cv-muted); margin-right: auto; }
.cv-copy, .cv-tools button {
  font: inherit; font-size: 13px; color: var(--cv-ink); background: var(--cv-chrome);
  border: 1px solid var(--cv-line); border-radius: 6px; padding: 3px 10px; cursor: pointer;
}

/* Shiki 雙主題：顏色、粗細、斜體都從 Shiki 產生的 CSS 變數取 */
.shiki, .shiki span {
  color: var(--shiki-light); font-style: var(--shiki-light-font-style);
  font-weight: var(--shiki-light-font-weight); text-decoration: var(--shiki-light-text-decoration);
}
.shiki { background-color: var(--shiki-light-bg); }
@media (prefers-color-scheme: dark) {${DARK_CODE(':root:not([data-theme="light"])')}
}${DARK_CODE(':root[data-theme="dark"]')}

.cv-block pre.shiki {
  margin: 0; padding: 14px 0; overflow-x: auto;
  font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  font-size: var(--cv-size); line-height: 1.65; tab-size: 4; font-variant-ligatures: contextual;
}
.cv-block pre.shiki code { counter-reset: cv-ln; display: block; min-width: max-content; }
.cv-block .line { display: inline-block; width: 100%; padding-right: 20px; }
.cv-block .line::before {
  counter-increment: cv-ln; content: counter(cv-ln);
  display: inline-block; width: 3.2em; padding-right: 1.2em; text-align: right;
  color: var(--cv-gutter); font-style: normal; font-weight: 400; user-select: none;
}
.cv-block .line:hover { background: var(--cv-hover); }
`;

// ---- 樣式：完整頁面才需要的部分 ----
const PAGE_CSS = `
:root { --cv-page:#f6f7f9; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --cv-page:#16181d; } }
:root[data-theme="dark"] { --cv-page:#16181d; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--cv-page); color: var(--cv-ink); font: 15px/1.6 "Noto Sans TC", system-ui, sans-serif; }
.cv-head {
  max-width: 1000px; margin: 0 auto; padding: 28px 16px 8px;
  display: flex; flex-wrap: wrap; gap: 12px 20px; align-items: center; justify-content: space-between;
}
.cv-head h1 { font-size: 20px; margin: 0; font-weight: 600; }
.cv-tools { display: flex; gap: 14px; align-items: center; color: var(--cv-muted); font-size: 13px; }
.cv-tools input[type=range] { width: 110px; vertical-align: middle; }
.cv-legend { display: flex; flex-wrap: wrap; gap: 8px 18px; color: var(--cv-muted); font-size: 13px; max-width: 1000px; margin: 0 auto; padding: 0 16px; }
.cv-legend b, .cv-legend em { color: var(--cv-ink); }
main { max-width: 1000px; margin: 0 auto; padding: 8px 16px 48px; }
`;

// ---- 互動：複製按鈕（兩種模式都有）；字級與主題切換（只有完整頁面） ----
const COPY_JS = `
document.querySelectorAll('.cv-copy').forEach(function (b) {
  if (b.dataset.cvBound) return; b.dataset.cvBound = '1';
  b.addEventListener('click', function () {
    var code = b.closest('.cv-block').querySelector('code').innerText;
    navigator.clipboard.writeText(code).then(function () {
      b.textContent = '已複製'; setTimeout(function () { b.textContent = '複製'; }, 1200);
    });
  });
});`;
const PAGE_JS = `
var root = document.documentElement;
function get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
function set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
var size = document.getElementById('cv-size'), sizeVal = document.getElementById('cv-size-val');
function applySize(v) { root.style.setProperty('--cv-size', v + 'px'); sizeVal.textContent = v + 'px'; size.value = v; }
applySize(get('cv-size') || 15);
size.addEventListener('input', function () { applySize(size.value); set('cv-size', size.value); });
var saved = get('cv-theme'); if (saved) root.dataset.theme = saved;
document.getElementById('cv-theme').addEventListener('click', function () {
  var dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  root.dataset.theme = dark ? 'light' : 'dark'; set('cv-theme', root.dataset.theme);
});`;

const FONT_LINK = `<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:ital,wght@0,400;0,700;1,400;1,700&family=Noto+Sans+TC:wght@400;600&display=swap" rel="stylesheet">`;

const output = opts.fragment
  ? `<!-- code-reading-page fragment：需要 JetBrains Mono 的話，把下面這行 <link> 移到 <head> -->
${FONT_LINK}
<style>${CODE_CSS}</style>
${blocks}
<script>(function () {${COPY_JS}
})();</script>
`
  : `<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(opts.title)}</title>
${FONT_LINK}
<style>${CODE_CSS}${PAGE_CSS}</style>
</head>
<body>
<header class="cv-head">
  <h1>${esc(opts.title)}</h1>
  <div class="cv-tools">
    <label>字級 <input id="cv-size" type="range" min="12" max="22" value="15"> <span id="cv-size-val">15px</span></label>
    <button id="cv-theme" type="button">切換亮／暗</button>
  </div>
</header>
<p class="cv-legend">
  <span><b>粗體</b>：關鍵字、函式名、類別名</span>
  <span><em>斜體</em>：註解、docstring、參數、self／this、裝飾器</span>
  <span><b><em>粗斜體</em></b>：True／False／None 等常數</span>
</p>
<main>
${blocks}
</main>
<script>(function () {${PAGE_JS}${COPY_JS}
})();</script>
</body>
</html>
`;

await writeFile(opts.out, output);
console.log(`已輸出 ${opts.out}（${sources.length} 個檔案，${opts.fragment ? '片段' : '完整頁面'}）`);
