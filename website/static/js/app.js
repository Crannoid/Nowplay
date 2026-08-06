// Nowplay — accordion toggling + detail sheet. No fetch/XHR: every card
// already carries everything the sheet needs in its data-* attributes
// (rendered server-side by templates/_card.html), so opening the sheet is
// pure client-side state, no round-trip to the read-only Flask app needed.

document.addEventListener("DOMContentLoaded", () => {
  // --- Accordion sections ---
  document.querySelectorAll(".section-toggle").forEach((toggle) => {
    toggle.addEventListener("click", () => {
      const grid = toggle.parentElement.querySelector(".card-grid");
      const isOpen = toggle.getAttribute("aria-expanded") === "true";

      toggle.setAttribute("aria-expanded", String(!isOpen));
      toggle.querySelector(".chevron").textContent = isOpen ? "▸" : "▾";

      const pill = toggle.querySelector(".count-pill");
      pill.classList.toggle("count-pill--active", !isOpen);
      pill.classList.toggle("count-pill--muted", isOpen);

      if (isOpen) {
        grid.setAttribute("hidden", "");
      } else {
        grid.removeAttribute("hidden");
      }
    });
  });

  // --- Detail bottom sheet ---
  const backdrop = document.getElementById("sheet-backdrop");
  const sheet = document.getElementById("detail-sheet");
  const elPoster = document.getElementById("sheet-poster");
  const elTitle = document.getElementById("sheet-title");
  const elMeta = document.getElementById("sheet-meta");
  const elOverview = document.getElementById("sheet-overview");
  const elOpenLink = document.getElementById("sheet-open-link");
  const elOpenPlatform = document.getElementById("sheet-open-platform");

  function openSheet(card) {
    const d = card.dataset;

    elTitle.textContent = d.title;

    const metaParts = [d.platformLabel, d.typeLabel, d.releaseYear].filter(Boolean);
    elMeta.textContent = metaParts.join(" · ");

    elOverview.textContent = d.overview || "No description available yet.";

    if (d.posterUrl) {
      elPoster.style.backgroundImage = `url('${d.posterUrl}')`;
    } else {
      elPoster.style.backgroundImage = "none";
    }

    elOpenPlatform.textContent = d.platformLabel;
    if (d.watchlistUrl) {
      elOpenLink.href = d.watchlistUrl;
      elOpenLink.style.display = "";
    } else {
      elOpenLink.style.display = "none";
    }

    backdrop.hidden = false;
    sheet.hidden = false;
  }

  function closeSheet() {
    backdrop.hidden = true;
    sheet.hidden = true;
  }

  document.querySelectorAll(".poster-card").forEach((card) => {
    card.addEventListener("click", () => openSheet(card));
  });

  backdrop.addEventListener("click", closeSheet);
});
