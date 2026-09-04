(function () {
  "use strict";

  const MEASUREMENT_ID = "G-E4SF1QQDWB";

  if (window.__POIGAME_GA4_LOADED__) return;
  window.__POIGAME_GA4_LOADED__ = true;

  window.dataLayer = window.dataLayer || [];
  window.gtag = window.gtag || function () {
    window.dataLayer.push(arguments);
  };

  const script = document.createElement("script");
  script.async = true;
  script.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(MEASUREMENT_ID);
  document.head.appendChild(script);

  window.gtag("js", new Date());
  window.gtag("config", MEASUREMENT_ID);
})();
