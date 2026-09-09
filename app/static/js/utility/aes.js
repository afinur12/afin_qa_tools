(function () {
  const input = document.getElementById("aes-input");
  if (!input) return;

  const output = document.getElementById("aes-output");
  const errorBox = document.getElementById("aes-error");
  const unsupportedBox = document.getElementById("aes-unsupported");
  const modeSelect = document.getElementById("aes-mode");
  const keyFormatSelect = document.getElementById("aes-key-format");
  const outputFormatSelect = document.getElementById("aes-output-format");
  const keyInput = document.getElementById("aes-key");
  const ivInput = document.getElementById("aes-iv");
  const ivField = document.getElementById("aes-iv-field");
  const ivHint = document.getElementById("aes-iv-hint");
  const ecbHint = document.getElementById("aes-ecb-hint");
  const copyBtn = document.getElementById("aes-copy");
  const encryptBtn = document.getElementById("aes-encrypt");
  const decryptBtn = document.getElementById("aes-decrypt");

  // ECB (CryptoJS) needs neither the Web Crypto API nor an IV; CBC/GCM/CTR
  // (native crypto.subtle) need both. Only bail out entirely if neither path
  // is usable.
  const hasSubtle = !!(window.crypto && window.crypto.subtle);
  if (!hasSubtle) {
    unsupportedBox.hidden = false;
  }

  function updateIvVisibility() {
    const isEcb = modeSelect.value === "AES-ECB";
    ivField.hidden = isEcb;
    ivHint.hidden = isEcb;
    ecbHint.hidden = !isEcb;
    if (!isEcb && !hasSubtle) {
      encryptBtn.disabled = true;
      decryptBtn.disabled = true;
    } else {
      encryptBtn.disabled = false;
      decryptBtn.disabled = false;
    }
  }
  modeSelect.addEventListener("change", updateIvVisibility);
  updateIvVisibility();

  // GCM's recommended nonce is 96 bits; CBC/CTR need a full 128-bit (16-byte)
  // block-size IV. ECB uses no IV at all.
  function ivLengthFor(mode) {
    return mode === "AES-GCM" ? 12 : 16;
  }

  function bytesToHex(bytes) {
    return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  }

  function hexToBytes(hex) {
    const clean = hex.trim().replace(/\s+/g, "");
    if (!/^[0-9a-fA-F]*$/.test(clean) || clean.length % 2 !== 0) {
      throw new Error("Not valid hex (must be an even number of 0-9/a-f digits).");
    }
    const bytes = new Uint8Array(clean.length / 2);
    for (let i = 0; i < bytes.length; i += 1) bytes[i] = parseInt(clean.substr(i * 2, 2), 16);
    return bytes;
  }

  function bytesToBase64(bytes) {
    let binary = "";
    bytes.forEach((b) => {
      binary += String.fromCharCode(b);
    });
    return btoa(binary);
  }

  function base64ToBytes(base64) {
    let binary;
    try {
      binary = atob(base64.trim());
    } catch {
      throw new Error("Not valid Base64.");
    }
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    return bytes;
  }

  // Extension point for a key format this file shouldn't hold — e.g. an
  // org-internal key derivation, which has no business living in a shared
  // repo. A separate, gitignored script loaded after this one (see
  // aes.local.js.example for the shape) can call
  // window.AesTool.registerKeyFormat(value, {label, placeholder, decode})
  // before the page needs it; if that file isn't present, its <script> tag
  // just 404s harmlessly and the extra option never appears.
  const customKeyFormats = {};
  window.AesTool = window.AesTool || {};
  window.AesTool.registerKeyFormat = function (value, { label, placeholder, decode }) {
    customKeyFormats[value] = { placeholder, decode };
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    keyFormatSelect.appendChild(option);
  };

  function decodeKey(raw, format) {
    if (format === "hex") return hexToBytes(raw);
    if (format === "base64") return base64ToBytes(raw);
    if (format === "passphrase-sha256" || format === "passphrase-md5") {
      // Any-length passphrase, hashed into a fixed-length key — for systems
      // that derive their key this way instead of expecting the literal raw
      // bytes. SHA-256 always yields 32 bytes (AES-256); MD5 always yields
      // 16 bytes (AES-128) — MD5(passphrase) is a very common "quick"
      // pattern in Java backends (Cipher.getInstance("AES") defaults to
      // ECB, paired with MessageDigest.getInstance("MD5") for the key).
      if (typeof CryptoJS === "undefined") {
        throw new Error("This key format needs the crypto-js library, which failed to load.");
      }
      return wordArrayToBytes(format === "passphrase-md5" ? CryptoJS.MD5(raw) : CryptoJS.SHA256(raw));
    }
    if (customKeyFormats[format]) return customKeyFormats[format].decode(raw);
    return new TextEncoder().encode(raw);
  }

  const KEY_FORMAT_PLACEHOLDERS = {
    utf8: "Must be exactly 16, 24, or 32 characters (AES-128/192/256)",
    hex: "Must decode to 16, 24, or 32 bytes — 32/48/64 hex characters",
    base64: "Must decode to 16, 24, or 32 bytes",
    "passphrase-sha256": "Any length — hashed via SHA-256 into a 32-byte AES-256 key",
    "passphrase-md5": "Any length — hashed via MD5 into a 16-byte AES-128 key",
  };
  keyFormatSelect.addEventListener("change", () => {
    const custom = customKeyFormats[keyFormatSelect.value];
    keyInput.placeholder = custom ? custom.placeholder : (KEY_FORMAT_PLACEHOLDERS[keyFormatSelect.value] || "");
  });

  function encodeOutput(bytes, format) {
    return format === "hex" ? bytesToHex(bytes) : bytesToBase64(bytes);
  }

  function decodeInputCiphertext(raw, format) {
    return format === "hex" ? hexToBytes(raw) : base64ToBytes(raw);
  }

  function concatBytes(...parts) {
    const total = parts.reduce((sum, p) => sum + p.length, 0);
    const result = new Uint8Array(total);
    let offset = 0;
    parts.forEach((p) => {
      result.set(p, offset);
      offset += p.length;
    });
    return result;
  }

  function algorithmParams(mode, iv) {
    if (mode === "AES-CTR") return { name: "AES-CTR", counter: iv, length: 64 };
    return { name: mode, iv };
  }

  function validateKeyLength(keyBytes) {
    const validLengths = { 16: "AES-128", 24: "AES-192", 32: "AES-256" };
    if (!validLengths[keyBytes.length]) {
      throw new Error(
        `Key must decode to 16, 24, or 32 bytes for AES-128/192/256 (got ${keyBytes.length} byte${keyBytes.length === 1 ? "" : "s"}).`
      );
    }
  }

  function showError(message) {
    errorBox.textContent = message;
    errorBox.hidden = false;
    output.textContent = "";
    output.classList.add("empty");
    copyBtn.dataset.copyText = "";
  }

  function showOutput(text) {
    errorBox.hidden = true;
    output.textContent = text;
    output.classList.remove("empty");
    copyBtn.dataset.copyText = text;
  }

  async function importSubtleKey(keyBytes, mode, usage) {
    validateKeyLength(keyBytes);
    return crypto.subtle.importKey("raw", keyBytes, { name: mode }, false, [usage]);
  }

  // ── AES-ECB, via the vendored crypto-js (no IV; not in Web Crypto) ───────
  function bytesToWordArray(bytes) {
    return CryptoJS.lib.WordArray.create(bytes);
  }

  function wordArrayToBytes(wordArray) {
    const bytes = new Uint8Array(wordArray.sigBytes);
    for (let i = 0; i < wordArray.sigBytes; i += 1) {
      bytes[i] = (wordArray.words[i >>> 2] >>> (24 - (i % 4) * 8)) & 0xff;
    }
    return bytes;
  }

  function encryptEcb(keyBytes, plaintext, outputFormat) {
    validateKeyLength(keyBytes);
    const encrypted = CryptoJS.AES.encrypt(CryptoJS.enc.Utf8.parse(plaintext), bytesToWordArray(keyBytes), {
      mode: CryptoJS.mode.ECB,
      padding: CryptoJS.pad.Pkcs7,
    });
    return encodeOutput(wordArrayToBytes(encrypted.ciphertext), outputFormat);
  }

  function decryptEcb(keyBytes, raw, outputFormat) {
    validateKeyLength(keyBytes);
    const ciphertext = bytesToWordArray(decodeInputCiphertext(raw, outputFormat));
    const decrypted = CryptoJS.AES.decrypt({ ciphertext }, bytesToWordArray(keyBytes), {
      mode: CryptoJS.mode.ECB,
      padding: CryptoJS.pad.Pkcs7,
    });
    // crypto-js's own toString(Utf8) silently replaces invalid byte
    // sequences instead of raising — a wrong key can decrypt to garbage
    // bytes that still "succeed" as a mangled (or empty) string. Decode the
    // raw bytes ourselves with the same strict TextDecoder the CBC/CTR path
    // uses below, so a wrong key/corrupted ciphertext reliably throws here
    // too instead of returning silently-wrong output.
    return new TextDecoder("utf-8", { fatal: true }).decode(wordArrayToBytes(decrypted));
  }

  async function encrypt() {
    const mode = modeSelect.value;
    const outputFormat = outputFormatSelect.value;
    const plaintext = input.value;
    if (!plaintext) {
      showError("Nothing to encrypt — type some text above.");
      return;
    }

    if (mode === "AES-ECB") {
      if (typeof CryptoJS === "undefined") {
        showError("ECB mode needs the crypto-js library, which failed to load.");
        return;
      }
      try {
        const keyBytes = decodeKey(keyInput.value, keyFormatSelect.value);
        showOutput(encryptEcb(keyBytes, plaintext, outputFormat));
      } catch (err) {
        showError(`Encryption failed: ${err.message}`);
      }
      return;
    }

    let key;
    let iv;
    try {
      key = await importSubtleKey(decodeKey(keyInput.value, keyFormatSelect.value), mode, "encrypt");
      const ivLength = ivLengthFor(mode);
      if (ivInput.value.trim()) {
        iv = hexToBytes(ivInput.value);
        if (iv.length !== ivLength) {
          showError(`IV for ${mode} must be ${ivLength} bytes of hex (got ${iv.length}).`);
          return;
        }
      } else {
        iv = crypto.getRandomValues(new Uint8Array(ivLength));
      }
    } catch (err) {
      showError(err.message);
      return;
    }

    try {
      const ciphertext = await crypto.subtle.encrypt(
        algorithmParams(mode, iv), key, new TextEncoder().encode(plaintext)
      );
      // IV is embedded in the output only when it wasn't explicitly supplied —
      // an explicit IV means the caller is tracking it themselves and wants a
      // plain ciphertext back.
      const combined = ivInput.value.trim() ? new Uint8Array(ciphertext) : concatBytes(iv, new Uint8Array(ciphertext));
      showOutput(encodeOutput(combined, outputFormat));
    } catch (err) {
      showError(`Encryption failed: ${err.message}`);
    }
  }

  async function decrypt() {
    const mode = modeSelect.value;
    const outputFormat = outputFormatSelect.value;
    const raw = input.value.trim();
    if (!raw) {
      showError("Nothing to decrypt — paste some ciphertext above.");
      return;
    }

    if (mode === "AES-ECB") {
      if (typeof CryptoJS === "undefined") {
        showError("ECB mode needs the crypto-js library, which failed to load.");
        return;
      }
      try {
        const keyBytes = decodeKey(keyInput.value, keyFormatSelect.value);
        const text = decryptEcb(keyBytes, raw, outputFormat);
        showOutput(text);
      } catch {
        showError("Decryption failed — wrong key, wrong mode, or corrupted ciphertext.");
      }
      return;
    }

    let key;
    let iv;
    let ciphertextBytes;
    try {
      key = await importSubtleKey(decodeKey(keyInput.value, keyFormatSelect.value), mode, "decrypt");
      const ivLength = ivLengthFor(mode);
      const inputBytes = decodeInputCiphertext(raw, outputFormat);
      if (ivInput.value.trim()) {
        iv = hexToBytes(ivInput.value);
        if (iv.length !== ivLength) {
          showError(`IV for ${mode} must be ${ivLength} bytes of hex (got ${iv.length}).`);
          return;
        }
        ciphertextBytes = inputBytes;
      } else {
        if (inputBytes.length <= ivLength) {
          showError(`Input is too short to contain a ${ivLength}-byte IV plus ciphertext — did you mean to enter an IV separately?`);
          return;
        }
        iv = inputBytes.slice(0, ivLength);
        ciphertextBytes = inputBytes.slice(ivLength);
      }
    } catch (err) {
      showError(err.message);
      return;
    }

    try {
      const plaintextBytes = await crypto.subtle.decrypt(algorithmParams(mode, iv), key, ciphertextBytes);
      const text = new TextDecoder("utf-8", { fatal: true }).decode(plaintextBytes);
      showOutput(text);
    } catch {
      showError("Decryption failed — wrong key, wrong IV, wrong mode, or corrupted ciphertext.");
    }
  }

  encryptBtn.addEventListener("click", encrypt);
  decryptBtn.addEventListener("click", decrypt);
})();
