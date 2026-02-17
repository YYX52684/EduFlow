/* EduFlow 前端设置：设置弹窗、壁纸、LLM 配置、主题、左侧栏折叠与双击隐藏 */
(function() {
  'use strict';
  var settingsModal = document.getElementById('settingsModal');
  function updateWallpaperPreview() {
    var wrap = document.getElementById('wallpaperPreview');
    try {
      var dataUrl = localStorage.getItem(window.WALLPAPER_KEY);
      if (dataUrl) {
        wrap.innerHTML = '<img src="' + dataUrl + '" alt="当前壁纸">';
      } else {
        wrap.innerHTML = '<span class="no-preview">当前未设置壁纸</span>';
      }
    } catch (e) {
      wrap.innerHTML = '<span class="no-preview">当前未设置壁纸</span>';
    }
  }
  function loadLlmConfig() {
    window.apiFetch('/api/llm/config').then(function(r) { return window.safeResponseJson(r); }).then(function(data) {
      document.getElementById('llmModelType').value = data.model_type || 'deepseek';
      document.getElementById('llmApiKey').value = '';
      document.getElementById('llmApiKeyMasked').textContent = data.has_api_key ? '已保存 Key: ' + (data.api_key_masked || '***') : '未设置';
      document.getElementById('llmBaseUrl').value = data.base_url || '';
      document.getElementById('llmModelName').value = data.model || '';
      document.getElementById('llmCustomFields').style.display = (data.model_type === 'openai') ? 'block' : 'none';
    }).catch(function() {
      document.getElementById('llmApiKeyMasked').textContent = '加载失败';
    });
  }
  document.getElementById('llmModelType').onchange = function() {
    document.getElementById('llmCustomFields').style.display = (this.value === 'openai') ? 'block' : 'none';
  };
  document.getElementById('btnSaveLlmConfig').onclick = function() {
    var payload = { model_type: document.getElementById('llmModelType').value };
    var key = document.getElementById('llmApiKey').value.trim();
    if (key) payload.api_key = key;
    if (document.getElementById('llmModelType').value === 'openai') {
      payload.base_url = document.getElementById('llmBaseUrl').value.trim();
      payload.model = document.getElementById('llmModelName').value.trim();
    }
    document.getElementById('llmConfigMsg').textContent = '保存中…';
    window.showLongTaskFeedback('保存 LLM 配置中…');
    window.apiFetch('/api/llm/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      .then(function(r) { return window.safeResponseJson(r); })
      .then(function(data) {
        document.getElementById('llmConfigMsg').textContent = data.message || '已保存';
        loadLlmConfig();
      })
      .catch(function(e) {
        document.getElementById('llmConfigMsg').textContent = '保存失败: ' + (e.message || e);
      })
      .finally(function() { window.hideLongTaskFeedback(); });
  };
  document.getElementById('btnSettings').onclick = function() {
    updateWallpaperPreview();
    loadLlmConfig();
    window.openModal(settingsModal, this);
  };
  document.getElementById('btnCloseSettings').onclick = function() { window.closeModal(settingsModal); };
  settingsModal.onclick = function(e) { if (e.target === settingsModal) window.closeModal(settingsModal); };
  (function initSettingsNav() {
    var navItems = settingsModal.querySelectorAll('.settings-nav-item');
    var pages = { llm: document.getElementById('settingsPageLlm'), wallpaper: document.getElementById('settingsPageWallpaper') };
    navItems.forEach(function(btn) {
      btn.onclick = function() {
        var pageId = this.getAttribute('data-settings-page');
        navItems.forEach(function(b) { b.classList.remove('active'); });
        this.classList.add('active');
        for (var k in pages) { pages[k].classList.remove('active'); if (k === pageId) pages[k].classList.add('active'); }
      };
    });
  })();

  var wallpaperDZ = document.getElementById('wallpaperDropZone');
  var wallpaperInput = document.getElementById('wallpaperFile');
  function setWallpaperFromFile(file) {
    if (!file || !file.type.startsWith('image/')) return;
    var r = new FileReader();
    r.onload = function() {
      try {
        localStorage.setItem(window.WALLPAPER_KEY, r.result);
        window.applyWallpaper(r.result);
        updateWallpaperPreview();
      } catch (e) { alert('壁纸过大或无法保存，请换一张较小的图片'); }
    };
    r.readAsDataURL(file);
  }
  if (wallpaperDZ) wallpaperDZ.onclick = function() { wallpaperInput.click(); };
  if (wallpaperInput) wallpaperInput.onchange = function() { setWallpaperFromFile(this.files[0]); this.value = ''; };
  if (wallpaperDZ) {
    wallpaperDZ.ondragover = function(e) { e.preventDefault(); this.classList.add('dragover'); };
    wallpaperDZ.ondragleave = function() { this.classList.remove('dragover'); };
    wallpaperDZ.ondrop = function(e) {
      e.preventDefault();
      this.classList.remove('dragover');
      var f = e.dataTransfer.files[0];
      if (f) setWallpaperFromFile(f);
    };
  }
  var btnClear = document.getElementById('btnClearWallpaper');
  if (btnClear) btnClear.onclick = function() {
    localStorage.removeItem(window.WALLPAPER_KEY);
    window.applyWallpaper(null);
    updateWallpaperPreview();
  };
  (function initThemeSelector() {
    var selector = document.getElementById('themeSelector');
    if (!selector) return;
    selector.querySelectorAll('input[name="theme"]').forEach(function(radio) {
      radio.onchange = function() { window.applyTheme(this.value); };
    });
  })();

  document.addEventListener('dblclick', function(e) {
    if (document.body.classList.contains('ui-hidden')) {
      document.body.classList.remove('ui-hidden');
      document.body.classList.add('ui-restoring');
      requestAnimationFrame(function() {
        requestAnimationFrame(function() {
          document.body.classList.remove('ui-restoring');
        });
      });
      return;
    }
    if (e.target.closest('button, a, input, select, textarea, .local-sidebar, .modal-overlay, .ctx-menu, section, header, .drop-zone, pre, .file-list, .breadcrumb, .sidebar-resize-handle, .sidebar-collapse-btn, .sidebar-expand-tab, .file-list-item, .nav a, label, [contenteditable]')) return;
    document.body.classList.add('ui-fade-out');
    setTimeout(function() {
      document.body.classList.add('ui-hidden');
      document.body.classList.remove('ui-fade-out');
    }, 220);
  });

  (function() {
    var SIDEBAR_WIDTH_KEY = 'eduflow_sidebar_width';
    var SIDEBAR_COLLAPSED_KEY = 'eduflow_sidebar_collapsed';
    var MIN_WIDTH = 200;
    var MAX_WIDTH = 480;
    var DEFAULT_WIDTH = 280;
    var root = document.documentElement;
    function getSidebarWidth() {
      var w = parseFloat(getComputedStyle(root).getPropertyValue('--sidebar-width'));
      return isNaN(w) ? DEFAULT_WIDTH : w;
    }
    function setSidebarWidth(px) {
      px = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, px));
      root.style.setProperty('--sidebar-width', px + 'px');
      try { localStorage.setItem(SIDEBAR_WIDTH_KEY, String(px)); } catch (e) {}
    }
    var localSidebar = document.getElementById('localSidebar');
    function setCollapsed(collapsed) {
      if (collapsed) {
        document.body.classList.add('sidebar-collapsed');
        if (localSidebar) localSidebar.classList.add('collapsed');
      } else {
        document.body.classList.remove('sidebar-collapsed');
        if (localSidebar) localSidebar.classList.remove('collapsed');
      }
      try { localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? '1' : '0'); } catch (e) {}
    }
    function isCollapsed() { return document.body.classList.contains('sidebar-collapsed'); }
    try {
      var savedW = localStorage.getItem(SIDEBAR_WIDTH_KEY);
      if (savedW != null) {
        var n = parseFloat(savedW);
        if (!isNaN(n)) root.style.setProperty('--sidebar-width', Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, n)) + 'px');
      }
      if (localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1') {
        document.body.classList.add('sidebar-collapsed');
        if (localSidebar) localSidebar.classList.add('collapsed');
      }
    } catch (e) {}
    var resizeHandle = document.getElementById('sidebarResizeHandle');
    if (resizeHandle) {
      resizeHandle.onmousedown = function(e) {
        if (isCollapsed()) return;
        e.preventDefault();
        var startX = e.clientX;
        var startW = getSidebarWidth();
        function onMove(ev) { setSidebarWidth(startW + (ev.clientX - startX)); }
        function onUp() {
          document.removeEventListener('mousemove', onMove);
          document.removeEventListener('mouseup', onUp);
        }
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
      };
    }
    var collapseBtn = document.getElementById('sidebarCollapseBtn');
    if (collapseBtn) collapseBtn.onclick = function() { setCollapsed(true); };
    var expandTab = document.getElementById('sidebarExpandTab');
    if (expandTab) expandTab.onclick = function() {
      setCollapsed(false);
      var w = DEFAULT_WIDTH;
      try { var s = localStorage.getItem(SIDEBAR_WIDTH_KEY); if (s != null) { var n = parseFloat(s); if (!isNaN(n)) w = n; } } catch (e) {}
      setSidebarWidth(w);
    };
    (function setupLeftSidebarSwipe() {
      if (!localSidebar) return;
      var dragPx = 0, touchStartX = null, wheelAccum = 0, wheelEndTimer = null;
      var COMMIT_RATIO = 0.35;
      var WHEEL_END_MS = 120;
      var transitionEase = 'cubic-bezier(0.16, 1, 0.3, 1)';
      function getWidth() { return localSidebar.getBoundingClientRect().width || 280; }
      function applyDrag(px) {
        localSidebar.style.transition = 'none';
        localSidebar.style.transform = 'translateX(-' + Math.max(0, Math.min(px, getWidth())) + 'px)';
      }
      function endDrag(commit) {
        if (commit) {
          localSidebar.style.transition = 'transform 0.25s ' + transitionEase;
          localSidebar.style.transform = '';
          setCollapsed(true);
        } else {
          localSidebar.style.transition = 'transform 0.3s ' + transitionEase;
          localSidebar.style.transform = 'translateX(0)';
          var onEnd = function() {
            localSidebar.removeEventListener('transitionend', onEnd);
            localSidebar.style.transition = '';
            localSidebar.style.transform = '';
          };
          localSidebar.addEventListener('transitionend', onEnd);
        }
        dragPx = 0;
        wheelAccum = 0;
        touchStartX = null;
      }
      localSidebar.addEventListener('wheel', function(e) {
        if (isCollapsed()) return;
        if (Math.abs(e.deltaX) < Math.abs(e.deltaY)) return;
        e.preventDefault();
        wheelAccum += -e.deltaX;
        wheelAccum = Math.max(0, Math.min(wheelAccum, getWidth()));
        applyDrag(wheelAccum);
        clearTimeout(wheelEndTimer);
        wheelEndTimer = setTimeout(function() {
          wheelEndTimer = null;
          var th = getWidth() * COMMIT_RATIO;
          endDrag(wheelAccum >= th);
        }, WHEEL_END_MS);
      }, { passive: false });
      localSidebar.addEventListener('touchstart', function(e) {
        touchStartX = e.touches[0].clientX;
        dragPx = 0;
      }, { passive: true });
      localSidebar.addEventListener('touchmove', function(e) {
        if (touchStartX == null || isCollapsed()) return;
        var dx = touchStartX - e.touches[0].clientX;
        dragPx = Math.max(0, Math.min(dx, getWidth()));
        applyDrag(dragPx);
        if (Math.abs(dx) > 8) e.preventDefault();
      }, { passive: false });
      localSidebar.addEventListener('touchend', function(e) {
        if (touchStartX == null) return;
        var th = getWidth() * COMMIT_RATIO;
        endDrag(dragPx >= th);
      }, { passive: true });
    })();
  })();
})();
