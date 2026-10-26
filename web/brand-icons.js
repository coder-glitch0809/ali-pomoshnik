/* Xizmatlar belgilari (ikonkalar): har bir ulanish o'z belgisi bilan ko'rinadi */
(() => {
  'use strict';
  const svg = (body, bg) => `<svg class="brand-ico" viewBox="0 0 32 32" aria-hidden="true">${bg ? `<rect width="32" height="32" rx="8" fill="${bg}"/>` : ''}${body}</svg>`;
  window.ALI_ICONS = {
    instagram: `<svg class="brand-ico" viewBox="0 0 32 32" aria-hidden="true"><defs><radialGradient id="igg" cx="30%" cy="107%" r="150%"><stop offset="0" stop-color="#fdf497"/><stop offset=".05" stop-color="#fdf497"/><stop offset=".45" stop-color="#fd5949"/><stop offset=".6" stop-color="#d6249f"/><stop offset=".9" stop-color="#285AEB"/></radialGradient></defs><rect width="32" height="32" rx="8" fill="url(#igg)"/><rect x="8" y="8" width="16" height="16" rx="5" fill="none" stroke="#fff" stroke-width="2"/><circle cx="16" cy="16" r="3.8" fill="none" stroke="#fff" stroke-width="2"/><circle cx="21" cy="11" r="1.2" fill="#fff"/></svg>`,
    telegram: svg('<path d="M7 15.5l16-6.3c.8-.3 1.4.2 1.2 1.3l-2.7 12.6c-.2.9-.7 1.1-1.5.7l-4.1-3-2 1.9c-.2.2-.4.4-.8.4l.3-4.2 7.6-6.9c.3-.3-.1-.5-.5-.2l-9.4 5.9-4-1.3c-.9-.3-.9-.9.2-1.3z" fill="#fff"/>', '#29a9eb'),
    github: svg('<path d="M16 6a10 10 0 0 0-3.2 19.5c.5.1.7-.2.7-.5v-1.8c-2.8.6-3.4-1.2-3.4-1.2-.5-1.2-1.1-1.5-1.1-1.5-.9-.6.1-.6.1-.6 1 .1 1.5 1 1.5 1 .9 1.5 2.4 1.1 3 .8.1-.6.4-1.1.6-1.3-2.2-.3-4.6-1.1-4.6-5 0-1.1.4-2 1-2.7-.1-.3-.4-1.3.1-2.7 0 0 .8-.3 2.7 1a9.4 9.4 0 0 1 5 0c1.9-1.3 2.7-1 2.7-1 .5 1.4.2 2.4.1 2.7.6.7 1 1.6 1 2.7 0 3.9-2.4 4.7-4.6 5 .4.3.7.9.7 1.9v2.8c0 .3.2.6.7.5A10 10 0 0 0 16 6z" fill="#fff"/>', '#24292f'),
    vercel: svg('<path d="M16 9l8 14H8z" fill="#fff"/>', '#000'),
    voice: svg('<path d="M16 7a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0v-6a3 3 0 0 1 3-3zm-6 9a6 6 0 0 0 12 0M16 22v3" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"/>', '#7c5cff'),
    google: svg('<path d="M24.5 16.2c0-.6-.1-1.2-.2-1.7H16v3.3h4.8a4.1 4.1 0 0 1-1.8 2.7v2.2h2.9c1.7-1.6 2.6-3.9 2.6-6.5z" fill="#4285f4"/><path d="M16 25c2.4 0 4.5-.8 5.9-2.2L19 20.6c-.8.5-1.8.9-3 .9-2.3 0-4.3-1.6-5-3.7H8v2.3A9 9 0 0 0 16 25z" fill="#34a853"/><path d="M11 17.8a5.4 5.4 0 0 1 0-3.5V12H8a9 9 0 0 0 0 8.1z" fill="#fbbc05"/><path d="M16 10.6c1.3 0 2.5.5 3.4 1.3l2.6-2.6A9 9 0 0 0 8 12l3 2.3c.7-2.1 2.7-3.7 5-3.7z" fill="#ea4335"/>', '#fff'),
    meta: svg('<path d="M9 19.5c0-4 1.9-7.5 4.2-7.5 1.6 0 2.6 1.6 3.9 3.8 1.4 2.4 2.5 4.2 3.9 4.2 1.2 0 2-1.1 2-2.9 0-2.5-1.3-4.9-3-4.9-1.4 0-2.6 1.6-3.6 3.3M9 19.5c0 1.6.7 2.5 1.8 2.5 1.6 0 2.6-1.6 4.4-4.7" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"/>', '#0866ff'),
    channels: svg('<path d="M9 13v6h3l6 4V9l-6 4zM21 13.5a3.5 3.5 0 0 1 0 5" fill="none" stroke="#fff" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>', '#29a9eb'),
    gemini: svg('<path d="M16 6c.6 5.3 4.7 9.4 10 10-5.3.6-9.4 4.7-10 10-.6-5.3-4.7-9.4-10-10 5.3-.6 9.4-4.7 10-10z" fill="url(#gmg)"/><defs><linearGradient id="gmg" x1="6" y1="6" x2="26" y2="26"><stop offset="0" stop-color="#4f8cff"/><stop offset=".5" stop-color="#9b72f2"/><stop offset="1" stop-color="#d96570"/></linearGradient></defs>', '#fff'),
    chatgpt: svg('<path d="M16 8.5a4 4 0 0 1 3.9 3l.2.8.8-.2a4 4 0 0 1 2.5 7.4l-.6.5.4.7a4 4 0 0 1-6.6 4.4l-.6-.6-.6.6a4 4 0 0 1-6.6-4.4l.4-.7-.6-.5a4 4 0 0 1 2.5-7.4l.8.2.2-.8A4 4 0 0 1 16 8.5z" fill="none" stroke="#fff" stroke-width="1.8"/><circle cx="16" cy="16" r="2.4" fill="#fff"/>', '#10a37f'),
    claude: svg('<g stroke="#fff" stroke-width="2.2" stroke-linecap="round">' + Array.from({ length: 8 }, (_, i) => { const a = i * Math.PI / 4, c = Math.cos(a), s = Math.sin(a); return `<line x1="${16 + c * 3}" y1="${16 + s * 3}" x2="${16 + c * 9}" y2="${16 + s * 9}"/>`; }).join('') + '</g>', '#d97757'),
    vscode: svg('<path d="M21.5 7.5L24 8.7v14.6l-2.5 1.2-9-8.2-4 3-1.5-.8v-6.9l1.5-.8 4 3zm0 4.6l-5 3.9 5 3.9z" fill="#fff"/>', '#007acc'),
    photoshop: svg('<text x="16" y="21" text-anchor="middle" font-family="Arial,sans-serif" font-weight="700" font-size="12" fill="#31a8ff">Ps</text>', '#001e36'),
    coreldraw: svg('<circle cx="16" cy="16" r="7" fill="none" stroke="#fff" stroke-width="2.4"/><path d="M16 9a7 7 0 0 1 0 14" fill="#5fbf3c"/>', '#2b8a3e'),
    firebase: svg('<path d="M10 23l2.4-15.3c.1-.4.6-.5.8-.1L15.8 13z" fill="#ffc400"/><path d="M10 23l6.6-12.1c.2-.4.7-.4.9 0L22 23z" fill="#ff9100"/><path d="M10 23l9.8-12c.3-.3.8-.2.9.2L23 23l-6.2 3.4c-.5.3-1.1.3-1.6 0z" fill="#dd2c00"/>', '#1e2430'),
    bedrock: svg('<path d="M16 7l7.5 4.3v8.6L16 24.2l-7.5-4.3v-8.6z" fill="none" stroke="#ff9900" stroke-width="2" stroke-linejoin="round"/><path d="M16 15.6l7.5-4.3M16 15.6v8.6M16 15.6l-7.5-4.3" stroke="#ff9900" stroke-width="1.6"/>', '#232f3e'),
    chatplace: svg('<path d="M9 10h14a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-7l-4 3v-3H9a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2z" fill="none" stroke="#fff" stroke-width="2" stroke-linejoin="round"/><circle cx="12.5" cy="15.5" r="1.2" fill="#fff"/><circle cx="16" cy="15.5" r="1.2" fill="#fff"/><circle cx="19.5" cy="15.5" r="1.2" fill="#fff"/>', '#6c3cff'),
    memory: svg('<path d="M12 9a3 3 0 0 0-3 3 3 3 0 0 0-1 5.5A3 3 0 0 0 12 22a2.5 2.5 0 0 0 4 1V10a2.5 2.5 0 0 0-4-1zm8 0a3 3 0 0 1 3 3 3 3 0 0 1 1 5.5A3 3 0 0 1 20 22a2.5 2.5 0 0 1-4 1" fill="none" stroke="#fff" stroke-width="1.8" stroke-linejoin="round"/>', '#e8590c'),
    coach: svg('<text x="16" y="21.5" text-anchor="middle" font-size="15">🧑‍🏫</text>', '#3b2f6b'),
  };
  // Ulanish / ilova kaliti -> belgi kaliti
  window.ALI_ICON_FOR = (key) => window.ALI_ICONS[{ codex: 'chatgpt', _coach: 'coach', tg_account: 'telegram' }[key] || key] || '';
})();
