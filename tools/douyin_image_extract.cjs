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
fs.mkdirSync(path.join(outDir, 'live'), { recursive: true });

const core = require(corePath);
const UA = core.MOBILE_UA ||
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 Version/17.4 Mobile/15E148 Safari/604.1';

function extractShareUrl(text) {
  const m = String(text || '').match(/https?:\/\/(?:v\.)?douyin\.com\/[^\s]+|https?:\/\/www\.iesdouyin\.com\/[^\s]+/i);
  return m ? m[0].replace(/[，。,.!！?？;；]+$/, '') : String(text || '').trim();
}

function extractCanonicalId(url) {
  const m = String(url || '').match(/\/(?:video|note|slides|share\/video|share\/note|share\/slides)\/(\d{17,19})(?:[/?#]|$)/i);
  return m ? m[1] : '';
}

function canonicalKind(url) {
  const m = String(url || '').match(/\/(?:share\/)?(video|note|slides)\/(\d{17,19})(?:[/?#]|$)/i);
  return m ? m[1].toLowerCase() : '';
}

async function resolveCanonicalInput(raw) {
  let current = extractShareUrl(raw);
  if (!current) throw new Error('No Douyin URL found in input');
  if (extractCanonicalId(current)) return current;

  for (let i = 0; i < 10; i++) {
    const resp = await fetch(current, {
      method: 'GET',
      headers: {
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
      },
      redirect: 'manual'
    });

    const loc = resp.headers.get('location');
    if (loc && resp.status >= 300 && resp.status < 400) {
      current = new URL(loc, current).href;
      if (extractCanonicalId(current)) return current;
      continue;
    }

    if (resp.url && extractCanonicalId(resp.url)) return resp.url;
    const html = await resp.text();
    const exact = html.match(/https?:\\?\/\\?\/(?:www\.)?(?:douyin\.com|iesdouyin\.com)\\?\/(?:share\\?\/)?(?:video|note|slides)\\?\/(\d{17,19})/i);
    if (exact) {
      const id = exact[1];
      const whole = exact[0].replace(/\\\//g, '/');
      const kind = /slides/i.test(whole) ? 'slides' : (/note/i.test(whole) ? 'note' : 'video');
      return kind === 'slides'
        ? `https://www.iesdouyin.com/share/slides/${id}/`
        : `https://www.douyin.com/${kind}/${id}`;
    }
    break;
  }
  throw new Error('Unable to resolve Douyin short URL to canonical content URL');
}

function deepFindItem(node, wantedId) {
  if (!node || typeof node !== 'object') return null;
  if (!Array.isArray(node)) {
    const id = node.aweme_id ?? node.awemeId ?? node.item_id ?? node.itemId;
    const images = node.images ?? node.image_list ?? (node.image_post_info && (node.image_post_info.images || node.image_post_info.image_list));
    if (String(id || '') === String(wantedId) && Array.isArray(images) && images.length) return node;
  }
  if (Array.isArray(node)) {
    for (const v of node) {
      const hit = deepFindItem(v, wantedId);
      if (hit) return hit;
    }
  } else {
    for (const v of Object.values(node)) {
      const hit = deepFindItem(v, wantedId);
      if (hit) return hit;
    }
  }
  return null;
}

function urlsFrom(value) {
  if (!value) return [];
  if (typeof value === 'string') return value ? [value] : [];
  if (Array.isArray(value)) return value.flatMap(urlsFrom).filter(Boolean);
  if (typeof value === 'object') {
    if (Array.isArray(value.url_list)) return value.url_list.filter(x => typeof x === 'string' && x);
    if (Array.isArray(value.urlList)) return value.urlList.filter(x => typeof x === 'string' && x);
    if (typeof value.url === 'string') return [value.url];
  }
  return [];
}

function unique(arr) {
  return [...new Set(arr.filter(Boolean))];
}

function rankedStaticUrls(img) {
  const out = [];
  if (!img || typeof img !== 'object') return out;
  const add = v => out.push(...urlsFrom(v));
  add(img.watermark_free_download_url_list);
  add(img.origin_image);
  add(img.display_image);
  add(img.url_list);
  add(img.url);
  add(img.download_url);
  add(img.download_addr);
  add(img.download_url_list);
  add(img.owner_watermark_image);
  return unique(out).sort((a,b) => {
    const aw = /watermark|playwm|dy-water/i.test(a) ? 1 : 0;
    const bw = /watermark|playwm|dy-water/i.test(b) ? 1 : 0;
    if (aw !== bw) return aw - bw;
    const awebp = /\.webp(?:\?|$)/i.test(a) ? 1 : 0;
    const bwebp = /\.webp(?:\?|$)/i.test(b) ? 1 : 0;
    return awebp - bwebp;
  });
}

function liveUrls(img) {
  if (!img || typeof img !== 'object') return [];
  const video = img.video || {};
  const candidates = [
    video.play_addr,
    video.play_addr_h264,
    video.download_addr,
    img.live_url_list,
    img.motion_url_list,
    img.animated_url_list
  ];
  return unique(candidates.flatMap(urlsFrom)).map(u => u.replace(/playwm/g, 'play'));
}

function bestLiveVideoUrls(img) {
  if (!img || typeof img !== 'object') return [];
  const video = img.video || {};
  const bitRate = Array.isArray(video.bit_rate) ? video.bit_rate : [];
  const candidates = [
    video.play_addr_h264,
    video.play_addr,
    ...bitRate.map(x => x && x.play_addr),
    video.play_addr_lowbr,
    video.download_addr,
    img.live_url_list,
    img.motion_url_list,
    img.animated_url_list
  ];
  return unique(candidates.flatMap(urlsFrom)).map(u => u.replace(/playwm/g, 'play'));
}

async function fetchAwemeDetail(itemId) {
  const api = new URL('https://www.douyin.com/aweme/v1/web/aweme/detail/');
  api.searchParams.set('aweme_id', itemId);
  api.searchParams.set('aid', '6383');

  let last = null;
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const resp = await fetch(api, {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36',
          'Accept': 'application/json, text/plain, */*',
          'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
          'Origin': 'https://open.douyin.com',
          'Referer': 'https://open.douyin.com/'
        },
        redirect: 'follow'
      });
      const text = await resp.text();
      if (!resp.ok) throw new Error(`aweme detail HTTP ${resp.status}`);
      let obj;
      try { obj = JSON.parse(text); } catch { throw new Error('aweme detail returned non-JSON'); }
      const item = obj.aweme_detail || (obj.data && obj.data.aweme_detail);
      if (!item || String(item.aweme_id || item.awemeId || '') !== String(itemId)) {
        throw new Error('aweme detail missing target item');
      }
      return item;
    } catch (e) {
      last = e;
      if (attempt < 3) await new Promise(r => setTimeout(r, attempt * 500));
    }
  }
  throw last || new Error('aweme detail failed');
}

function payloadFromAwemeDetail(item, itemId) {
  const rawImages = (item.image_post_info && (item.image_post_info.images || item.image_post_info.image_list))
    || item.images || item.image_list || [];
  if (!Array.isArray(rawImages) || rawImages.length === 0) {
    throw new Error('aweme detail contains no image list');
  }

  const images = [];
  const live = [];
  for (let i = 0; i < rawImages.length; i++) {
    const img = rawImages[i] || {};
    const staticCandidates = rankedStaticUrls(img);
    if (staticCandidates.length) {
      images.push({
        index: i + 1,
        url: staticCandidates[0],
        fallback_urls: staticCandidates.slice(1),
        width: Number(img.width || img.origin_image?.width || img.display_image?.width || 0),
        height: Number(img.height || img.origin_image?.height || img.display_image?.height || 0),
        uri: img.uri || img.origin_image?.uri || '',
        clip_type: img.clip_type ?? null,
        live_photo_type: img.live_photo_type ?? null
      });
    }

    const motions = bestLiveVideoUrls(img);
    const isLive = img.live_photo_type === 1 || [3,4,5].includes(img.clip_type) || motions.length > 0;
    if (isLive && motions.length) {
      live.push({
        index: i + 1,
        url: motions[0],
        fallback_urls: motions.slice(1),
        clip_type: img.clip_type ?? null,
        live_photo_type: img.live_photo_type ?? null,
        duration: Number(img.video?.duration || 0),
        width: Number(img.video?.width || 0),
        height: Number(img.video?.height || 0)
      });
    }
  }

  return {
    success: true,
    type: 'image',
    title: item.desc || item.share_info?.share_title || item.share_info?.share_desc || '',
    author: item.author?.nickname || item.authorInfo?.nickname || '',
    item_id: String(item.aweme_id ?? item.awemeId ?? itemId),
    image_count: images.length,
    images,
    live_count: live.length,
    live,
    source: 'aweme-detail'
  };
}


async function fetchSlidesInfo(canonical, itemId) {
  const api = new URL('https://www.iesdouyin.com/web/api/v2/aweme/slidesinfo/');
  api.searchParams.set('aweme_ids', `[${itemId}]`);
  api.searchParams.set('request_source', '200');

  let last = null;
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const resp = await fetch(api, {
        headers: {
          'User-Agent': UA,
          'Referer': canonical,
          'Accept': 'application/json,text/plain,*/*',
          'Accept-Language': 'zh-CN,zh;q=0.9'
        },
        redirect: 'follow'
      });
      const text = await resp.text();
      if (!resp.ok) throw new Error(`slidesinfo HTTP ${resp.status}`);
      let obj;
      try { obj = JSON.parse(text); } catch { throw new Error('slidesinfo returned non-JSON'); }
      if (obj.status_code !== 0) throw new Error(`slidesinfo status_code=${obj.status_code}`);
      const item = deepFindItem(obj, itemId);
      if (!item) throw new Error('slidesinfo did not contain target item/images');

      const rawImages = (item.image_post_info && (item.image_post_info.images || item.image_post_info.image_list))
        || item.images || item.image_list || [];

      const images = [];
      const live = [];
      for (let i = 0; i < rawImages.length; i++) {
        const img = rawImages[i];
        const staticCandidates = rankedStaticUrls(img);
        if (staticCandidates.length) {
          images.push({
            index: i + 1,
            url: staticCandidates[0],
            fallback_urls: staticCandidates.slice(1),
            width: Number(img.width || img.origin_image?.width || img.display_image?.width || 0),
            height: Number(img.height || img.origin_image?.height || img.display_image?.height || 0),
            uri: img.uri || img.origin_image?.uri || '',
            clip_type: img.clip_type ?? null
          });
        }
        const motions = liveUrls(img);
        if (motions.length) {
          live.push({
            index: i + 1,
            url: motions[0],
            fallback_urls: motions.slice(1),
            clip_type: img.clip_type ?? null
          });
        }
      }

      if (!images.length && !live.length) throw new Error('slidesinfo target had no media URLs');

      return {
        success: true,
        type: 'image',
        title: item.desc || item.share_info?.share_title || '',
        author: item.authorInfo?.nickname || item.author?.nickname || '',
        item_id: String(item.aweme_id ?? item.awemeId ?? itemId),
        image_count: images.length,
        images,
        live_count: live.length,
        live,
        source: 'slidesinfo'
      };
    } catch (e) {
      last = e;
      if (attempt < 3) await new Promise(r => setTimeout(r, attempt * 500));
    }
  }
  throw last || new Error('slidesinfo failed');
}

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

async function fetchBinaryOne(url, referer) {
  const resp = await fetch(url, {
    headers: {
      'User-Agent': UA,
      'Referer': referer || 'https://www.douyin.com/',
      'Accept': '*/*',
      'Accept-Language': 'zh-CN,zh;q=0.9'
    },
    redirect: 'follow'
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const buf = Buffer.from(await resp.arrayBuffer());
  if (!buf.length) throw new Error('empty body');
  return { bytes: buf, contentType: resp.headers.get('content-type') || '', finalUrl: resp.url || url };
}

async function fetchBinary(primary, fallbacks, referer) {
  const urls = unique([primary, ...(fallbacks || [])]);
  let last = null;
  for (const u of urls) {
    for (const ref of [referer, 'https://www.douyin.com/', '']) {
      try { return await fetchBinaryOne(u, ref); } catch (e) { last = e; }
    }
  }
  throw last || new Error('download failed');
}

(async () => {
  const report = {
    input: rawInput,
    upstream: [
      'Hartcher1996/DyExtract@26e737098b01350a4f58a04e04a8878726db39ee',
      'Furinelle/hanabi slidesinfo strategy'
    ],
    errors: []
  };

  let canonicalInput;
  try {
    canonicalInput = await resolveCanonicalInput(rawInput);
    report.canonical_input = canonicalInput;
    report.resolved_item_id = extractCanonicalId(canonicalInput);
    report.resolved_kind = canonicalKind(canonicalInput);
    console.log('resolved canonical:', canonicalInput);
  } catch (e) {
    report.errors.push(`resolve: ${e.message || String(e)}`);
    fs.writeFileSync(path.join(outDir, 'result.json'), JSON.stringify(report, null, 2));
    process.exit(3);
  }

  let payload;
  let detailError = null;
  try {
    const detail = await fetchAwemeDetail(report.resolved_item_id);
    payload = payloadFromAwemeDetail(detail, report.resolved_item_id);
    report.detail_source = 'aweme-detail';
  } catch (e) {
    detailError = e;
    console.warn('aweme detail failed, falling back:', e.message || String(e));
  }

  if (!payload) {
    try {
      if (report.resolved_kind === 'slides') {
        payload = await fetchSlidesInfo(canonicalInput, report.resolved_item_id);
        report.detail_source = 'slidesinfo-fallback';
      } else {
        const parsed = await core.buildParseResponse(canonicalInput);
        payload = parsed && parsed.payload ? parsed.payload : {};
        report.detail_source = 'dyextract-fallback';
      }
    } catch (e) {
      report.errors.push(`parse: ${e.message || String(e)}`);
      if (detailError) report.errors.push(`aweme-detail: ${detailError.message || String(detailError)}`);
      fs.writeFileSync(path.join(outDir, 'result.json'), JSON.stringify(report, null, 2));
      console.error(JSON.stringify(report, null, 2));
      process.exit(4);
    }
  }

  report.payload = payload;
  report.type = payload.type || '';
  report.item_id = payload.item_id || report.resolved_item_id || '';
  report.title = payload.title || '';
  report.author = payload.author || '';

  if (payload.type !== 'image' || !Array.isArray(payload.images) || payload.images.length === 0) {
    report.errors.push(`not an image post: type=${payload.type || 'unknown'}`);
    fs.writeFileSync(path.join(outDir, 'result.json'), JSON.stringify(report, null, 2));
    process.exit(5);
  }

  report.candidate_count = payload.images.length;
  report.live_candidate_count = Array.isArray(payload.live) ? payload.live.length : 0;
  report.downloaded = [];
  report.live_downloaded = [];

  for (let i = 0; i < payload.images.length; i++) {
    const entry = payload.images[i];
    const url = typeof entry === 'string' ? entry : (entry && entry.url) || '';
    try {
      const got = await fetchBinary(url, entry && entry.fallback_urls, canonicalInput);
      const ext = extFrom(got.contentType, got.finalUrl, got.bytes);
      const name = String(i + 1).padStart(2, '0') + ext;
      const rel = path.posix.join('images', name);
      fs.writeFileSync(path.join(outDir, rel), got.bytes);
      report.downloaded.push({
        index: entry.index || i + 1,
        filename: rel,
        bytes: got.bytes.length,
        content_type: got.contentType,
        width: entry.width || 0,
        height: entry.height || 0,
        uri: entry.uri || '',
        clip_type: entry.clip_type ?? null,
        source_url: url,
        final_url: got.finalUrl
      });
      console.log(`image ${i + 1}/${payload.images.length}: ${name}`);
    } catch (e) {
      report.errors.push(`image ${i + 1}: ${e.message || String(e)}`);
    }
  }

  const lives = Array.isArray(payload.live) ? payload.live : [];
  for (let i = 0; i < lives.length; i++) {
    const entry = lives[i];
    try {
      const got = await fetchBinary(entry.url, entry.fallback_urls, canonicalInput);
      const ext = extFrom(got.contentType, got.finalUrl, got.bytes);
      const name = String(entry.index || i + 1).padStart(2, '0') + (ext === '.bin' ? '.mp4' : ext);
      const rel = path.posix.join('live', name);
      fs.writeFileSync(path.join(outDir, rel), got.bytes);
      report.live_downloaded.push({
        index: entry.index || i + 1,
        filename: rel,
        bytes: got.bytes.length,
        content_type: got.contentType,
        clip_type: entry.clip_type ?? null,
        source_url: entry.url,
        final_url: got.finalUrl
      });
      console.log(`live ${i + 1}/${lives.length}: ${name}`);
    } catch (e) {
      report.errors.push(`live ${i + 1}: ${e.message || String(e)}`);
    }
  }

  report.downloaded_count = report.downloaded.length;
  report.live_downloaded_count = report.live_downloaded.length;
  fs.writeFileSync(path.join(outDir, 'result.json'), JSON.stringify(report, null, 2));

  console.log(JSON.stringify({
    item_id: report.item_id,
    title: report.title,
    author: report.author,
    candidate_count: report.candidate_count,
    downloaded_count: report.downloaded_count,
    live_candidate_count: report.live_candidate_count,
    live_downloaded_count: report.live_downloaded_count,
    errors: report.errors
  }, null, 2));

  if (report.downloaded_count !== report.candidate_count ||
      report.live_downloaded_count !== report.live_candidate_count ||
      report.errors.length) {
    process.exit(6);
  }
})().catch(err => {
  console.error(err);
  process.exit(9);
});
