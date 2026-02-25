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
  var wallpaperEditorModal = document.getElementById('wallpaperEditorModal');
  var wallpaperEditorViewport = document.getElementById('wallpaperEditorViewport');
  var wallpaperEditorCanvas = document.getElementById('wallpaperEditorCanvas');
  var wallpaperZoomRange = document.getElementById('wallpaperZoomRange');
  var wallpaperZoomValue = document.getElementById('wallpaperZoomValue');
  var wallpaperImg = null;
  var wallpaperState = {
    scale: 1,
    minScale: 1,
    maxScale: 3,
    offsetX: 0,
    offsetY: 0,
    dragging: false,
    dragStartX: 0,
    dragStartY: 0,
    startOffsetX: 0,
    startOffsetY: 0
  };

  function drawWallpaperEditor() {
    if (!wallpaperImg || !wallpaperEditorCanvas || !wallpaperEditorViewport) return;
    var ctx = wallpaperEditorCanvas.getContext('2d');
    if (!ctx) return;
    var dpr = window.devicePixelRatio || 1;
    var vw = wallpaperEditorViewport.clientWidth || 480;
    var vh = wallpaperEditorViewport.clientHeight || 270;
    var needResize = (wallpaperEditorCanvas.width !== vw * dpr) || (wallpaperEditorCanvas.height !== vh * dpr);
    if (needResize) {
      wallpaperEditorCanvas.width = vw * dpr;
      wallpaperEditorCanvas.height = vh * dpr;
      wallpaperEditorCanvas.style.width = vw + 'px';
      wallpaperEditorCanvas.style.height = vh + 'px';
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, vw, vh);
    ctx.save();
    ctx.translate(wallpaperState.offsetX, wallpaperState.offsetY);
    ctx.scale(wallpaperState.scale, wallpaperState.scale);
    ctx.drawImage(wallpaperImg, 0, 0);
    ctx.restore();
  }

  function initWallpaperEditor(dataUrl) {
    if (!wallpaperEditorCanvas || !wallpaperEditorViewport) return;
    wallpaperEditorViewport.classList.remove('loaded');
    wallpaperImg = new Image();
    wallpaperImg.onload = function() {
      function layoutAndDraw() {
        var vw = wallpaperEditorViewport.clientWidth || 480;
        var vh = wallpaperEditorViewport.clientHeight || 270;
        var scaleX = vw / wallpaperImg.width;
        var scaleY = vh / wallpaperImg.height;
        var minScale = Math.max(scaleX, scaleY);
        wallpaperState.minScale = minScale;
        wallpaperState.maxScale = minScale * 3;
        wallpaperState.scale = minScale;
        wallpaperState.offsetX = (vw - wallpaperImg.width * wallpaperState.scale) / 2;
        wallpaperState.offsetY = (vh - wallpaperImg.height * wallpaperState.scale) / 2;
        if (wallpaperZoomRange) {
          wallpaperZoomRange.min = 100;
          wallpaperZoomRange.max = 300;
          wallpaperZoomRange.value = 100;
        }
        if (wallpaperZoomValue) wallpaperZoomValue.textContent = '100%';
        drawWallpaperEditor();
        wallpaperEditorViewport.classList.add('loaded');
      }
      requestAnimationFrame(function() { requestAnimationFrame(layoutAndDraw); });
    };
    wallpaperImg.src = dataUrl;
  }

  function updateWallpaperScaleFromSlider() {
    if (!wallpaperZoomRange) return;
    var pct = parseFloat(wallpaperZoomRange.value || '100');
    if (isNaN(pct)) pct = 100;
    var factor = pct / 100;
    var scale = wallpaperState.minScale * factor;
    if (scale < wallpaperState.minScale * 0.5) scale = wallpaperState.minScale * 0.5;
    if (scale > wallpaperState.maxScale) scale = wallpaperState.maxScale;
    wallpaperState.scale = scale;
    if (wallpaperZoomValue) {
      var disp = Math.round((scale / wallpaperState.minScale) * 100);
      wallpaperZoomValue.textContent = disp + '%';
    }
    drawWallpaperEditor();
  }

  function setWallpaperFromFile(file) {
    if (!file || !file.type.startsWith('image/')) return;
    if (!wallpaperEditorModal || !window.openModal) return;
    window.openModal(wallpaperEditorModal, null);
    var r = new FileReader();
    r.onload = function() {
      try {
        initWallpaperEditor(r.result);
      } catch (e) {
        alert('无法加载壁纸，请换一张图片');
        if (window.closeModal) window.closeModal(wallpaperEditorModal);
      }
    };
    r.readAsDataURL(file);
  }
  if (wallpaperDZ) wallpaperDZ.onclick = function() { if (wallpaperInput) wallpaperInput.click(); };
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

  if (wallpaperEditorCanvas && wallpaperEditorViewport) {
    wallpaperEditorCanvas.onmousedown = function(e) {
      wallpaperState.dragging = true;
      wallpaperState.dragStartX = e.clientX;
      wallpaperState.dragStartY = e.clientY;
      wallpaperState.startOffsetX = wallpaperState.offsetX;
      wallpaperState.startOffsetY = wallpaperState.offsetY;
      wallpaperEditorViewport.classList.add('dragging');
    };
    window.addEventListener('mousemove', function(e) {
      if (!wallpaperState.dragging) return;
      var dx = e.clientX - wallpaperState.dragStartX;
      var dy = e.clientY - wallpaperState.dragStartY;
      wallpaperState.offsetX = wallpaperState.startOffsetX + dx;
      wallpaperState.offsetY = wallpaperState.startOffsetY + dy;
      drawWallpaperEditor();
    });
    window.addEventListener('mouseup', function() {
      if (!wallpaperState.dragging) return;
      wallpaperState.dragging = false;
      wallpaperEditorViewport.classList.remove('dragging');
    });
  }

  if (wallpaperZoomRange) {
    wallpaperZoomRange.oninput = updateWallpaperScaleFromSlider;
  }
  var btnZoomOut = document.getElementById('btnWallpaperZoomOut');
  var btnZoomIn = document.getElementById('btnWallpaperZoomIn');
  if (btnZoomOut && wallpaperZoomRange) {
    btnZoomOut.onclick = function() {
      var v = parseFloat(wallpaperZoomRange.value || '100');
      if (isNaN(v)) v = 100;
      wallpaperZoomRange.value = String(Math.max(50, v - 10));
      updateWallpaperScaleFromSlider();
    };
  }
  if (btnZoomIn && wallpaperZoomRange) {
    btnZoomIn.onclick = function() {
      var v = parseFloat(wallpaperZoomRange.value || '100');
      if (isNaN(v)) v = 100;
      wallpaperZoomRange.value = String(Math.min(300, v + 10));
      updateWallpaperScaleFromSlider();
    };
  }

  function applyWallpaperFromEditor() {
    if (!wallpaperEditorCanvas) return;
    try {
      var dataUrl = wallpaperEditorCanvas.toDataURL('image/jpeg', 0.9);
      localStorage.setItem(window.WALLPAPER_KEY, dataUrl);
      window.applyWallpaper(dataUrl);
      updateWallpaperPreview();
      if (window.closeModal && wallpaperEditorModal) window.closeModal(wallpaperEditorModal);
    } catch (e) {
      alert('壁纸过大或无法保存，请换一张较小的图片');
    }
  }
  var btnWallpaperApply = document.getElementById('btnWallpaperApply');
  var btnWallpaperCancel = document.getElementById('btnWallpaperCancel');
  var btnCloseWallpaperEditor = document.getElementById('btnCloseWallpaperEditor');
  if (btnWallpaperApply) btnWallpaperApply.onclick = applyWallpaperFromEditor;
  if (btnWallpaperCancel) btnWallpaperCancel.onclick = function() {
    if (window.closeModal && wallpaperEditorModal) window.closeModal(wallpaperEditorModal);
  };
  if (btnCloseWallpaperEditor) btnCloseWallpaperEditor.onclick = function() {
    if (window.closeModal && wallpaperEditorModal) window.closeModal(wallpaperEditorModal);
  };
  if (wallpaperEditorModal) {
    wallpaperEditorModal.onclick = function(e) {
      if (e.target === wallpaperEditorModal && window.closeModal) window.closeModal(wallpaperEditorModal);
    };
  }

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
