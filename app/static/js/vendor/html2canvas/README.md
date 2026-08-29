# html2canvas (vendored)

`html2canvas.min.js` is html2canvas 1.4.1 (MIT, see `LICENSE`), the
project's official prebuilt UMD bundle — unmodified. It assigns itself to
`window.html2canvas`. No CDN, no npm install at runtime.

Used by the API Client's Export Image feature (`app/static/js/api_client.js`,
`renderNodeToPngBlob`) to rasterize the request/response cards to a PNG.

## Why this instead of the earlier hand-rolled approach

The first version of Export Image serialized the target DOM into an SVG
`<foreignObject>`, drew that into an `<img>`, then `drawImage`'d it onto a
`<canvas>` — the classic dependency-free "screenshot a DOM node" trick.
Chrome taints any canvas drawn from an SVG containing `<foreignObject>`
(arbitrary embedded HTML) as a blanket security measure, regardless of the
image being same-origin — so `canvas.toBlob()` always failed with
`SecurityError: Tainted canvases may not be exported`, no matter how the
SVG was constructed. html2canvas sidesteps this entirely: it does not
rasterize an image at all, it walks the DOM and repaints each element's
box, text, and borders directly with `<canvas>` drawing primitives — so
the canvas is never "tainted" by an image load in the first place.

## Rebuilding / updating

```
npm install html2canvas@<version> --no-save
```

Then copy `node_modules/html2canvas/dist/html2canvas.min.js` and
`node_modules/html2canvas/LICENSE` here.
