(function (global) {
  "use strict";

  const DEFAULT_CACHE_LIMIT = 8;
  const CLEANUP_DELAY_MS = 180;

  function create(options = {}) {
    const researchData = options.researchData || {};
    const readingBody = options.readingBody || null;
    const virtualDocument = researchData.virtual_document?.enabled
      ? researchData.virtual_document
      : null;
    const descriptors = Array.isArray(virtualDocument?.chunks)
      ? virtualDocument.chunks
      : [];
    const descriptorByIndex = new Map(
      descriptors.map((descriptor) => [Number(descriptor.index), descriptor])
    );
    const chunkCache = new Map();
    const chunkRequests = new Map();
    const cacheLimit = Math.max(1, Number(options.cacheLimit || DEFAULT_CACHE_LIMIT));
    const onContentChanged = typeof options.onContentChanged === "function"
      ? options.onContentChanged
      : () => {};
    const onViewportChanged = typeof options.onViewportChanged === "function"
      ? options.onViewportChanged
      : () => {};
    const getSelectedSentenceNode = typeof options.getSelectedSentenceNode === "function"
      ? options.getSelectedSentenceNode
      : () => null;
    const getReadingCueTargetLine = typeof options.getReadingCueTargetLine === "function"
      ? options.getReadingCueTargetLine
      : () => window.innerHeight / 2;

    let chunkObserver = null;
    let cleanupTimer = 0;
    let viewportLoadHandle = 0;
    let activeChunkIndex = Number(virtualDocument?.initial_chunk || 0);

    function chunkElement(chunkIndex) {
      return document.getElementById(`work-chunk-${chunkIndex}`);
    }

    function chunkIndexForPosition(position) {
      let low = 0;
      let high = descriptors.length - 1;
      while (low <= high) {
        const middle = Math.floor((low + high) / 2);
        const descriptor = descriptors[middle];
        const start = Number(descriptor.sentence_start || 0);
        const end = start + Number(descriptor.sentence_count || 0) - 1;
        if (position < start) {
          high = middle - 1;
        } else if (position > end) {
          low = middle + 1;
        } else {
          return Number(descriptor.index);
        }
      }
      return -1;
    }

    function rememberChunk(payload) {
      const chunkIndex = Number(payload?.chunk?.index);
      if (!Number.isInteger(chunkIndex)) return;
      chunkCache.delete(chunkIndex);
      chunkCache.set(chunkIndex, payload);
      while (chunkCache.size > cacheLimit) {
        const oldestIndex = chunkCache.keys().next().value;
        chunkCache.delete(oldestIndex);
      }
    }

    async function requestChunk({ chunkIndex = null, anchor = "" } = {}) {
      if (!virtualDocument) return null;
      const requestKey = anchor ? `anchor:${anchor}` : `chunk:${chunkIndex}`;
      if (chunkRequests.has(requestKey)) {
        return chunkRequests.get(requestKey);
      }
      const request = (async () => {
        const url = new URL(virtualDocument.endpoint, location.origin);
        url.searchParams.set("corpus_id", researchData.corpus_id || researchData.author_id || "");
        url.searchParams.set("work_id", researchData.work_id || "");
        if (researchData.variant_id) {
          url.searchParams.set("variant_id", researchData.variant_id);
        }
        if (anchor) {
          url.searchParams.set("anchor", anchor);
          url.searchParams.delete("chunk");
        } else {
          url.searchParams.set("chunk", String(chunkIndex));
          url.searchParams.delete("anchor");
        }
        const response = await fetch(url, { headers: { Accept: "application/json" } });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || !payload?.chunk) {
          throw new Error(payload?.error || `청크를 불러오지 못했습니다 (${response.status})`);
        }
        rememberChunk(payload);
        return payload;
      })();
      chunkRequests.set(requestKey, request);
      try {
        return await request;
      } finally {
        chunkRequests.delete(requestKey);
      }
    }

    function applyScrollCorrection(chunk, beforeTop, beforeHeight) {
      if (beforeTop >= 0) return;
      const heightDelta = chunk.getBoundingClientRect().height - beforeHeight;
      if (Math.abs(heightDelta) > 0.5) {
        window.scrollBy({ top: heightDelta, left: 0, behavior: "auto" });
      }
    }

    function mountChunk(payload, preserveScroll = true) {
      const chunkData = payload?.chunk;
      const chunkIndex = Number(chunkData?.index);
      const chunk = chunkElement(chunkIndex);
      if (!chunk || !chunkData) return null;
      const beforeRect = chunk.getBoundingClientRect();
      chunk.innerHTML = String(chunkData.html || "");
      chunk.style.removeProperty("min-height");
      chunk.classList.add("is-loaded");
      chunk.classList.remove("reader-chunk-placeholder", "is-load-error");
      chunk.dataset.chunkState = "loaded";
      chunk.removeAttribute("aria-hidden");
      chunk.setAttribute("aria-busy", "false");
      const measuredHeight = Math.ceil(chunk.getBoundingClientRect().height);
      const descriptor = descriptorByIndex.get(chunkIndex);
      if (descriptor && measuredHeight > 0) {
        descriptor.measured_height = measuredHeight;
      }
      onContentChanged();
      if (preserveScroll) {
        applyScrollCorrection(chunk, beforeRect.top, beforeRect.height);
      }
      onViewportChanged();
      queueCleanup();
      return chunk;
    }

    function renderChunkError(chunk, chunkIndex) {
      chunk.style.removeProperty("min-height");
      chunk.classList.remove("is-loaded");
      chunk.classList.add("reader-chunk-placeholder", "is-load-error");
      chunk.dataset.chunkState = "error";
      chunk.removeAttribute("aria-hidden");
      chunk.setAttribute("aria-busy", "false");
      chunk.innerHTML = `<p class="reader-chunk-error" role="status">이 부분을 불러오지 못했습니다. <button type="button" data-load-work-chunk="${chunkIndex}">다시 시도</button></p>`;
    }

    async function ensureChunk(chunkIndex, { preserveScroll = true } = {}) {
      if (!virtualDocument || chunkIndex < 0 || chunkIndex >= descriptors.length) return null;
      const chunk = chunkElement(chunkIndex);
      if (!chunk) return null;
      if (chunk.dataset.chunkState === "loaded") return chunk;
      chunk.dataset.chunkState = "loading";
      chunk.setAttribute("aria-busy", "true");
      try {
        const cached = chunkCache.get(chunkIndex);
        const payload = cached || await requestChunk({ chunkIndex });
        return mountChunk(payload, preserveScroll);
      } catch (error) {
        renderChunkError(chunk, chunkIndex);
        throw error;
      }
    }

    async function ensureTarget(targetId) {
      if (!targetId) return null;
      const existing = document.getElementById(targetId);
      if (existing) return existing;
      if (!virtualDocument) return null;
      const payload = await requestChunk({ anchor: targetId });
      const chunkIndex = Number(payload.chunk.index);
      const chunk = mountChunk(payload, true);
      activeChunkIndex = chunkIndex;
      await Promise.all(
        [chunkIndex - 1, chunkIndex + 1]
          .filter((neighborIndex) => neighborIndex >= 0 && neighborIndex < descriptors.length)
          .map((neighborIndex) => ensureChunk(neighborIndex).catch(() => null))
      );
      return chunk ? document.getElementById(targetId) : null;
    }

    function warmChunks(chunkIndex) {
      if (!virtualDocument) return;
      [chunkIndex - 1, chunkIndex + 1].forEach((neighborIndex) => {
        if (neighborIndex < 0 || neighborIndex >= descriptors.length) return;
        ensureChunk(neighborIndex).catch(() => {});
      });
    }

    function chunkForNode(node) {
      const chunk = node?.closest?.(".reader-chunk");
      const chunkIndex = Number(chunk?.dataset.chunkIndex);
      return Number.isInteger(chunkIndex) ? chunkIndex : -1;
    }

    function unmountChunk(chunk) {
      if (!chunk || chunk.dataset.chunkState !== "loaded") return false;
      if (chunk.contains(document.activeElement)) return false;
      const selectedNode = getSelectedSentenceNode();
      if (selectedNode && chunk.contains(selectedNode)) return false;
      const chunkIndex = Number(chunk.dataset.chunkIndex);
      const descriptor = descriptorByIndex.get(chunkIndex);
      const measuredHeight = Math.ceil(chunk.getBoundingClientRect().height);
      if (descriptor && measuredHeight > 0) {
        descriptor.measured_height = measuredHeight;
      }
      chunk.style.minHeight = `${Math.max(1, measuredHeight)}px`;
      chunk.innerHTML = `<span class="visually-hidden">문서 청크 ${chunkIndex + 1}. 스크롤하면 다시 불러옵니다.</span>`;
      chunk.classList.remove("is-loaded");
      chunk.classList.add("reader-chunk-placeholder");
      chunk.dataset.chunkState = "placeholder";
      chunk.setAttribute("aria-hidden", "true");
      return true;
    }

    function cleanupChunks() {
      cleanupTimer = 0;
      if (!virtualDocument) return;
      const keepIndexes = new Set([
        activeChunkIndex - 1,
        activeChunkIndex,
        activeChunkIndex + 1
      ]);
      const selectedChunkIndex = chunkForNode(getSelectedSentenceNode());
      if (selectedChunkIndex >= 0) keepIndexes.add(selectedChunkIndex);
      const focusedChunkIndex = chunkForNode(document.activeElement);
      if (focusedChunkIndex >= 0) keepIndexes.add(focusedChunkIndex);
      let changed = false;
      document.querySelectorAll(".reader-chunk.is-loaded").forEach((chunk) => {
        const chunkIndex = Number(chunk.dataset.chunkIndex);
        if (!keepIndexes.has(chunkIndex)) {
          changed = unmountChunk(chunk) || changed;
        }
      });
      if (changed) onContentChanged();
    }

    function queueCleanup() {
      if (!virtualDocument) return;
      window.clearTimeout(cleanupTimer);
      cleanupTimer = window.setTimeout(cleanupChunks, CLEANUP_DELAY_MS);
    }

    function refreshViewportChunk() {
      viewportLoadHandle = 0;
      if (!virtualDocument || !readingBody) return;
      const bodyRect = readingBody.getBoundingClientRect();
      const probeX = Math.max(
        1,
        Math.min(window.innerWidth - 1, bodyRect.left + Math.min(180, bodyRect.width / 2))
      );
      const probeY = Math.max(1, Math.min(window.innerHeight - 1, getReadingCueTargetLine()));
      const chunk = document.elementFromPoint(probeX, probeY)?.closest?.(".reader-chunk");
      if (!chunk) return;
      const chunkIndex = Number(chunk.dataset.chunkIndex);
      if (!Number.isInteger(chunkIndex)) return;
      activeChunkIndex = chunkIndex;
      ensureChunk(chunkIndex).catch(() => {});
      warmChunks(chunkIndex);
      queueCleanup();
    }

    function scheduleViewportRefresh() {
      if (!virtualDocument || viewportLoadHandle) return;
      viewportLoadHandle = window.requestAnimationFrame(refreshViewportChunk);
    }

    function initialize() {
      onContentChanged();
      if (!virtualDocument) return;
      document.querySelectorAll(".reader-chunk.is-loaded").forEach((chunk) => {
        const descriptor = descriptorByIndex.get(Number(chunk.dataset.chunkIndex));
        if (descriptor) descriptor.measured_height = Math.ceil(chunk.getBoundingClientRect().height);
      });
      if ("IntersectionObserver" in window) {
        chunkObserver = new IntersectionObserver((entries) => {
          let closestEntry = null;
          entries.forEach((entry) => {
            if (!entry.isIntersecting) return;
            const chunkIndex = Number(entry.target.dataset.chunkIndex);
            ensureChunk(chunkIndex).catch(() => {});
            if (!closestEntry || Math.abs(entry.boundingClientRect.top) < Math.abs(closestEntry.boundingClientRect.top)) {
              closestEntry = entry;
            }
          });
          if (closestEntry) {
            activeChunkIndex = Number(closestEntry.target.dataset.chunkIndex);
            warmChunks(activeChunkIndex);
            queueCleanup();
          }
        }, {
          root: null,
          rootMargin: "1000px 0px",
          threshold: 0
        });
        document.querySelectorAll(".reader-chunk").forEach((chunk) => chunkObserver.observe(chunk));
      }
      window.addEventListener("scroll", scheduleViewportRefresh, { passive: true });
      window.addEventListener("pageshow", scheduleViewportRefresh);
      warmChunks(activeChunkIndex);
      scheduleViewportRefresh();
    }

    function setActiveChunkIndex(value) {
      const nextIndex = Number(value);
      if (Number.isInteger(nextIndex)) activeChunkIndex = nextIndex;
    }

    return Object.freeze({
      document: virtualDocument,
      descriptors,
      get activeChunkIndex() {
        return activeChunkIndex;
      },
      chunkForNode,
      chunkIndexForPosition,
      ensureChunk,
      ensureTarget,
      initialize,
      queueCleanup,
      setActiveChunkIndex,
      warmChunks,
    });
  }

  global.ReaderWorkVirtual = Object.freeze({ create });
})(window);
