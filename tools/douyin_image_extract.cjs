#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');

const rawInput = process.argv[2] || '';
const outDir = process.argv[3] || 'output';
const corePath = process.env.DYEXTRACT_CORE || '/tmp/DyExtract/lib/core.js';

if (!rawInput.trim()) {
  console.error('Missing Douyin URL/share text');
  process.exit(2);
}

fs.rmSync(outDir, { recursive: true, force: true });
fs.mkdirSync(path.join(outDir, 'images'), { recursive: true });

const core = require(corePath);

const UA = core.MOBILE_UA ||
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 Version/17.4 Mobile/15E148 Safari/604.1';

function extFrom(contentType, url, bytes) {
  const ct = String(contentType || '').toLowerCase();
  if (ct.includes('jpeg') || ct.includes('jpg')) return '.jpg';
  if (ct.includes('png')) return '.png';
  if (ct.includes('webp')) return '.webp';
  if (ct.includes('gif')) return '.gif';
  if (ct.includes('mp4') || ct.includes('video/')) return '.mp4';

  const lower = String(url || '').toLowerCase().split('?')[0];
  for (const ext of ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.mp4']) {
    if (lower.endsWith(ext)) return ext === '.jpeg' ? '.jpg' : ext;
  }

  if (bytes && bytes.length >= 12) {
    if (bytes[0] === 0xff && bytes[1] === 0xd8) return '.jpg';
    if (bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47) return '.png';
    if (bytes.toString('ascii', 0, 4) === 'RIFF' && bytes.toString('ascii', 8, 12) === 'WEBP') return '.webp';
    if (bytes.toString('ascii', 4, 8) === 'ftyp') return '.mp4';
  }
  return '.bin';
}

async function fetchBinary(url) {
  const headerSets = [
    {
      'User-Agent': UA,
      'Referer': 'https://www.douyin.com/',
      'Accept': 'image/avif,image/webp,image/apng,image/*,video/mp4,*/*;q=0.8',
      'Accept-Language': 'zh-CN,zh;q=0.9'
    },
    {
      'User-Agent': UA,
      'Accept': '*/*'
    },
    {
      'User-Agent': UA,
      'Referer': 'https://www.iesdouyin.com/',
      'Accept': '*/*'
    }
  ];

  let lastErr = null;
  for (const headers of headerSets) {
    try {
      const resp = await fetch(url, { headers, redirect: 'follow' });
      if (!resp.ok) {
        lastErr = new Error(`HTTP ${resp.status}`);
        continue;
      }
      const ab = await resp.arrayBuffer();
      const buf = Buffer.from(ab);
      if (!buf.length) {
        lastErr = new Error('empty body');
        continue;
      }
      return {
        bytes: buf,
        contentType: resp.headers.get('content-type') || '',
        finalUrl: resp.url || url
      };
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr || new Error('download failed');
}

(async () => {
  const report = {
    input: rawInput,
    upstream: 'Hartcher1996/DyExtract@26e737098b01350a4f58a04e04a8878726db39ee',
    errors: []
  };

  let parsed;
  try {
    parsed = await core.buildParseResponse(rawInput);
  } catch (e) {
    report.errors.push(`parse: ${e && e.message ? e.message : String(e)}`);
    fs.writeFileSync(path.join(outDir, 'result.json'), JSON.stringify(report, null, 2));
    console.error(JSON.stringify(report, null, 2));
    process.exit(3);
  }

  const payload = parsed && parsed.payload ? parsed.payload : {};
  report.payload = payload;
  report.type = payload.type || '';
  report.item_id = payload.item_id || '';
  report.title = payload.title || '';
  report.author = payload.author || '';

  if (payload.type !== 'image' || !Array.isArray(payload.images) || payload.images.length === 0) {
    report.errors.push(`not an image post: type=${payload.type || 'unknown'}`);
    fs.writeFileSync(path.join(outDir, 'result.json'), JSON.stringify(report, null, 2));
    console.error(JSON.stringify(report, null, 2));
    process.exit(4);
  }

  report.candidate_count = payload.images.length;
  report.downloaded = [];

  for (let i = 0; i < payload.images.length; i++) {
    const entry = payload.images[i];
    const url = typeof entry === 'string' ? entry : (entry && entry.url) || '';
    if (!url) {
      report.errors.push(`resource ${i + 1}: missing URL`);
      continue;
    }

    try {
      const got = await fetchBinary(url);
      const ext = extFrom(got.contentType, got.finalUrl, got.bytes);
      const name = String(i + 1).padStart(2, '0') + ext;
      const rel = path.posix.join('images', name);
      fs.writeFileSync(path.join(outDir, rel), got.bytes);
      report.downloaded.push({
        index: i + 1,
        filename: rel,
        bytes: got.bytes.length,
        content_type: got.contentType,
        width: typeof entry === 'object' && entry ? entry.width || 0 : 0,
        height: typeof entry === 'object' && entry ? entry.height || 0 : 0,
        uri: typeof entry === 'object' && entry ? entry.uri || '' : '',
        source_url: url,
        final_url: got.finalUrl
      });
      console.log(`downloaded ${i + 1}/${payload.images.length}: ${name} (${got.bytes.length} bytes)`);
    } catch (e) {
      report.errors.push(`resource ${i + 1}: ${e && e.message ? e.message : String(e)}`);
    }
  }

  report.downloaded_count = report.downloaded.length;
  fs.writeFileSync(path.join(outDir, 'result.json'), JSON.stringify(report, null, 2));

  console.log(JSON.stringify({
    item_id: report.item_id,
    title: report.title,
    author: report.author,
    candidate_count: report.candidate_count,
    downloaded_count: report.downloaded_count,
    errors: report.errors
  }, null, 2));

  if (report.downloaded_count !== report.candidate_count || report.errors.length) {
    process.exit(5);
  }
})().catch(err => {
  console.error(err);
  process.exit(9);
});
