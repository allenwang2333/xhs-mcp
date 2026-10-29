"""Read rendered page content. Never serialize browser cookies or storage."""

SEARCH_CARDS = """() => {
    const text = (root, selector) => root.querySelector(selector)?.textContent?.trim() || '';
    return [...document.querySelectorAll('section.note-item')].map(card => {
        const links = [...card.querySelectorAll('a[href]')];
        const pattern = /\\/(explore|search_result|discovery\\/item)\\/[a-f0-9]{24}/i;
        const link = links.find(a => pattern.test(a.pathname));
        if (!link) return null;
        return {
            url: link.href,
            title: text(card, '.title'),
            author: text(card, '.author .name, .author-wrapper .name'),
            likes: text(card, '.like-wrapper .count'),
            cover_url: card.querySelector('.cover img, img')?.src || ''
        };
    }).filter(Boolean);
}"""

POST_DETAIL = """() => {
    const text = selector => document.querySelector(selector)?.textContent?.trim() || '';
    const root = document.querySelector('.note-detail-mask, .note-container') || document;
    const images = [...root.querySelectorAll('.swiper-slide img, .note-slider img')]
        .map(img => img.src).filter(src => /^https?:\\/\\//.test(src));
    return {
        title: text('#detail-title'),
        content: text('#detail-desc'),
        author: text('.author-container .username, .author-wrapper .username'),
        date: text('.bottom-container .date, .note-content .date'),
        likes: text('.interact-container .like-wrapper .count, ' +
                    '.interaction-container .like-wrapper .count'),
        images: [...new Set(images)].slice(0, 30),
        tags: [...new Set([...document.querySelectorAll('#detail-desc .tag')]
            .map(tag => tag.textContent.trim()))]
    };
}"""

# Poll for content, but stop early when the site asks for human action.
PAGE_STATE = """kind => {
    if (location.pathname.startsWith('/website-login/error')) return 'restricted';
    const visible = selector => [...document.querySelectorAll(selector)].some(el =>
        el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden');
    const body = document.body?.innerText || '';
    if (visible('#captcha, .captcha-container, .verify-modal')) return 'verification';
    if (visible('.login-container, .login-modal, .login-mask')) return 'login';
    if (kind === 'search' && document.querySelector('section.note-item')) return 'ready';
    if (kind === 'post' && [...document.querySelectorAll('#detail-title, #detail-desc')]
        .some(el => el.textContent.trim())) return 'ready';
    if (/请完成.*验证|安全验证|拖动滑块|访问频次异常|访问过于频繁/.test(body))
        return 'verification';
    if (/页面不见了|笔记不存在|笔记已删除|内容无法展示/.test(body) ||
        /内容暂时无法展示|当前笔记暂时无法浏览/.test(body)) return 'unavailable';
    if (kind === 'search' && /暂无搜索结果|没有找到相关/.test(body)) return 'empty';
    return false;
}"""
