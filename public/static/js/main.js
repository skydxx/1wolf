(function () {
  if ('scrollRestoration' in history) history.scrollRestoration = 'manual';

  var root = document.documentElement;
  var dot = document.querySelector('.cur-dot');
  var ret = document.querySelector('.cur-ret');
  var fine = window.matchMedia('(pointer: fine)').matches;

  if (fine && dot && ret) {
    root.classList.add('cur-on');
    var tx = window.innerWidth / 2, ty = window.innerHeight / 2, rx = tx, ry = ty;

    document.addEventListener('mousemove', function (e) {
      tx = e.clientX; ty = e.clientY;
      dot.style.transform = 'translate3d(' + (tx - 2.5) + 'px,' + (ty - 2.5) + 'px,0)';
      var t = e.target;
      var interactive = t.closest && t.closest('a,button,input,select,textarea,summary,.drop,label.check');
      ret.classList.toggle('hover', !!interactive);
    });
    document.addEventListener('mousedown', function () { ret.classList.add('down'); });
    document.addEventListener('mouseup', function () { ret.classList.remove('down'); });

    (function loop() {
      rx += (tx - rx) * 0.18;
      ry += (ty - ry) * 0.18;
      var s = ret.offsetWidth / 2;
      ret.style.transform = 'translate3d(' + (rx - s) + 'px,' + (ry - s) + 'px,0)';
      requestAnimationFrame(loop);
    })();
  }

  var burger = document.querySelector('.nav-burger');
  var links = document.querySelector('.nav-links');
  function closeNav() {
    if (links) links.classList.remove('open');
    if (burger) burger.setAttribute('aria-expanded', 'false');
  }
  if (burger && links) {
    burger.addEventListener('click', function () {
      var open = links.classList.toggle('open');
      burger.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }

  var lastPathKey = location.pathname + location.search;

  var main = document.querySelector('main');
  if (!main || !window.fetch || !window.DOMParser) return;

  function currentScriptSrcs() {
    var set = {};
    document.querySelectorAll('script[src]').forEach(function (s) { set[s.src] = true; });
    return set;
  }

  function runPageScripts(doc) {
    document.querySelectorAll('script[data-spa-injected]').forEach(function (s) { s.remove(); });
    var known = currentScriptSrcs();
    doc.querySelectorAll('body script[src]').forEach(function (old) {
      if (known[old.src]) return;
      var fresh = document.createElement('script');
      for (var i = 0; i < old.attributes.length; i++) {
        fresh.setAttribute(old.attributes[i].name, old.attributes[i].value);
      }
      fresh.setAttribute('data-spa-injected', '1');
      document.body.appendChild(fresh);
    });
  }

  function isRoutable(url) {
    if (url.origin !== location.origin) return false;
    if (/^\/(static|media)\//.test(url.pathname)) return false;
    return true;
  }

  function wait(ms) {
    return new Promise(function (r) { setTimeout(r, ms); });
  }

  async function navigate(url, evt) {
    if (evt) evt.preventDefault();
    if (window.__navBusy) { location.href = url.href; return; }
    window.__navBusy = true;
    try {
      var res = await fetch(url.href, { cache: 'no-cache', headers: { 'X-Requested-With': 'fetch' } });
      if (res.redirected && new URL(res.url).pathname !== url.pathname) { location.href = res.url; return; }
      if (!res.ok || (res.headers.get('content-type') || '').indexOf('text/html') === -1) { location.href = url.href; return; }
      var html = await res.text();
      var doc = new DOMParser().parseFromString(html, 'text/html');
      var incoming = doc.querySelector('main');
      if (!incoming) { location.href = url.href; return; }

      main.style.transition = 'opacity .15s ease, transform .15s ease';
      main.style.opacity = '0';
      main.style.transform = 'translateX(-16px)';
      await wait(150);

      document.title = doc.title;
      main.innerHTML = incoming.innerHTML;
      closeNav();
      runPageScripts(doc);

      main.style.transition = 'none';
      main.style.opacity = '0';
      main.style.transform = 'translateX(16px)';
      void main.offsetHeight;
      if (url.hash) {
        var target = document.getElementById(url.hash.slice(1));
        if (target) target.scrollIntoView();
      } else {
        window.scrollTo(0, 0);
      }
      setTimeout(function () {
        main.style.transition = 'opacity .25s ease, transform .25s ease';
        main.style.opacity = '1';
        main.style.transform = 'none';
      }, 20);
      setTimeout(function () {
        main.style.transition = '';
        main.style.opacity = '';
        main.style.transform = '';
      }, 320);

      lastPathKey = url.pathname + url.search;
      history.pushState({ spa: true }, '', url.href);
    } catch (err) {
      location.href = url.href;
    } finally {
      window.__navBusy = false;
    }
  }

  document.addEventListener('click', function (e) {
    if (e.defaultPrevented || e.button !== 0) return;
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target.closest && e.target.closest('a[href]');
    if (!a || a.hasAttribute('data-no-router') || a.target === '_blank' || a.hasAttribute('download')) return;
    var url;
    try { url = new URL(a.href, location.href); } catch (err) { return; }
    if (!isRoutable(url)) return;
    if (url.pathname === location.pathname && url.search === location.search) {
      if (url.hash) return;
      e.preventDefault();
      return;
    }
    navigate(url, e);
  });

  window.addEventListener('popstate', function () {
    var key = location.pathname + location.search;
    if (key !== lastPathKey) {
      location.reload();
    }
    lastPathKey = key;
  });
})();
