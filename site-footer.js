(() => {
  "use strict";

  if (document.querySelector("[data-poigame-footer]")) return;

  if (!document.querySelector('link[rel="icon"]')) {
    const icon = document.createElement("link");
    icon.rel = "icon";
    icon.href = "poigamelab_icon.png";
    document.head.appendChild(icon);
  }

  if (!document.getElementById("poigame-footer-style")) {
    const style = document.createElement("style");
    style.id = "poigame-footer-style";
    style.textContent = `
      .poigame-footer {
        margin-top: 48px;
        padding: 28px 18px 34px;
        border-top: 1px solid #e9e3f7;
        background: #faf8ff;
        color: #706780;
        font-size: 12px;
        line-height: 1.7;
        text-align: center;
      }
      .poigame-footer__links {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        gap: 10px 18px;
        margin-bottom: 12px;
      }
      .poigame-footer a {
        color: #5b35b5;
        font-weight: 700;
        text-decoration: none;
      }
      .poigame-footer a:hover { text-decoration: underline; }
      .poigame-footer__note {
        max-width: 760px;
        margin: 0 auto 10px;
      }
      .poigame-footer__copy { margin: 0; }
    `;
    document.head.appendChild(style);
  }

  const footer = document.createElement("footer");
  footer.className = "poigame-footer";
  footer.setAttribute("data-poigame-footer", "");
  footer.innerHTML = `
    <nav class="poigame-footer__links" aria-label="サイト情報">
      <a href="about.html">運営情報・免責事項</a>
      <a href="privacy.html">プライバシーポリシー</a>
      <a href="contact.html">お問い合わせ</a>
    </nav>
    <p class="poigame-footer__note">
      案件の報酬・条件・掲載状況は変動します。申込み前に必ずリンク先のポイントサイトで最新条件をご確認ください。
    </p>
    <p class="poigame-footer__copy">© 2026 POIGAME LAB</p>
  `;
  document.body.appendChild(footer);
})();