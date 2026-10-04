# The scanner's shell engine for features/scanner.feature, loaded after
# hooks/lib-shell-words.awk:
#   awk -v mode=tokens|texts -f hooks/lib-shell-words.awk -f tests/scan_json.awk
# stdin is the command; prints a JSON array of what the hooks see.
function js(s,   i, c, o) {
  o = ""
  for (i = 1; i <= length(s); i++) {
    c = substr(s, i, 1)
    if (c == "\\") o = o "\\\\"
    else if (c == "\"") o = o "\\\""
    else if (c == "\n") o = o "\\n"
    else if (c == "\t") o = o "\\t"
    else if (c == "\r") o = o "\\r"
    else o = o c
  }
  return "\"" o "\""
}
{ buf = buf (NR > 1 ? "\n" : "") $0 }
END {
  out = ""
  if (mode == "tokens") {
    n = scan(buf, w, k, q)
    for (i = 1; i <= n; i++) {
      v = (k[i] == ";") ? ";" : (k[i] == "q") ? "q:" q[i] : "w:" w[i]
      out = out (i > 1 ? "," : "") js(v)
    }
  } else {
    # exactly what the hooks feed texts_of: the text plus a newline, heredocs stripped
    nt = texts_of(strip_heredocs(buf "\n"), texts, nested)
    for (x = 1; x <= nt; x++) out = out (x > 1 ? "," : "") js(nested[x] ":" texts[x])
  }
  print "[" out "]"
}
