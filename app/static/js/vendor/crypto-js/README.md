# crypto-js (vendored)

`crypto-js.min.js` is [crypto-js](https://github.com/brix/crypto-js) 4.2.0
(MIT, see `LICENSE`), the project's official prebuilt UMD bundle —
unmodified. It assigns itself to `window.CryptoJS`. No CDN, no npm install
at runtime.

Used by the AES Encrypt/Decrypt tool (`app/static/js/utility/aes.js`) for
**AES-ECB only**. CBC/GCM/CTR use the browser's native Web Crypto API
(`crypto.subtle`) instead, which doesn't implement ECB at all — mode
ciphers that need no IV aren't part of the standard, so ECB is the one
mode this app can't get natively and needs a library for.

ECB is intentionally not the default in the tool's UI: it leaks patterns
in the plaintext (identical plaintext blocks produce identical ciphertext
blocks) and most guidance recommends against it. It's offered anyway
because some backends still default to it (e.g. Java's `Cipher.getInstance
("AES")`, which is ECB unless a mode is specified explicitly), and this is
a QA interop tool, not a security product — matching whatever the system
under test actually does is the point.

## Rebuilding / updating

```
curl -o crypto-js.min.js https://cdnjs.cloudflare.com/ajax/libs/crypto-js/<version>/crypto-js.min.js
```
