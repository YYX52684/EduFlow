/* EduFlow 前端设置：设置弹窗、壁纸、LLM 配置、主题、左侧栏折叠与双击隐藏 */
(function() {
  'use strict';

  var settingsModal = document.getElementById('settingsModal');
  var btnSettings = document.getElementById('btnSettings');
  if (!settingsModal || !btnSettings) return;

  function updateWallpaperPreview() {
    var wrap = document.getElementById('wallpaperPreview');
    if (!wrap) return;
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
    window.apiFetch('/api/llm/config')
      .then(function(r) { return window.safeResponseJson(r); })
      .then(function(data) {
        var el;
        if ((el = document.getElementById('llmModelType'))) el.value = data.model_type || 'deepseek';
        if ((el = document.getElementById('llmApiKey'))) el.value = '';
        if ((el = document.getElementById('llmApiKeyMasked'))) el.textContent = data.has_api_key ? '已保存 Key: ' + (data.api_key_masked || '***') : '未设置';
        if ((el = document.getElementById('btnClearLlmApiKey'))) el.style.display = data.has_api_key ? '' : 'none';
        if ((el = document.getElementById('llmBaseUrl'))) el.value = data.base_url || '';
        if ((el = document.getElementById('llmModelName'))) el.value = data.model || '';
        if ((el = document.getElementById('llmCustomFields'))) el.style.display = (data.model_type === 'openai') ? 'block' : 'none';
      })
      .catch(function() {
        var el = document.getElementById('llmApiKeyMasked');
        if (el) el.textContent = '加载失败';
      });
  }

  var llmModelType = document.getElementById('llmModelType');
  if (llmModelType) {
    llmModelType.onchange = function() {
      var cf = document.getElementById('llmCustomFields');
      if (cf) cf.style.display = (this.value === 'openai') ? 'block' : 'none';
    };
  }

  var btnClearLlmApiKey = document.getElementById('btnClearLlmApiKey');
  if (btnClearLlmApiKey) {
    btnClearLlmApiKey.onclick = function() {
      var msgEl = document.getElementById('llmConfigMsg');
      msgEl.textContent = '清除中…';
      window.apiFetch('/api/llm/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: '' })
      })
        .then(function(r) { return window.safeResponseJson(r); })
        .then(function(data) {
          msgEl.textContent = '已清除工作区 API Key';
          document.getElementById('llmApiKey').value = '';
          loadLlmConfig();
        })
        .catch(function(e) {
          msgEl.textContent = '清除失败: ' + (e.message || e);
        });
    };
  }

  var btnSaveLlmConfig = document.getElementById('btnSaveLlmConfig');
  if (btnSaveLlmConfig) {
    btnSaveLlmConfig.onclick = function() {
      var payload = { model_type: document.getElementById('llmModelType').value };
      var key = document.getElementById('llmApiKey').value.trim();
      if (key) payload.api_key = key;
      if (document.getElementById('llmModelType').value === 'openai') {
        payload.base_url = document.getElementById('llmBaseUrl').value.trim();
        payload.model = document.getElementById('llmModelName').value.trim();
      }
      document.getElementById('llmConfigMsg').textContent = '保存中…';
      window.showLongTaskFeedback('保存 LLM 配置中…');
      window.apiFetch('/api/llm/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
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
  }

  btnSettings.onclick = function() {
    updateWallpaperPreview();
    loadLlmConfig();
    if (typeof window.openModal === 'function') {
      window.openModal(settingsModal, this);
    } else {
      settingsModal.classList.add('show');
      settingsModal.setAttribute('aria-hidden', 'false');
    }
  };

  var btnCloseSettings = document.getElementById('btnCloseSettings');
  if (btnCloseSettings) {
    btnCloseSettings.onclick = function() {
      if (typeof window.closeModal === 'function') window.closeModal(settingsModal);
    };
  }

  settingsModal.onclick = function(e) {
    if (e.target === settingsModal && typeof window.closeModal === 'function') {
      window.closeModal(settingsModal);
    }
  };

  (function initSettingsNav() {
    var navItems = settingsModal.querySelectorAll('.settings-nav-item');
    var pages = {
      llm: document.getElementById('settingsPageLlm'),
      wallpaper: document.getElementById('settingsPageWallpaper')
    };
    navItems.forEach(function(btn) {
      btn.onclick = function() {
        var pageId = this.getAttribute('data-settings-page');
        navItems.forEach(function(b) { b.classList.remove('active'); });
        this.classList.add('active');
        var keys = Object.keys(pages);
        for (var i = 0; i < keys.length; i++) {
          var k = keys[i];
          pages[k].classList.remove('active');
          if (k === pageId) pages[k].classList.add('active');
        }
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
      requestAnimationFrame(function() {
        requestAnimationFrame(layoutAndDraw);
      });
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
        if (typeof window.closeModal === 'function') window.closeModal(wallpaperEditorModal);
      }
    };
    r.readAsDataURL(file);
  }

  if (wallpaperDZ) {
    wallpaperDZ.onclick = function() {
      if (wallpaperInput) wallpaperInput.click();
    };
  }
  if (wallpaperInput) {
    wallpaperInput.onchange = function() {
      setWallpaperFromFile(this.files[0]);
      this.value = '';
    };
  }
  if (wallpaperDZ) {
    wallpaperDZ.ondragover = function(e) {
      e.preventDefault();
      this.classList.add('dragover');
    };
    wallpaperDZ.ondragleave = function() {
      this.classList.remove('dragover');
    };
    wallpaperDZ.ondrop = function(e) {
      e.preventDefault();
      this.classList.remove('dragover');
      var f = e.dataTransfer.files[0];
      if (f) setWallpaperFromFile(f);
    };
  }

  var btnClear = document.getElementById('btnClearWallpaper');
  if (btnClear) {
    btnClear.onclick = function() {
      localStorage.removeItem(window.WALLPAPER_KEY);
      window.applyWallpaper(null);
      updateWallpaperPreview();
    };
  }

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
      if (typeof window.closeModal === 'function' && wallpaperEditorModal) {
        window.closeModal(wallpaperEditorModal);
      }
    } catch (e) {
      alert('壁纸过大或无法保存，请换一张较小的图片');
    }
  }

  var btnWallpaperApply = document.getElementById('btnWallpaperApply');
  var btnWallpaperCancel = document.getElementById('btnWallpaperCancel');
  var btnCloseWallpaperEditor = document.getElementById('btnCloseWallpaperEditor');
  if (btnWallpaperApply) btnWallpaperApply.onclick = applyWallpaperFromEditor;
  if (btnWallpaperCancel) {
    btnWallpaperCancel.onclick = function() {
      if (typeof window.closeModal === 'function' && wallpaperEditorModal) window.closeModal(wallpaperEditorModal);
    };
  }
  if (btnCloseWallpaperEditor) {
    btnCloseWallpaperEditor.onclick = function() {
      if (typeof window.closeModal === 'function' && wallpaperEditorModal) window.closeModal(wallpaperEditorModal);
    };
  }
  if (wallpaperEditorModal) {
    wallpaperEditorModal.onclick = function(e) {
      if (e.target === wallpaperEditorModal && typeof window.closeModal === 'function') {
        window.closeModal(wallpaperEditorModal);
      }
    };
  }

  function onDblClick(e) {
    if (document.body.classList.contains('ui-hidden')) {
      document.body.classList.remove('ui-hidden');
      document.body.classList.add('ui-restoring');
      function removeRestoring() {
        document.body.classList.remove('ui-restoring');
      }
      requestAnimationFrame(function() {
        requestAnimationFrame(removeRestoring);
      });
      return;
    }
    var ignoreSelector = 'button, a, input, select, textarea, .modal-overlay, section, header, .drop-zone, pre, .file-list, .breadcrumb, .file-list-item, .nav a, label, [contenteditable]';
    if (e.target.closest(ignoreSelector)) return;
    document.body.classList.add('ui-fade-out');
    setTimeout(function() {
      document.body.classList.add('ui-hidden');
      document.body.classList.remove('ui-fade-out');
    }, 220);
  }

  document.addEventListener('dblclick', onDblClick);
})();
