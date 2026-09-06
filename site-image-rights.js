(() => {
  "use strict";

  // Register only artwork that requires a visible rights notice.
  // User-approved or POIGAME LAB original artwork should not be added here.
  window.POIGAME_IMAGE_RIGHTS = Object.freeze({
    "ワーキングヒーロー": Object.freeze({
      credit: "画像出典：ワーキングヒーローズ公式サイト"
    })
  });

  // Preserve the full official Working Heroes key visual instead of cropping it
  // inside the site's fixed-ratio card/detail image frames.
  const style = document.createElement("style");
  style.textContent = `
    .game-thumbnail[src*="w-heroes.com/img/sp/key_visual.png"],
    .game-artwork img[src*="w-heroes.com/img/sp/key_visual.png"] {
      object-fit: contain !important;
      background: #ffffff;
    }
  `;
  document.head.appendChild(style);
})();
