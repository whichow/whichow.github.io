#!/usr/bin/env node
import { createCipheriv, createDecipheriv, createHash, randomBytes } from "node:crypto";
import { spawnSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const BASE = "https://dy.kukutool.com";
const UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36";
const RESPONSE_KEY = Buffer.from("12345678901234567890123456789013", "utf8");
const STANDARD = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
const CUSTOM = "ZYXABCDEFGHIJKLMNOPQRSTUVWzyxabcdefghijklmnopqrstuvw9876543210-_";

function cookieString(current, res) {
  const jar = new Map();
  for (const part of String(current || "").split(";").map(x => x.trim()).filter(Boolean)) {
    const i = part.indexOf("=");
    if (i > 0) jar.set(part.slice(0, i), part.slice(i + 1));
  }
  for (const raw of (res.headers.getSetCookie?.() || [])) {
    const pair = raw.split(";")[0];
    const i = pair.indexOf("=");
    if (i > 0) jar.set(pair.slice(0, i), pair.slice(i + 1));
  }
  return [...jar.entries()].map(([k,v]) => `${k}=${v}`).join("; ");
}

async function jsonFetch(url, options={}) {
  const res = await fetch(url, options);
  const text = await res.text();
  let data;
  try { data = JSON.parse(text); }
  catch { throw new Error(`non-json from ${url}: ${text.slice(0,200)}`); }
  return {res, data};
}

async function sessionCookie() {
  const res = await fetch(`${BASE}/xiaohongshu`, {headers:{"user-agent":UA}});
  return cookieString("", res);
}

async function discoverAuthProfiles() {
  const page = await fetch(`${BASE}/xiaohongshu`, {headers:{"user-agent":UA}});
  const html = await page.text();
  const scriptUrls = [...html.matchAll(/<script[^>]+src=["']([^"']+)["']/g)]
    .map(m => new URL(m[1], BASE).href);
  const suffixes = new Set();
  for (const url of scriptUrls) {
    try {
      const js = await (await fetch(url, {headers:{"user-agent":UA, referer:`${BASE}/xiaohongshu`}})).text();
      for (const m of js.matchAll(/auth-([a-zA-Z0-9_-]{4,32})/g)) suffixes.add(m[1]);
    } catch {}
  }
  return [...suffixes];
}

async function authorize(sourceUrl, cookie) {
  const payload = {
    requestURL:sourceUrl,
    pagePath:"/xiaohongshu",
    mode:"single"
  };
  const suffixes = ["25e532", ...(await discoverAuthProfiles())];
  const tried = [];
  for (const suffix of [...new Set(suffixes)]) {
    const route = `${BASE}/api/auth-${suffix}`;
    try {
      const {res, data} = await jsonFetch(route, {
        method:"POST",
        headers:{
          "content-type":"application/json",
          "user-agent":UA,
          "referer":`${BASE}/xiaohongshu`,
          "origin":BASE,
          "cookie":cookie
        },
        body:JSON.stringify(payload)
      });
      tried.push({suffix,status:res.status});
      const keyField = `k_${suffix}`;
      const seedField = `s_${suffix}`;
      if (res.ok && data?.[keyField] && data?.[seedField]) {
        return {
          key:data[keyField],
          seed:data[seedField],
          suffix,
          cookie:cookieString(cookie,res),
          tried
        };
      }
    } catch (e) {
      tried.push({suffix,error:String(e?.message || e)});
    }
  }
  throw new Error("auth discovery failed: "+JSON.stringify(tried));
}

function encryptPayload(params, auth) {
  const iv = randomBytes(12);
  const key = createHash("sha256").update(`${auth.key}:${auth.seed}`).digest();
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  const encrypted = Buffer.concat([
    cipher.update(JSON.stringify(params), "utf8"),
    cipher.final(),
    cipher.getAuthTag()
  ]);
  const out = {version:3};
  out[`k_${auth.suffix}`] = auth.key;
  out[`p_${auth.suffix}`] = encrypted.toString("base64");
  out[`i_${auth.suffix}`] = iv.toString("base64");
  out[`r_${auth.suffix}`] = 1;
  return out;
}

function customB64(value) {
  return [...value].map(ch => {
    const i = CUSTOM.indexOf(ch);
    return i < 0 ? ch : STANDARD[i];
  }).join("");
}

function reverseBlocks(value, n=8) {
  let out="";
  for (let i=0;i<value.length;i+=n) out += value.slice(i,i+n).split("").reverse().join("");
  return out;
}

function xorText(value, key=0x5a) {
  let out="";
  for (let i=0;i<value.length;i++) out += String.fromCharCode(value.charCodeAt(i)^key);
  return out;
}

function decryptResult(data, iv) {
  data = customB64(reverseBlocks(xorText(data)));
  iv = customB64(reverseBlocks(xorText(iv)));
  const decipher = createDecipheriv("aes-256-cbc", RESPONSE_KEY, Buffer.from(iv,"base64"));
  const plain = Buffer.concat([
    decipher.update(Buffer.from(data,"base64")),
    decipher.final()
  ]).toString("utf8");
  return JSON.parse(plain);
}

async function parseXhs(sourceUrl) {
  const cookie = await sessionCookie();
  const auth = await authorize(sourceUrl, cookie);
  const body = encryptPayload({
    requestURL:sourceUrl,
    captchaKey:"",
    captchaInput:"",
    totalSuccessCount:"0",
    successCount:"0",
    firstSuccessDate:"",
    pagePath:"/xiaohongshu",
    isMobile:"false",
    geoipIp:""
  }, auth);

  const {res, data} = await jsonFetch(`${BASE}/api/parse`, {
    method:"POST",
    headers:{
      "content-type":"application/json",
      "user-agent":UA,
      "referer":`${BASE}/xiaohongshu`,
      "origin":BASE,
      "cookie":auth.cookie
    },
    body:JSON.stringify(body)
  });
  if (!res.ok) throw new Error(`parse http ${res.status}`);
  if (data.status !== 0) throw new Error(data.message || "parse failed");
  return data.encrypt ? decryptResult(data.data, data.iv) : data.data;
}

function chooseVideo(data) {
  const v = data?.videos?.[0];
  if (!v) throw new Error("no video in parser result");
  if (typeof v === "string") return v;
  const normal = v.video_fullinfo?.find(x => String(x?.type || "").includes("正常")) || v.video_fullinfo?.[0];
  return normal?.url || v.url;
}

function run(cmd,args) {
  const r = spawnSync(cmd,args,{stdio:"inherit"});
  if (r.status !== 0) throw new Error(`${cmd} failed with exit ${r.status}`);
}

async function main() {
  const sourceUrl = process.argv[2];
  const outDir = process.argv[3] || "output";
  if (!sourceUrl) throw new Error("missing source url");
  mkdirSync(outDir,{recursive:true});
  const data = await parseXhs(sourceUrl);
  const videoUrl = chooseVideo(data);
  const out = resolve(outDir,"video.mp4");
  run("ffmpeg",["-y","-loglevel","warning","-i",videoUrl,"-c","copy",out]);
  writeFileSync(resolve(outDir,"kukutool_result.json"), JSON.stringify({
    title:data?.title || "",
    video_url:videoUrl,
    parser:"kukutool",
    raw_summary:{
      has_videos:Array.isArray(data?.videos) && data.videos.length>0,
      author:data?.author || data?.nickname || ""
    }
  },null,2));
  console.log(JSON.stringify({title:data?.title || "",video_url:videoUrl,output:out},null,2));
}

main().catch(err => { console.error(err?.stack || String(err)); process.exit(1); });
