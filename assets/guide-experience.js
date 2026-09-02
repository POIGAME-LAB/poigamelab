(function () {
  "use strict";

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function safeUrl(value) {
    try {
      const url = new URL(String(value || ""), window.location.href);
      return ["http:", "https:"].includes(url.protocol) ? url.href : "";
    } catch (_) {
      return "";
    }
  }

  function statusLabel(status) {
    if (status === "completed") return "達成";
    if (status === "retired") return "撤退";
    return "挑戦中";
  }

  function renderPlayer(player, extraClass = "") {
    const sources = Array.isArray(player.sources) ? player.sources : [];
    const firstSource = sources.map(safeUrl).find(Boolean) || "";
    const milestones = Array.isArray(player.milestones) ? player.milestones : [];
    const items = milestones.map((m) => `
      <div class="timeline-item">
        <span class="timeline-day">${escapeHtml(m.dayLabel || (m.day ? `${m.day}日目` : "記録"))}</span>
        <span class="timeline-dot" aria-hidden="true"></span>
        <strong class="timeline-label">${escapeHtml(m.label || (m.level ? `Lv${m.level}` : ""))}</strong>
        ${m.detail ? `<small class="timeline-sub">${escapeHtml(m.detail)}</small>` : ""}
      </div>`).join("");

    return `
      <article class="player-card${extraClass}" data-status="${escapeHtml(player.status || "ongoing")}">
        <div class="player-card-head">
          <div class="player-avatar" aria-hidden="true">👤</div>
          <div>
            <div class="player-name-row">
              <span class="player-name">${escapeHtml(player.label || "プレイヤー")}</span>
              <span class="player-status">${escapeHtml(statusLabel(player.status))}</span>
            </div>
            <div class="player-summary">${escapeHtml(player.summary || "進捗記録")}</div>
          </div>
          ${firstSource ? `<a class="player-source" href="${firstSource}" target="_blank" rel="noopener noreferrer">出典を見る</a>` : ""}
        </div>
        <div class="timeline" aria-label="${escapeHtml(player.label || "プレイヤー")}の進捗">
          ${items}
        </div>
        ${player.note ? `<p class="player-note">${escapeHtml(player.note)}</p>` : ""}
      </article>`;
  }

  function render(root, data) {
    const players = Array.isArray(data.players) ? data.players : [];

    const requestedLimit = Number.parseInt(data.initialVisible, 10);
    const visibleLimit =
      Number.isFinite(requestedLimit) && requestedLimit > 0
        ? requestedLimit
        : 4;

    const hiddenCount = Math.max(0, players.length - visibleLimit);

    const playerHtml = players.map((player, index) =>
      renderPlayer(
        player,
        index >= visibleLimit ? " is-extra-player" : ""
      )
    ).join("");

    root.innerHTML = `
      <div class="experience-head">
        <h2>${escapeHtml(data.title || "実例：プレイヤーの進捗記録")}</h2>
        <span class="experience-count">${players.length}名の実例</span>
      </div>

      <p class="experience-intro">
        ${escapeHtml(
          data.intro ||
          "公開されているプレイヤー記録を、同一人物ごとにまとめています。"
        )}
      </p>

      ${data.notice
        ? `<p class="experience-notice">${escapeHtml(data.notice)}</p>`
        : ""
      }

      <div class="player-list">
        ${playerHtml}
      </div>

      ${hiddenCount > 0
        ? `
          <button
            type="button"
            class="experience-more-button"
            aria-expanded="false"
          >
            <span class="experience-more-text">\u3082\u3063\u3068\u898b\u308b</span>
            <small class="experience-more-count">\u3042\u3068${hiddenCount}\u4eba</small>
            <span class="experience-more-arrow" aria-hidden="true">⌄</span>
          </button>
        `
        : ""
      }

      ${data.footnote
        ? `<p class="experience-footnote">${escapeHtml(data.footnote)}</p>`
        : ""
      }
    `;

    const button = root.querySelector(".experience-more-button");

    if (button) {
      button.addEventListener("click", () => {
        const expanded = button.getAttribute("aria-expanded") !== "true";

        button.setAttribute("aria-expanded", String(expanded));
        root.classList.toggle("is-expanded", expanded);

        const text = button.querySelector(".experience-more-text");
        const count = button.querySelector(".experience-more-count");

        if (text) {
          text.textContent = expanded
            ? "\u9589\u3058\u308b"
            : "\u3082\u3063\u3068\u898b\u308b";
        }

        if (count) {
          count.hidden = expanded;
        }
      });
    }
  }

  async function init(root) {
    const inlineId = root.dataset.experienceInline;
    if (inlineId) {
      const el = document.getElementById(inlineId);
      if (!el) throw new Error(`experience inline data not found: ${inlineId}`);
      render(root, JSON.parse(el.textContent));
      return;
    }

    const src = root.dataset.experienceSrc;
    if (!src) throw new Error("experience data source missing");
    const response = await fetch(src, { cache: "no-store" });
    if (!response.ok) throw new Error(`experience data fetch failed: ${response.status}`);
    render(root, await response.json());
  }

  function boot() {
    document.querySelectorAll("[data-experience-src],[data-experience-inline]").forEach((root) => {
      init(root).catch((error) => {
        console.error("POIGAME LAB experience render failed", error);
        root.innerHTML = '<p class="experience-footnote">進捗データを読み込めませんでした。</p>';
      });
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
