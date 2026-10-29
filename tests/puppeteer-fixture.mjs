import {runBridge} from '../src/xhs_mcp/puppeteer/bridge.mjs';

let fixture = {html: '', status: 200};
const urls = [];

await runBridge({
  intercept: async request => {
    if (request.resourceType() === 'document') {
      urls.push(request.url());
      await request.respond({
        status: fixture.status,
        contentType: 'text/html; charset=utf-8',
        body: fixture.html,
      });
    } else {
      await request.abort();
    }
    return true;
  },
  commands: {
    fixture: async (_page, params) => { fixture = params; },
    requests: async () => urls,
    set_content: async (page, params) => { await page.setContent(params.html); },
    set_cookies: async (_page, params, browser) => {
      await browser.defaultBrowserContext().setCookie(...params.cookies);
    },
    cookies: async (_page, _params, browser) => browser.defaultBrowserContext().cookies(),
  },
});
