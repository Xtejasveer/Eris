// A tiny Python syntax highlighter: returns HTML for one line of code.

import { esc } from "./ui.js";

const KEYWORDS = new Set(("False None True and as assert async await break class continue def del elif else except " +
  "finally for from global if import in is lambda nonlocal not or pass raise return try while with yield").split(" "));
const BUILTINS = new Set(("print len range input int str float list dict set tuple sum min max abs sorted enumerate " +
  "zip map filter open type isinstance round any all reversed").split(" "));
const TOKEN = /("""[\s\S]*?"""|'''[\s\S]*?'''|[rbfu]?"(?:[^"\\]|\\.)*"?|[rbfu]?'(?:[^'\\]|\\.)*'?)|(#.*$)|(\b\d+(?:\.\d+)?\b)|([A-Za-z_]\w*)|(\s+)|(.)/gm;

export function highlightLine(line) {
  let out = "";
  let m;
  TOKEN.lastIndex = 0;
  let prevWord = "";
  while ((m = TOKEN.exec(line)) !== null) {
    const [tok, str, comment, num, word] = m;
    if (str) out += `<span class="tk-str">${esc(tok)}</span>`;
    else if (comment) out += `<span class="tk-com">${esc(tok)}</span>`;
    else if (num) out += `<span class="tk-num">${tok}</span>`;
    else if (word) {
      if (KEYWORDS.has(word)) out += `<span class="tk-kw">${word}</span>`;
      else if (prevWord === "def" || prevWord === "class") out += `<span class="tk-fn">${word}</span>`;
      else if (BUILTINS.has(word)) out += `<span class="tk-bi">${word}</span>`;
      else out += esc(word);
      prevWord = word;
      continue;
    } else out += esc(tok);
    if (tok.trim()) prevWord = "";
  }
  return out;
}

export function highlightCode(code) {
  return code.split("\n").map(highlightLine);
}
