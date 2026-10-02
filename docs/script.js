/* A&R Scouting Command Center — Landing interactions */
(function () {
  'use strict';

  var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- Nav: estado al hacer scroll ---------- */
  var nav = document.getElementById('nav');
  function onScroll() {
    if (window.scrollY > 24) nav.classList.add('scrolled');
    else nav.classList.remove('scrolled');
  }
  onScroll();
  window.addEventListener('scroll', onScroll, { passive: true });

  /* ---------- Menú móvil ---------- */
  var toggle = document.getElementById('navToggle');
  var links = document.getElementById('navLinks');

  toggle.addEventListener('click', function () {
    var open = links.classList.toggle('open');
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Cerrar menú' : 'Abrir menú');
  });

  links.addEventListener('click', function (e) {
    if (e.target.tagName === 'A') {
      links.classList.remove('open');
      toggle.setAttribute('aria-expanded', 'false');
      toggle.setAttribute('aria-label', 'Abrir menú');
    }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && links.classList.contains('open')) {
      links.classList.remove('open');
      toggle.setAttribute('aria-expanded', 'false');
      toggle.focus();
    }
  });

  /* ---------- Scroll reveal (IntersectionObserver) ---------- */
  var revealEls = document.querySelectorAll('.reveal');
  revealEls.forEach(function (el) {
    var delay = el.getAttribute('data-delay');
    if (delay) el.style.setProperty('--d', delay + 'ms');
  });

  if (reducedMotion || !('IntersectionObserver' in window)) {
    revealEls.forEach(function (el) { el.classList.add('visible'); });
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -60px 0px' });

    revealEls.forEach(function (el) { io.observe(el); });
  }

  /* ---------- Contadores animados ---------- */
  function animateCount(el) {
    var target = parseFloat(el.getAttribute('data-count'));
    var suffix = el.getAttribute('data-suffix') || '';
    if (isNaN(target)) return;

    if (reducedMotion) {
      el.textContent = target + suffix;
      return;
    }

    var duration = 1400;
    var start = performance.now();

    function tick(now) {
      var p = Math.min((now - start) / duration, 1);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(target * eased) + suffix;
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  var counters = document.querySelectorAll('.metric[data-count]');
  if ('IntersectionObserver' in window) {
    var counterIO = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          animateCount(entry.target);
          counterIO.unobserve(entry.target);
        }
      });
    }, { threshold: 0.6 });
    counters.forEach(function (el) { counterIO.observe(el); });
  }

  /* ---------- Enlace activo según sección visible ---------- */
  var sections = document.querySelectorAll('main section[id]');
  var navAnchors = document.querySelectorAll('.nav-links a');

  if ('IntersectionObserver' in window && sections.length) {
    var sectionIO = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var id = entry.target.id;
        navAnchors.forEach(function (a) {
          a.classList.toggle('active', a.getAttribute('href') === '#' + id);
        });
      });
    }, { rootMargin: '-45% 0px -50% 0px', threshold: 0 });

    sections.forEach(function (s) { sectionIO.observe(s); });
  }

  /* ---------- Año dinámico en el footer ---------- */
  var yearEl = document.getElementById('year');
  if (yearEl) yearEl.textContent = new Date().getFullYear();
})();
