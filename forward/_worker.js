// Forwards the spare addresses to the two main ones.
//   polygrovedb.com, www.polygrovedb.*   ->  https://polygrovedb.org
//   polygroveapp.org, www.polygroveapp.* ->  https://polygroveapp.com
// The path and query are kept, so old links land on the same page.
// Deployed as its own Cloudflare Pages project (polygrove-forward) so the
// two real sites never run code on a request.
const MAIN = { polygrovedb: 'polygrovedb.org', polygroveapp: 'polygroveapp.com' };

export default {
  fetch(request) {
    const url = new URL(request.url);
    const host = url.hostname.replace(/^www\./, '');
    const name = host.split('.')[0];
    const to = MAIN[name] || MAIN.polygrovedb;
    // www -> bare on the same domain never changes; .com <-> .org might.
    const status = host === to ? 301 : 302;
    return Response.redirect(`https://${to}${url.pathname}${url.search}`, status);
  },
};
