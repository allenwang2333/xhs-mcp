import {createInterface} from 'node:readline';
import {pathToFileURL} from 'node:url';

const hosts = new Set(['xiaohongshu.com', 'www.xiaohongshu.com']);

function evaluateSource(source, argument) {
  const value = (0, eval)(`(${source})`);
  return typeof value === 'function' ? value(argument) : value;
}

async function interceptNavigation(request, page, intercept) {
  if (request.isInterceptResolutionHandled()) return;
  if (request.isNavigationRequest() && request.frame() === page.mainFrame()) {
    const url = new URL(request.url());
    if (url.protocol === 'http:' && hosts.has(url.hostname) && !url.port) {
      // Upgrade site-generated HTTP redirects without sending the HTTP request.
      url.protocol = 'https:';
      await request.respond({status: 307, headers: {location: url.href}});
      return;
    }
    if (url.protocol !== 'https:' || !hosts.has(url.hostname) || url.port ||
        url.username || url.password) {
      await request.abort();
      return;
    }
  }
  if (intercept && await intercept(request)) return;
  await request.continue();
}

// Test hooks stay outside the production command set and never become MCP tools.
export async function runBridge({intercept, commands = {}} = {}) {
  let browser;
  let page;
  let launching;
  let closing;

  const close = () => {
    closing ??= (async () => {
      await launching?.catch(() => {});
      await browser?.close();
    })();
    return closing;
  };
  const onEnd = () => { void close(); };
  const onSignal = () => { void close().finally(() => process.exit(0)); };
  process.stdin.once('end', onEnd);
  for (const signal of ['SIGTERM', 'SIGINT', 'SIGHUP']) process.on(signal, onSignal);

  const lines = createInterface({input: process.stdin, crlfDelay: Infinity});
  try {
    for await (const line of lines) {
      if (closing) break;
      let method;
      try {
        const request = JSON.parse(line);
        method = request.method;
        const params = request.params ?? {};
        let result;
        if (method === 'launch') {
          let puppeteer;
          try {
            puppeteer = (await import('puppeteer-core')).default;
          } catch {
            const error = new Error('Missing Node dependencies');
            error.code = 'dependencies';
            throw error;
          }
          if (closing) break;
          launching = puppeteer.launch({
            ...(params.chrome_path ? {executablePath: params.chrome_path} : {channel: 'chrome'}),
            userDataDir: params.profile_dir,
            headless: params.headless,
            defaultViewport: {width: 1440, height: 1000},
            args: ['--lang=zh-CN'],
            timeout: params.timeout_ms,
            handleSIGINT: false,
            handleSIGTERM: false,
            handleSIGHUP: false,
          }).then(instance => { browser = instance; return instance; });
          await launching;
          page = (await browser.pages())[0] ?? await browser.newPage();
          page.setDefaultTimeout(params.timeout_ms);
          page.setDefaultNavigationTimeout(params.timeout_ms);
          await page.setRequestInterception(true);
          page.on('request', request => {
            void interceptNavigation(request, page, intercept).catch(() => {
              if (!request.isInterceptResolutionHandled()) void request.abort().catch(() => {});
            });
          });
          result = null;
        } else if (!page) {
          throw new Error('Browser is not running');
        } else if (method === 'goto') {
          const response = await page.goto(params.url, {waitUntil: 'domcontentloaded'});
          result = response?.status() ?? null;
        } else if (method === 'evaluate') {
          result = await page.evaluate(evaluateSource, params.source, params.argument);
        } else if (method === 'wait_for_function') {
          const handle = await page.waitForFunction(evaluateSource, {}, params.source, params.argument);
          try {
            result = await handle.jsonValue();
          } finally {
            await handle.dispose();
          }
        } else if (Object.hasOwn(commands, method)) {
          result = await commands[method](page, params, browser);
        } else {
          throw new Error('Unknown browser command');
        }
        process.stdout.write(JSON.stringify({ok: true, result: result ?? null}) + '\n');
      } catch (error) {
        // Never send raw browser errors: they can contain URLs and access parameters.
        const code = error.code === 'dependencies' ? 'dependencies'
          : error.name === 'TimeoutError' ? 'timeout'
          : method === 'launch' ? 'launch' : 'request';
        process.stdout.write(JSON.stringify({ok: false, error: code}) + '\n');
      }
    }
  } finally {
    await close();
    lines.close();
    process.stdin.off('end', onEnd);
    for (const signal of ['SIGTERM', 'SIGINT', 'SIGHUP']) process.off(signal, onSignal);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await runBridge();
}
