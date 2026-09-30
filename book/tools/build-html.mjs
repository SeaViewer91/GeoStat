// 공간통계학 책: md → 단일 파일 HTML
//
// - 원본: book/lessons/*.md (GitHub에서 그대로 읽히는 md)
// - 결과: book/html/<강 파일명>.html (강별), book/html/book.html (책 전체)
// - HTML 한 파일에 CSS, 미리 그린 KaTeX 수식(글꼴 포함), SVG 그림을 모두 넣음. 인터넷 없이 열림
// - 절 앵커는 GitHub와 같은 규칙(github-slugger)으로 만들어, md에 쓴 링크가 HTML에서도 그대로 동작함
// - 한글 조사가 바로 붙은 굵게도 처리함 (markdown-it-cjk-friendly). md 쪽은 check_bold.py로 따로 점검함
//
// 사용: cd book/tools && npm install && npm run build
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import GithubSlugger from 'github-slugger';
import katex from 'katex';
import MarkdownIt from 'markdown-it';
import cjkFriendly from 'markdown-it-cjk-friendly';
import texmath from 'markdown-it-texmath';

const require = createRequire(import.meta.url);
const TOOLS = path.dirname(fileURLToPath(import.meta.url));
const BOOK = path.resolve(TOOLS, '..');
const LESSONS = path.join(BOOK, 'lessons');
const OUT = path.join(BOOK, 'html');
const REPO_BLOB = 'https://github.com/SeaViewer91/GeoStat/blob/main/';

const issues = [];
const warn = (file, msg) => issues.push(`${file}: ${msg}`);

// ---------------------------------------------------------------- 원본 읽기
function parseFrontMatter(raw, file) {
  const m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(raw);
  if (!m) throw new Error(`${file}: 머리말(---)이 없음`);
  const meta = {};
  for (const line of m[1].split(/\r?\n/)) {
    const kv = /^([a-z_]+):\s*(.*)$/.exec(line.trim());
    if (kv) meta[kv[1]] = kv[2].trim().replace(/^["']|["']$/g, '');
  }
  for (const k of ['id', 'part', 'title', 'app', 'version', 'updated', 'status'])
    if (meta[k] === undefined) warn(file, `머리말에 ${k}가 없음`);
  return { meta, body: raw.slice(m[0].length) };
}

// md의 맨 위·맨 아래 이동 줄([목차](../README.md) · …)은 HTML에서 따로 만들므로 뺌
function stripNavLines(body) {
  return body
    .split('\n')
    .filter((l) => !/^\[목차\]\(\.\.\/README\.md\)/.test(l.trim()))
    .join('\n');
}

const book = JSON.parse(fs.readFileSync(path.join(BOOK, 'parts.json'), 'utf8'));
const files = fs
  .readdirSync(LESSONS)
  .filter((f) => f.endsWith('.md'))
  .sort();
const lessons = files.map((file) => {
  const { meta, body } = parseFrontMatter(fs.readFileSync(path.join(LESSONS, file), 'utf8'), file);
  return { file, stem: file.replace(/\.md$/, ''), meta, body: stripNavLines(body) };
});
const byStem = new Map(lessons.map((l) => [l.stem, l]));

// ---------------------------------------------------------------- 그림
function inlineSvg(src, file) {
  const p = path.resolve(LESSONS, src);
  if (!fs.existsSync(p)) {
    warn(file, `그림 파일 없음: ${src}`);
    return null;
  }
  let svg = fs.readFileSync(p, 'utf8');
  if (/\sid="/.test(svg)) warn(file, `SVG에 id 속성이 있음: ${src}`);
  svg = svg
    .replace(/<\?xml[^>]*\?>/g, '')
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/<svg\b([^>]*)>/, (_a, attrs) => `<svg${attrs.replace(/\s(width|height)="[^"]*"/g, '')} width="100%">`);
  return svg.trim();
}

// ---------------------------------------------------------------- 렌더러
const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

/**
 * mode = 'single' (강별 파일) | 'book' (책 전체 파일)
 * 책 전체 파일에서는 강끼리 앵커가 겹치지 않도록 모든 id 앞에 'l<강번호>-'를 붙임
 */
function renderLesson(lesson, mode) {
  const { file, meta } = lesson;
  const prefix = mode === 'book' ? `l${meta.id}-` : '';
  const engine = {
    renderToString(tex, opts) {
      try {
        return katex.renderToString(tex, { ...opts, throwOnError: true, strict: 'error', output: 'html' });
      } catch (e) {
        warn(file, `수식 오류: ${e.message}`);
        return `<span class="math-error">${esc(tex)}</span>`;
      }
    },
  };
  const md = new MarkdownIt({ html: true, linkify: false, typographer: false });
  md.use(cjkFriendly);
  texmath.katex = engine;
  md.use(texmath, { engine, delimiters: ['dollars', 'gitlab'] });

  // 제목 id: GitHub와 같은 규칙
  const slugger = new GithubSlugger();
  const headings = [];
  md.core.ruler.push('heading_ids', (state) => {
    state.tokens.forEach((t, i) => {
      if (t.type !== 'heading_open') return;
      const inline = state.tokens[i + 1];
      const text = inline.children.filter((c) => c.type === 'text' || c.type === 'code_inline').map((c) => c.content).join('');
      const id = prefix + slugger.slug(text);
      t.attrSet('id', id);
      headings.push({ id, text, level: Number(t.tag.slice(1)) });
    });
  });

  // 링크: 강 md → HTML 안의 위치, 그 밖의 상대 경로 → GitHub 주소
  md.core.ruler.push('rewrite_links', (state) => {
    for (const blk of state.tokens) {
      for (const t of blk.children ?? []) {
        if (t.type !== 'link_open') continue;
        const href = t.attrGet('href');
        if (!href || /^[a-z]+:|^#/.test(href)) {
          if (href?.startsWith('#') && prefix) t.attrSet('href', `#${prefix}${href.slice(1)}`);
          continue;
        }
        const [p, hash] = href.split('#');
        const target = path.resolve(LESSONS, p);
        const stem = path.basename(target).replace(/\.md$/, '');
        if (path.dirname(target) === LESSONS && byStem.has(stem)) {
          const other = byStem.get(stem);
          if (mode === 'book') t.attrSet('href', `#l${other.meta.id}-${hash ?? ''}`.replace(/-$/, ''));
          else t.attrSet('href', `${stem}.html${hash ? '#' + hash : ''}`);
        } else if (path.dirname(target) === LESSONS && p.endsWith('.md')) {
          warn(file, `없는 강으로 가는 링크: ${href}`);
        } else {
          const rel = path.relative(path.resolve(BOOK, '..'), target).split(path.sep).join('/');
          const isDir = fs.existsSync(target) && fs.statSync(target).isDirectory();
          const base = isDir ? REPO_BLOB.replace('/blob/', '/tree/') : REPO_BLOB;
          t.attrSet('href', base + rel + (hash ? '#' + hash : ''));
        }
      }
    }
  });

  // 그림: 문단에 그림 하나만 있으면 <figure>로, SVG는 본문에 직접 넣음
  md.renderer.rules.image = (tokens, idx) => {
    const t = tokens[idx];
    const src = t.attrGet('src');
    const caption = t.content;
    if (!caption.trim()) warn(file, `그림 캡션 없음: ${src}`);
    const svg = src.endsWith('.svg') ? inlineSvg(src, file) : null;
    const inner = svg ? `<div class="fig-svg" role="img" aria-label="${esc(caption)}">${svg}</div>` : `<img src="${esc(src)}" alt="${esc(caption)}">`;
    return `<figure>${inner}<figcaption>${md.renderInline(caption)}</figcaption></figure>`;
  };
  const onlyImage = (inline) => inline?.children?.length === 1 && inline.children[0].type === 'image';
  md.renderer.rules.paragraph_open = (tokens, idx, o, e, self) => (onlyImage(tokens[idx + 1]) ? '' : self.renderToken(tokens, idx, o));
  md.renderer.rules.paragraph_close = (tokens, idx, o, e, self) => (onlyImage(tokens[idx - 1]) ? '' : self.renderToken(tokens, idx, o));
  md.renderer.rules.table_open = () => '<div class="table-wrap"><table>';
  md.renderer.rules.table_close = () => '</table></div>';

  const html = md.render(lesson.body);
  return { html, headings };
}

// ---------------------------------------------------------------- 페이지 틀
const katexCss = (() => {
  const dir = path.dirname(require.resolve('katex/dist/katex.min.css'));
  let css = fs.readFileSync(path.join(dir, 'katex.min.css'), 'utf8');
  // 글꼴은 woff2만 base64로 넣고 나머지 형식은 뺌
  css = css.replace(/src:([^;}]*)/g, (_all, srcs) => {
    const m = /url\((fonts\/[^)]+\.woff2)\)/.exec(srcs);
    if (!m) return `src:${srcs}`;
    const b64 = fs.readFileSync(path.join(dir, m[1])).toString('base64');
    return `src:url(data:font/woff2;base64,${b64}) format("woff2")`;
  });
  return css;
})();

const PAGE_CSS = `
:root{--bg:#ffffff;--fg:#1c2330;--mu:#5a6475;--line:#e3e6eb;--soft:#f5f6f8;--ac:#2563eb;--quote:#eef3fd;--side:#fafbfc}
@media (prefers-color-scheme:dark){:root{--bg:#1a1e26;--fg:#e6e9ef;--mu:#a7afbd;--line:#333a47;--soft:#222733;--ac:#6d9bff;--quote:#1f2b45;--side:#161a21}}
*{box-sizing:border-box}
html{scroll-padding-top:16px}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.75 system-ui,-apple-system,'Apple SD Gothic Neo','Malgun Gothic','Noto Sans KR',sans-serif;word-break:keep-all;overflow-wrap:break-word}
a{color:var(--ac);text-decoration:none}a:hover{text-decoration:underline}
.layout{display:flex;min-height:100vh}
nav.side{position:sticky;top:0;align-self:flex-start;width:280px;flex:none;height:100vh;overflow-y:auto;padding:24px 16px;border-right:1px solid var(--line);background:var(--side);font-size:14px;line-height:1.5}
nav.side .book-title{font-weight:700;font-size:15px;margin-bottom:4px}
nav.side .book-sub{color:var(--mu);font-size:12px;margin-bottom:16px}
nav.side .part{margin:14px 0 4px;font-weight:600;color:var(--mu);font-size:12px}
nav.side ul{list-style:none;margin:0;padding:0}
nav.side li{margin:2px 0}
nav.side li.todo{color:var(--mu);opacity:.6}
nav.side li.cur>a{font-weight:700}
nav.side ul.sec{margin:4px 0 6px 12px;font-size:13px}
main{flex:1;min-width:0;padding:32px 40px 80px}
article{max-width:780px;margin:0 auto}
h1{font-size:30px;line-height:1.3;margin:8px 0 16px}
h2{font-size:22px;margin:44px 0 12px;padding-bottom:6px;border-bottom:1px solid var(--line)}
h3{font-size:18px;margin:28px 0 8px}
p,ul,ol{margin:10px 0}
li{margin:3px 0}
blockquote{margin:14px 0;padding:10px 16px;background:var(--quote);border-left:4px solid var(--ac);border-radius:0 6px 6px 0}
blockquote p{margin:4px 0}
code{font:14px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:var(--soft);padding:1px 5px;border-radius:4px}
pre{background:var(--soft);padding:12px 16px;border-radius:6px;overflow-x:auto;line-height:1.5}
pre code{background:none;padding:0}
.table-wrap{overflow-x:auto;margin:14px 0}
table{border-collapse:collapse;font-size:14px;line-height:1.55}
th,td{border:1px solid var(--line);padding:6px 10px;vertical-align:top;text-align:left}
th{background:var(--soft)}
figure{margin:22px 0}
figure .fig-svg svg{display:block;max-width:100%;height:auto;border-radius:6px}
figcaption{font-size:14px;color:var(--mu);margin-top:8px;line-height:1.6}
.katex-display{overflow-x:auto;overflow-y:hidden;padding:4px 0}
.katex{font-size:1.08em}
details{margin:14px 0;padding:8px 14px;border:1px solid var(--line);border-radius:6px;background:var(--soft)}
details summary{cursor:pointer;font-weight:600}
hr{border:0;border-top:1px solid var(--line);margin:32px 0}
.pager{display:flex;justify-content:space-between;gap:12px;margin:48px auto 0;max-width:780px;padding-top:16px;border-top:1px solid var(--line);font-size:14px}
.meta{color:var(--mu);font-size:13px}
.cover{max-width:780px;margin:0 auto 40px}
.cover h1{font-size:36px;margin-bottom:4px}
.lesson+.lesson{margin-top:72px;padding-top:24px;border-top:3px double var(--line)}
.math-error{color:#c2410c;font-family:monospace}
@media (max-width:900px){.layout{display:block}nav.side{position:static;width:auto;height:auto;border-right:0;border-bottom:1px solid var(--line)}main{padding:20px 16px 60px}}
@media print{nav.side,.pager{display:none}main{padding:0}body{font-size:11pt}.lesson+.lesson{break-before:page;border:0;margin-top:0}figure,table,.katex-display{break-inside:avoid}h2,h3{break-after:avoid}a{color:inherit}}
`;

const HEADER_COMMENT = '<!-- 자동 생성됨 (book/tools/build-html.mjs). 원본은 book/lessons/*.md 이며 이 파일은 직접 고치지 않음 -->';
const APP_LABEL = { full: '● 앱에서 전부', partial: '◐ 일부 앱', code: '○ 코드로', none: '' };

function page(title, sideHtml, mainHtml) {
  return `<!doctype html>
${HEADER_COMMENT}
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>${esc(title)}</title>
<style>${katexCss}</style>
<style>${PAGE_CSS}</style>
</head>
<body>
<div class="layout">
<nav class="side">${sideHtml}</nav>
<main>${mainHtml}</main>
</div>
</body>
</html>
`;
}

// 목차: 부·강 전체. 쓴 강만 링크, 현재 강은 절 목록을 펼침
function sideToc({ mode, current, headingsById }) {
  let s = `<div class="book-title">${esc(book.title)}</div><div class="book-sub">${esc(book.subtitle)} · ${esc(book.status)}</div>`;
  if (mode === 'single') s += `<div><a href="book.html">책 전체 한 파일로 보기</a></div>`;
  for (const part of book.parts) {
    const label = part.part === 'appendix' ? '부록' : `${part.part}부 ${part.title}`;
    s += `<div class="part">${esc(label)}</div><ul>`;
    for (const l of part.lessons) {
      const done = lessons.find((x) => x.meta.id === l.id);
      const name = `${/^\d+$/.test(l.id) ? Number(l.id) + '강' : l.id}. ${l.title}`;
      if (!done) {
        s += `<li class="todo">${esc(name)}</li>`;
        continue;
      }
      const href = mode === 'book' ? `#l${l.id}` : `${done.stem}.html`;
      const isCur = current === l.id || mode === 'book';
      s += `<li class="${current === l.id ? 'cur' : ''}"><a href="${href}">${esc(name)}</a>`;
      const hs = headingsById.get(l.id);
      if (isCur && hs) {
        s += '<ul class="sec">';
        for (const h of hs.filter((h) => h.level === 2)) s += `<li><a href="#${h.id}">${esc(h.text)}</a></li>`;
        s += '</ul>';
      }
      s += '</li>';
    }
    s += '</ul>';
  }
  return s;
}

function lessonHeaderMeta(meta) {
  const status = { draft: '초안 (검수 전)', verified: '검증 완료', reviewed: '검수 완료' }[meta.status] ?? meta.status;
  return `<div class="meta">${esc(status)} · 판 ${esc(meta.version)} · ${esc(meta.updated)}${APP_LABEL[meta.app] ? ' · 앱 지원 ' + APP_LABEL[meta.app] : ''}</div>`;
}

// ---------------------------------------------------------------- 빌드
fs.mkdirSync(OUT, { recursive: true });

// 강별 파일
const renderedSingle = lessons.map((l) => ({ l, ...renderLesson(l, 'single') }));
const headingsSingle = new Map(renderedSingle.map((r) => [r.l.meta.id, r.headings]));
renderedSingle.forEach(({ l, html }, i) => {
  const prev = renderedSingle[i - 1]?.l;
  const next = renderedSingle[i + 1]?.l;
  const pager = `<div class="pager"><span>${prev ? `<a href="${prev.stem}.html">← ${esc(prev.meta.title)}</a>` : ''}</span><span>${next ? `<a href="${next.stem}.html">${esc(next.meta.title)} →</a>` : ''}</span></div>`;
  const main = `<article>${lessonHeaderMeta(l.meta)}${html}</article>${pager}`;
  const side = sideToc({ mode: 'single', current: l.meta.id, headingsById: headingsSingle });
  fs.writeFileSync(path.join(OUT, `${l.stem}.html`), page(`${l.meta.title} · ${book.title}`, side, main));
});

// 책 전체 파일
const renderedBook = lessons.map((l) => ({ l, ...renderLesson(l, 'book') }));
const headingsBook = new Map(renderedBook.map((r) => [r.l.meta.id, r.headings]));
const cover = `<section class="cover"><h1>${esc(book.title)}</h1><div class="meta">${esc(book.subtitle)} · ${esc(book.status)} · 빌드 ${new Date().toISOString().slice(0, 10)}</div>
<p>이 파일 하나에 지금까지 쓴 모든 강이 들어 있음. 왼쪽 목차에서 흐리게 보이는 강은 아직 쓰지 않은 강임. 브라우저 인쇄로 PDF를 만들 수 있음.</p></section>`;
const body = renderedBook.map(({ l, html }) => `<section class="lesson" id="l${l.meta.id}"><article>${lessonHeaderMeta(l.meta)}${html}</article></section>`).join('\n');
fs.writeFileSync(path.join(OUT, 'book.html'), page(book.title, sideToc({ mode: 'book', current: null, headingsById: headingsBook }), cover + body));

// 점검: 렌더링 뒤 남은 $ (수식 구분자 오류)
for (const f of fs.readdirSync(OUT).filter((f) => f.endsWith('.html'))) {
  const text = fs
    .readFileSync(path.join(OUT, f), 'utf8')
    .replace(/<style>[\s\S]*?<\/style>/g, '')
    .replace(/<span class="katex[\s\S]*?<\/annotation>/g, '')
    .replace(/<[^>]+>/g, '');
  if (text.includes('$')) warn(f, '렌더링 뒤에 $가 남음 (수식 구분자 확인)');
}

for (const f of fs.readdirSync(OUT)) {
  const kb = (fs.statSync(path.join(OUT, f)).size / 1024).toFixed(0);
  console.log(`  html/${f}  ${kb} KB`);
}
if (issues.length) {
  console.log(`\n문제 ${issues.length}건`);
  for (const m of issues) console.log('  - ' + m);
  process.exitCode = 1;
} else console.log('\n문제 없음');
