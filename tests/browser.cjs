const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs=require('fs'); const path=require('path');
const root=path.resolve(__dirname,'..');
const assert=(v,m)=>{if(!v)throw Error(m)};
(async()=>{
 const browser=await chromium.launch({headless:true});
 const errors=[];const results=[];
 fs.mkdirSync(path.join(root,'screenshots'),{recursive:true});
 for(const [project,port] of [['quote',8111],['invoice',8112],['support',8113],['booking',8114]]){
  const context=await browser.newContext({viewport:{width:1440,height:1000}});const page=await context.newPage();
  page.on('pageerror',e=>errors.push(project+': '+e.message));
  await page.goto('http://127.0.0.1:'+port);await page.locator('#login').waitFor();
  const password=fs.readFileSync(path.join(root,'data',project+'-demo','FIRST-LOGIN.txt'),'utf8').split(/\r?\n/)[1];
  await page.locator('#f-password').fill(password);await page.locator('#login button').click();await page.locator('#create').waitFor();
  await page.screenshot({path:path.join(root,'screenshots',project+'-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),project+' mobile overflow');
  await page.screenshot({path:path.join(root,'screenshots',project+'-mobile.png'),fullPage:true});
  await page.setViewportSize({width:1440,height:1000});
  if(project==='quote'){
   await page.locator('#create').click();await page.locator('#f-customer').fill('DEMO QA Buyer');await page.locator('#f-email').fill('qa@example.com');
   await page.locator('#f-lines').fill('LAMP-01,2\nWIRE-10,1');await page.locator('#create-form [type=submit]').click();
   await page.locator('[data-action=approve]').waitFor();await page.locator('[data-action=approve]').click();await page.locator('#modal').waitFor({state:'hidden'});
   const row=page.locator('tr').filter({hasText:'DEMO QA Buyer'}).first();await row.locator('[data-open]').click();await page.locator('#print').waitFor();
   assert((await page.locator('.total').textContent()).includes('112.30'),'quote total incorrect');
   await page.screenshot({path:path.join(root,'screenshots','quote-document.png'),fullPage:true});
  }
  if(project==='invoice'){
   const row=page.locator('tr').filter({hasText:'Paper Co'});await row.locator('[data-open]').click();
   await page.locator('#f-total').fill('120');await page.locator('#invoice-form [type=submit]').click();await page.locator('[data-action=approve]').waitFor();
   await page.locator('[data-action=approve]').click();await page.locator('#modal').waitFor({state:'hidden'});
   const exported=await context.request.get('http://127.0.0.1:'+port+'/api/export');assert((await exported.text()).includes('Paper Co'),'approved invoice not exported');
  }
  if(project==='support'){
   const pub=await context.newPage();await pub.goto('http://127.0.0.1:'+port+'/public');await pub.locator('#f-customer').fill('DEMO QA Visitor');
   await pub.locator('#f-email').fill('qa@example.com');await pub.locator('#f-question').fill('Какие сроки доставки заказа?');await pub.locator('[name=consent]').check();
   await pub.locator('#ask-form [type=submit]').click();await pub.locator('#answer h3').waitFor();
   assert((await pub.locator('#answer').textContent()).includes('Источник:'),'source missing');
   await pub.screenshot({path:path.join(root,'screenshots','support-public.png'),fullPage:true});
   await page.reload();await page.locator('#create').waitFor();await page.locator('tr').filter({hasText:'DEMO QA Visitor'}).first().locator('[data-open]').click();
   await page.locator('#reply-form [type=submit]').click();await page.locator('a[href^="/api/email"]').waitFor();
   const href=await page.locator('a[href^="/api/email"]').getAttribute('href');const eml=await context.request.get('http://127.0.0.1:'+port+href);assert((await eml.text()).includes('X-Unsent: 1'),'email not a draft');
   await pub.close();
  }
  if(project==='booking'){
   const pub=await context.newPage();await pub.goto('http://127.0.0.1:'+port+'/public');
   let day=new Date();day.setUTCDate(day.getUTCDate()+2);while([0,6].includes(day.getUTCDay()))day.setUTCDate(day.getUTCDate()+1);
   await pub.locator('#f-day').fill(day.toISOString().slice(0,10));await pub.locator('[data-slot]').first().waitFor();await pub.locator('[data-slot]').first().click();
   await pub.locator('#f-customer').fill('DEMO QA Booking');await pub.locator('#f-email').fill('qa@example.com');await pub.locator('[name=consent]').check();
   await pub.screenshot({path:path.join(root,'screenshots','booking-public.png'),fullPage:true});
   await pub.locator('#booking-form [type=submit]').click();await pub.locator('input[readonly]').waitFor();const cancel=await pub.locator('input[readonly]').inputValue();
   const calendar=await pub.locator('a[href^="/api/public/calendar"]').getAttribute('href');const ics=await context.request.get('http://127.0.0.1:'+port+calendar);
   assert((await ics.text()).includes('BEGIN:VEVENT'),'calendar missing event');
   await pub.goto(cancel);await pub.reload();await pub.locator('#cancel-booking').click();await pub.getByText('Запись отменена',{exact:true}).waitFor();await pub.close();
  }
  results.push(project+': desktop, mobile, authenticated workflow passed');await context.close();
 }
 await browser.close();assert(!errors.length,errors.join('\n'));
 fs.writeFileSync(path.join(root,'screenshots','browser-results.json'),JSON.stringify({results,errors},null,2));
 console.log(results.join('\n'));
})().catch(e=>{console.error(e);process.exit(1)});
