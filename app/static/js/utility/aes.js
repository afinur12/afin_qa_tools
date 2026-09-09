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
  const copyBtn = document.getElementById("aes-copy");
  const encryptBtn = document.getElementById("aes-encrypt");
  const decryptBtn = document.getElementById("aes-decrypt");

  if (!window.crypto || !window.crypto.subtle) {
    unsupportedBox.hidden = false;
    encryptBtn.disabled = true;
    decryptBtn.disabled = true;
    return;
  }

  // GCM's recommended nonce is 96 bits; CBC/CTR need a full 128-bit (16-byte)
  // block-size IV.
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

  function decodeKey(raw, format) {
    if (format === "hex") return hexToBytes(raw);
    if (format === "base64") return base64ToBytes(raw);
    return new TextEncoder().encode(raw);
  }

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

  async function importKey(keyBytes, mode, usage) {
    const validLengths = { 16: "AES-128", 24: "AES-192", 32: "AES-256" };
    if (!validLengths[keyBytes.length]) {
      throw new Error(
        `Key must decode to 16, 24, or 32 bytes for AES-128/192/256 (got ${keyBytes.length} byte${keyBytes.length === 1 ? "" : "s"}).`
      );
    }
    return crypto.subtle.importKey("raw", keyBytes, { name: mode }, false, [usage]);
  }

  async function encrypt() {
    const mode = modeSelect.value;
    const outputFormat = outputFormatSelect.value;
    const plaintext = input.value;
    if (!plaintext) {
      showError("Nothing to encrypt — type some text above.");
      return;
    }

    let key;
    let iv;
    try {
      key = await importKey(decodeKey(keyInput.value, keyFormatSelect.value), mode, "encrypt");
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

    let key;
    let iv;
    let ciphertextBytes;
    try {
      key = await importKey(decodeKey(keyInput.value, keyFormatSelect.value), mode, "decrypt");
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
    } catch (err) {
      showError("Decryption failed — wrong key, wrong IV, wrong mode, or corrupted ciphertext.");
    }
  }

  encryptBtn.addEventListener("click", encrypt);
  decryptBtn.addEventListener("click", decrypt);
})();
