# highlight.js (vendored)

`highlight.bundle.js` is highlight.js 11.12.0 (BSD-3-Clause, see `LICENSE`),
bundled with esbuild to include only the core plus 8 languages: bash, json,
sql, xml, yaml, python, javascript, plaintext — everything the Note Section
needs, nothing else. No CDN, no npm install at runtime; this file is the
entire dependency.

Theme: `../../css/vendor/highlightjs/atom-one-dark.css` is highlight.js's
stock `atom-one-dark` stylesheet, unmodified.

## Rebuilding (e.g. to add a language or take an update)

```
npm install highlight.js esbuild
```

Then bundle an entry file that imports core + the languages you want and
assigns the result to `window.hljs`:

```js
import hljs from "highlight.js/lib/core";
import bash from "highlight.js/lib/languages/bash";
// ...one import per language

hljs.registerLanguage("bash", bash);
// ...one registerLanguage call per language

window.hljs = hljs;
```

```
esbuild entry.js --bundle --minify --format=iife --outfile=highlight.bundle.js
```

Language name -> highlight.js registration name mapping lives in
`app/static/js/app.js` (search for `LANGUAGE_MAP`) — update it if you add or
rename a language here.
