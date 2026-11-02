// libsodium-compatibele "sealed box" (crypto_box_seal) bovenop tweetnacl.
// Nodig om GitHub Actions-secrets vanuit de browser te versleutelen.
// nonce = BLAKE2b-192(ephemeral_pk || recipient_pk)
(function (root) {
  const IV = new Uint32Array([
    0xf3bcc908, 0x6a09e667, 0x84caa73b, 0xbb67ae85, 0xfe94f82b, 0x3c6ef372, 0x5f1d36f1, 0xa54ff53a,
    0xade682d1, 0x510e527f, 0x2b3e6c1f, 0x9b05688c, 0xfb41bd6b, 0x1f83d9ab, 0x137e2179, 0x5be0cd19,
  ]);
  const SIGMA = [
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 14, 10, 4, 8, 9, 15, 13, 6, 1, 12, 0, 2, 11, 7, 5, 3,
    11, 8, 12, 0, 5, 2, 15, 13, 10, 14, 3, 6, 7, 1, 9, 4, 7, 9, 3, 1, 13, 12, 11, 14, 2, 6, 5, 10, 4, 0, 15, 8,
    9, 0, 5, 7, 2, 4, 10, 15, 14, 1, 11, 12, 6, 8, 3, 13, 2, 12, 6, 10, 0, 11, 8, 3, 4, 13, 7, 5, 15, 14, 1, 9,
    12, 5, 1, 15, 14, 13, 4, 10, 0, 7, 6, 3, 9, 2, 8, 11, 13, 11, 7, 14, 12, 1, 3, 9, 5, 0, 15, 4, 8, 6, 2, 10,
    6, 15, 14, 9, 11, 3, 0, 8, 12, 2, 13, 7, 1, 4, 10, 5, 10, 2, 8, 4, 7, 6, 1, 5, 15, 11, 9, 14, 3, 12, 13, 0,
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 14, 10, 4, 8, 9, 15, 13, 6, 1, 12, 0, 2, 11, 7, 5, 3,
  ].map(x => x * 2);

  function add64(v, a, b) {            // v[a] += v[b]
    const lo = v[a] + v[b], hi = v[a + 1] + v[b + 1] + (lo >= 0x100000000 ? 1 : 0);
    v[a] = lo >>> 0; v[a + 1] = hi >>> 0;
  }
  function add64c(v, a, lo0, hi0) {
    const lo = v[a] + lo0, hi = v[a + 1] + hi0 + (lo >= 0x100000000 ? 1 : 0);
    v[a] = lo >>> 0; v[a + 1] = hi >>> 0;
  }
  function xorRot(v, a, b, n) {        // v[a] = rotr64(v[a] ^ v[b], n)
    let lo = v[a] ^ v[b], hi = v[a + 1] ^ v[b + 1];
    if (n === 32) { v[a] = hi; v[a + 1] = lo; return; }
    if (n > 32) { const t = lo; lo = hi; hi = t; n -= 32; }
    v[a] = ((lo >>> n) | (hi << (32 - n))) >>> 0;
    v[a + 1] = ((hi >>> n) | (lo << (32 - n))) >>> 0;
  }
  function G(v, m, a, b, c, d, x, y) {
    add64(v, a, b); add64c(v, a, m[x], m[x + 1]); xorRot(v, d, a, 32);
    add64(v, c, d); xorRot(v, b, c, 24);
    add64(v, a, b); add64c(v, a, m[y], m[y + 1]); xorRot(v, d, a, 16);
    add64(v, c, d); xorRot(v, b, c, 63);
  }
  function compress(h, block, t, last) {
    const v = new Uint32Array(32), m = new Uint32Array(32);
    v.set(h); v.set(IV, 16);
    v[24] ^= t; v[25] ^= t / 0x100000000;
    if (last) { v[28] = ~v[28]; v[29] = ~v[29]; }
    for (let i = 0; i < 32; i++) m[i] = block[i * 4] | (block[i * 4 + 1] << 8) | (block[i * 4 + 2] << 16) | (block[i * 4 + 3] << 24);
    for (let r = 0; r < 12; r++) {
      const s = SIGMA.slice(r * 16, r * 16 + 16);
      G(v, m, 0, 8, 16, 24, s[0], s[1]); G(v, m, 2, 10, 18, 26, s[2], s[3]);
      G(v, m, 4, 12, 20, 28, s[4], s[5]); G(v, m, 6, 14, 22, 30, s[6], s[7]);
      G(v, m, 0, 10, 20, 30, s[8], s[9]); G(v, m, 2, 12, 22, 24, s[10], s[11]);
      G(v, m, 4, 14, 16, 26, s[12], s[13]); G(v, m, 6, 8, 18, 28, s[14], s[15]);
    }
    for (let i = 0; i < 16; i++) h[i] ^= v[i] ^ v[i + 16];
  }
  function blake2b(input, outlen) {
    const h = new Uint32Array(IV);
    h[0] ^= 0x01010000 ^ outlen;
    const n = Math.max(1, Math.ceil(input.length / 128));
    for (let i = 0; i < n; i++) {
      const block = new Uint8Array(128);
      block.set(input.subarray(i * 128, i * 128 + 128));
      compress(h, block, Math.min((i + 1) * 128, input.length), i === n - 1);
    }
    const out = new Uint8Array(outlen);
    for (let i = 0; i < outlen; i++) out[i] = h[i >> 2] >>> (8 * (i & 3));
    return out;
  }

  function seal(message, recipientPk, nacl) {
    const eph = nacl.box.keyPair();
    const both = new Uint8Array(64); both.set(eph.publicKey); both.set(recipientPk, 32);
    const nonce = blake2b(both, 24);
    const boxed = nacl.box(message, nonce, recipientPk, eph.secretKey);
    const out = new Uint8Array(32 + boxed.length); out.set(eph.publicKey); out.set(boxed, 32);
    return out;
  }

  const api = { blake2b, seal };
  if (typeof module !== "undefined") module.exports = api; else root.SealedBox = api;
})(this);
