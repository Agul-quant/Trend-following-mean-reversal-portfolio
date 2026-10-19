#!/usr/bin/env node
'use strict';
// Render the exact completed standalone HTML; never load market data or refit.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const escape = x => String(x).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function args(argv) {
  let reports = path.resolve(__dirname, '..', 'final_reports'); let screenshots = null;
  for (let i=0;i<argv.length;i++) {
    if (argv[i] === '--reports' && argv[i+1]) reports=path.resolve(argv[++i]);
    else if (argv[i] === '--screenshots' && argv[i+1]) screenshots=path.resolve(argv[++i]);
    else if (argv[i] === '--help') { console.log('node scripts/render_final_reports.cjs [--reports DIRECTORY] [--screenshots PRIVATE_QA_DIRECTORY]'); process.exit(0); }
    else throw new Error('Unknown or incomplete option');
  }
  return {reports,screenshots};
}
async function main() {
  const {reports,screenshots}=args(process.argv.slice(2));
  const m=JSON.parse(fs.readFileSync(path.join(reports,'manifest.json'),'utf8'));
  if (!Array.isArray(m.stages) || m.stages.length!==3 || m.aggregate_only!==true) throw Error('Expected complete aggregate-only three-stage manifest');
  for (const [name, sha] of Object.entries(m.files)) {
    const target=path.resolve(reports,name);
    if (!target.startsWith(reports+path.sep) || digest(fs.readFileSync(target))!==sha) throw Error('Source report hash mismatch');
  }
  if (fs.existsSync(path.join(reports,'render_manifest.json'))) throw Error('Rendering already complete; choose a new report directory');
  if (screenshots) fs.mkdirSync(screenshots,{recursive:true});
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE_PATH || chromium.executablePath()});
  const rendered=[];
  try {
    for (const stage of m.stages) {
      const htmlPath=path.resolve(reports,stage.html); const pdfPath=htmlPath.replace(/\.html$/,'.pdf');
      if (!htmlPath.startsWith(reports+path.sep) || pdfPath===htmlPath || fs.existsSync(pdfPath)) throw Error('Invalid or already rendered target');
      const context=await browser.newContext({viewport:{width:1280,height:950},deviceScaleFactor:1});
      const page=await context.newPage(); const errors=[]; const remote=[];
      page.on('pageerror',e=>errors.push(e.message));
      await page.route('**/*', route => {
        const url=route.request().url();
        if (/^(?:file|data|about):/.test(url)) return route.continue();
        remote.push(url.split('?')[0]); return route.abort();
      });
      await page.goto(pathToFileURL(htmlPath).href,{waitUntil:'load'});
      await page.evaluate(()=>document.fonts.ready);
      const audit=await page.evaluate(()=>({
        title:document.title,
        brokenImages:[...document.images].filter(im=>!im.complete || im.naturalWidth===0).length,
        invalidAnchors:[...document.querySelectorAll('a[href^="#"]')].filter(a=>!document.getElementById(a.hash.slice(1))).map(a=>a.hash),
        scripts:document.scripts.length,
        desktopOverflow:document.documentElement.scrollWidth>window.innerWidth+1,
        numericHeaders:[...document.querySelectorAll('th.num')].length,
        numericHeaderAlignment:[...document.querySelectorAll('th.num')].every(e=>getComputedStyle(e).textAlign==='right'),
        headings:[...document.querySelectorAll('h1,h2')].map(h=>h.textContent)
      }));
      if (errors.length || remote.length || audit.brokenImages || audit.invalidAnchors.length || audit.scripts || audit.desktopOverflow || !audit.numericHeaderAlignment) throw Error('Offline HTML checks failed: '+JSON.stringify({errors,remote,audit}));
      if (screenshots) {
        await page.screenshot({path:path.join(screenshots,stage.stage+'_desktop.png')});
        await page.setViewportSize({width:390,height:844});
        await page.screenshot({path:path.join(screenshots,stage.stage+'_mobile.png')});
        audit.mobileOverflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+1);
        await page.setViewportSize({width:1280,height:950});
      }
      await page.emulateMedia({media:'print'});
      const footer='<div style="width:100%;text-align:center;font-family:Arial,sans-serif;font-size:8px;color:#666">'+escape(stage.stage.replaceAll('_',' '))+' · <span class="pageNumber"></span> / <span class="totalPages"></span></div>';
      await page.pdf({path:pdfPath,preferCSSPageSize:true,printBackground:true,displayHeaderFooter:true,headerTemplate:'<div></div>',footerTemplate:footer,tagged:true,outline:true});
      rendered.push({stage:stage.stage,html:stage.html,html_sha256:digest(fs.readFileSync(htmlPath)),pdf:path.relative(reports,pdfPath).split(path.sep).join('/'),pdf_sha256:digest(fs.readFileSync(pdfPath)),offline_browser_checks:audit});
      await context.close();
    }
    const receipt={schema:'same_html_pdf_rendering_v1',same_HTML_source:true,runtime:'Playwright '+require('playwright/package.json').version,browser:browser.version(),external_network_requests:0,raw_market_or_daily_arrays:false,reports:rendered};
    fs.writeFileSync(path.join(reports,'render_manifest.json'),JSON.stringify(receipt,null,2)+'\n');
    console.log(JSON.stringify({rendered:rendered.map(x=>x.pdf),networkRequests:0}));
  } finally { await browser.close(); }
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
