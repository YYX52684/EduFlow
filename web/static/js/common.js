/* EduFlow 前端公共：常量、模态框、认证存读、工作区、API、壁纸与主题 */
(function() {
  'use strict';
  window.API = window.API || '';
  window.WALLPAPER_KEY = 'eduflow_wallpaper';
  window.AUTH_TOKEN_KEY = 'eduflow_token';
  window.WALLPAPER_OVERLAY = 'linear-gradient(rgba(245, 240, 230, 0.88), rgba(245, 240, 230, 0.9)), ';
  window.lastUploadData = null;
  window.lastScriptFile = null;

  var FOCUSABLE_SELECTOR = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
  function getFocusables(container) {
    if (!container) return [];
    var list = container.querySelectorAll(FOCUSABLE_SELECTOR);
    return Array.prototype.filter.call(list, function(el) { return el.offsetParent !== null && !el.hasAttribute('aria-hidden'); });
  }
  function setupModalFocusTrap(overlay, onEscape) {
    function handleKeydown(e) {
      if (e.key === 'Escape') {
        e.preventDefault();
        if (onEscape) onEscape();
        return;
      }
      if (e.key !== 'Tab') return;
      var panel = overlay.querySelector('.modal-panel');
      if (!panel) return;
      var focusables = getFocusables(panel);
      if (focusables.length === 0) return;
      var first = focusables[0];
      var last = focusables[focusables.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
    overlay._modalKeydown = handleKeydown;
    document.addEventListener('keydown', handleKeydown);
  }
  function removeModalFocusTrap(overlay) {
    if (overlay._modalKeydown) {
      document.removeEventListener('keydown', overlay._modalKeydown);
      overlay._modalKeydown = null;
    }
  }
  function openModal(overlay, triggerButton) {
    if (!overlay) return;
    overlay._modalPreviousFocus = triggerButton && document.activeElement ? document.activeElement : null;
    overlay.classList.add('show');
    overlay.setAttribute('aria-hidden', 'false');
    var panel = overlay.querySelector('.modal-panel');
    var focusables = getFocusables(panel);
    if (focusables.length > 0) {
      setTimeout(function() { focusables[0].focus(); }, 50);
    }
    setupModalFocusTrap(overlay, function() { closeModal(overlay); });
  }
  function closeModal(overlay) {
    if (!overlay) return;
    overlay.classList.remove('show');
    overlay.setAttribute('aria-hidden', 'true');
    removeModalFocusTrap(overlay);
    var prev = overlay._modalPreviousFocus;
    if (prev && typeof prev.focus === 'function') {
      setTimeout(function() { prev.focus(); }, 50);
    }
    overlay._modalPreviousFocus = null;
  }
  window.getFocusables = getFocusables;
  window.setupModalFocusTrap = setupModalFocusTrap;
  window.removeModalFocusTrap = removeModalFocusTrap;
  window.openModal = openModal;
  window.closeModal = closeModal;

  function showLongTaskFeedback(message) {
    var el = document.getElementById('globalLoadingOverlay');
    var text = document.getElementById('globalLoadingText');
    if (el) { el.classList.add('show'); el.setAttribute('aria-busy', 'true'); }
    if (text) text.textContent = message || '处理中…';
  }
  function hideLongTaskFeedback() {
    var el = document.getElementById('globalLoadingOverlay');
    if (el) { el.classList.remove('show'); el.setAttribute('aria-busy', 'false'); }
  }
  window.showLongTaskFeedback = showLongTaskFeedback;
  window.hideLongTaskFeedback = hideLongTaskFeedback;

  /** 统一按钮加载态：传入 button 元素与 true/false，会切换 .is-loading 并 disabled */
  function setButtonLoading(btn, loading) {
    if (!btn) return;
    if (loading) {
      btn.classList.add('is-loading');
      btn.disabled = true;
    } else {
      btn.classList.remove('is-loading');
      btn.disabled = false;
    }
  }
  window.setButtonLoading = setButtonLoading;

  function getAuthToken() { try { return localStorage.getItem(window.AUTH_TOKEN_KEY) || ''; } catch (e) { return ''; } }
  function setAuthToken(t) { try { localStorage.setItem(window.AUTH_TOKEN_KEY, t || ''); } catch (e) {} }
  function clearAuthToken() { try { localStorage.removeItem(window.AUTH_TOKEN_KEY); } catch (e) {} }
  function showAuthScreen() { var el = document.getElementById('authScreen'); if (el) el.classList.remove('hidden'); }
  function hideAuthScreen() { var el = document.getElementById('authScreen'); if (el) el.classList.add('hidden'); }
  /** 校验当前 token 是否有效，不强制显示登录屏（登录为可选功能） */
  async function checkAuth() {
    var token = getAuthToken();
    if (!token) { return false; }
    var base = (typeof window.API !== 'undefined' && window.API) ? window.API : (window.location.origin || '');
    var url = base.replace(/\/$/, '') + '/api/auth/me';
    try {
      var r = await fetch(url, { headers: { 'Authorization': 'Bearer ' + token } });
      if (r.status === 401) { clearAuthToken(); return false; }
      var d = await r.json();
      if (d && d.user) { window.AUTH_USER = d.user; window.AUTH_WORKSPACE_ID = d.workspace_id || ''; return true; }
    } catch (e) {}
    clearAuthToken();
    return false;
  }
  window.getAuthToken = getAuthToken;
  window.setAuthToken = setAuthToken;
  window.clearAuthToken = clearAuthToken;
  window.showAuthScreen = showAuthScreen;
  window.hideAuthScreen = hideAuthScreen;
  window.checkAuth = checkAuth;

  function syncWorkspaceFromUrl() {
    var m = /^\/w\/([^/]+)\/?$/.exec(location.pathname);
    if (m) {
      try {
        window.WORKSPACE_ID = decodeURIComponent(m[1]);
      } catch (e) {
        window.WORKSPACE_ID = m[1];
      }
    } else {
      window.WORKSPACE_ID = (window.AUTH_WORKSPACE_ID || 'demo');
    }
    var wl = document.getElementById('currentWorkspaceLabel');
    if (wl) wl.textContent = getWorkspaceId();
    if (getAuthToken() && typeof window.refreshWorkspaceFileList === 'function') window.refreshWorkspaceFileList();
  }
  function getWorkspaceId() { return window.WORKSPACE_ID || ''; }
  window.syncWorkspaceFromUrl = syncWorkspaceFromUrl;
  window.getWorkspaceId = getWorkspaceId;

  function encodeWorkspaceIdForHeader(id) {
    if (!id) return '';
    try {
      return btoa(unescape(encodeURIComponent(id)));
    } catch (e) {
      return /^[\x00-\x7F]*$/.test(id) ? id : '';
    }
  }

  /** 全局 Toast：API 失败时统一提示，不打断控制台 */
  var toastQueue = [];
  var toastVisible = false;
  function getToastContainer() {
    var id = 'eduflow-toast-container';
    var el = document.getElementById(id);
    if (!el) {
      el = document.createElement('div');
      el.id = id;
      el.className = 'toast-container';
      el.setAttribute('aria-live', 'polite');
      document.body.appendChild(el);
    }
    return el;
  }
  function showToast(message, type) {
    type = type || 'error';
    var container = getToastContainer();
    var item = document.createElement('div');
    item.className = 'toast-item toast--' + type;
    item.textContent = message || '请求失败';
    container.appendChild(item);
    toastVisible = true;
    requestAnimationFrame(function() { item.classList.add('toast--show'); });
    setTimeout(function() {
      item.classList.remove('toast--show');
      setTimeout(function() {
        if (item.parentNode) item.parentNode.removeChild(item);
        toastVisible = container.children.length > 0;
      }, 300);
    }, 3500);
  }
  window.showToast = showToast;

  /** 防抖：用于搜索框等，减少无效调用 */
  function debounce(fn, ms) {
    var t;
    return function() {
      var a = arguments;
      var self = this;
      clearTimeout(t);
      t = setTimeout(function() { fn.apply(self, a); }, ms);
    };
  }
  window.debounce = debounce;

  function apiFetch(path, options) {
    options = options || {};
    options.headers = options.headers || {};
    var token = getAuthToken();
    if (token) options.headers['Authorization'] = 'Bearer ' + token;
    var wid = getWorkspaceId();
    var encoded = encodeWorkspaceIdForHeader(wid);
    options.headers['X-Workspace-Id'] = encoded || (wid && /^[\x00-\x7F]*$/.test(wid) ? wid : '');
    var base = (typeof window.API !== 'undefined' && window.API) ? window.API : (window.location.origin || '');
    var url = path.startsWith('http') ? path : (base.replace(/\/$/, '') + (path.startsWith('/') ? path : '/' + path));
    return fetch(url, options)
      .then(function(r) {
        if (!r.ok) {
          r.clone().text().then(function(text) {
            var msg = '请求失败';
            try {
              var d = JSON.parse(text);
              msg = getUserFriendlyLlmErrorMessage(d) || d.message || d.detail || msg;
            } catch (e) { if (text) msg = text.slice(0, 120); }
            showToast(msg, 'error');
          }).catch(function() { showToast('请求失败', 'error'); });
        }
        return r;
      })
      .catch(function(e) {
        showToast(e.message || '网络错误，请检查连接', 'error');
        throw e;
      });
  }
  function safeResponseJson(r) {
    return r.text().then(function(text) {
      try { return JSON.parse(text); } catch (e) { return { detail: text || r.statusText || 'Invalid response' }; }
    });
  }

  /** 将 API 错误体转为用户可见的简短文案，避免把整段 details/reason 堆给用户。 */
  function getUserFriendlyLlmErrorMessage(d) {
    if (!d || typeof d !== 'object') return '';
    var code = d.code || (d.error_detail && d.error_detail.code);
    var detailsReason = (d.details && d.details.reason) || (d.error_detail && d.error_detail.details && d.error_detail.details.reason) || '';
    var reasonStr = String(detailsReason);
    if (code === 'LLM_ERROR' && (reasonStr.indexOf('401') !== -1 || reasonStr.indexOf('key') !== -1 || reasonStr.indexOf('Key') !== -1 || reasonStr.indexOf('当前key') !== -1)) {
      return '未设置 API Key 或 Key 无效，请在「设置」中填写或更换。';
    }
    if (code === 'CONFIG_ERROR') return d.message || '未配置完整的 LLM 信息，请在「设置」中填写 API Key 与模型。';
    return d.message || (d.error_detail && d.error_detail.message) || '';
  }

  window.encodeWorkspaceIdForHeader = encodeWorkspaceIdForHeader;
  window.apiFetch = apiFetch;
  window.safeResponseJson = safeResponseJson;
  window.getUserFriendlyLlmErrorMessage = getUserFriendlyLlmErrorMessage;

  function showWorkspaceToast(id) {
    var wl = document.getElementById('currentWorkspaceLabel');
    if (!wl) return;
    wl.textContent = '已切换: ' + id;
    setTimeout(function() { wl.textContent = id; }, 2000);
  }
  window.showWorkspaceToast = showWorkspaceToast;

  (function initCollapsibleSections() {
    var KEY = 'eduflow_sections_collapsed';
    try {
      var saved = JSON.parse(localStorage.getItem(KEY) || '{}');
    } catch (e) { var saved = {}; }
    document.querySelectorAll('.collapsible-section').forEach(function(el) {
      var id = el.dataset.section;
      var header = el.querySelector('.section-header');
      if (!header) return;
      if (saved[id]) el.classList.add('collapsed');
      header.setAttribute('aria-expanded', el.classList.contains('collapsed') ? 'false' : 'true');
      header.onclick = function() {
        el.classList.toggle('collapsed');
        header.setAttribute('aria-expanded', el.classList.contains('collapsed') ? 'false' : 'true');
        try {
          saved[id] = el.classList.contains('collapsed');
          localStorage.setItem(KEY, JSON.stringify(saved));
        } catch (e) {}
      };
      header.onkeydown = function(e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); header.click(); }
      };
    });
  })();

  function applyWallpaper(dataUrl) {
    if (!dataUrl) {
      document.body.style.backgroundImage = '';
      document.body.style.backgroundSize = '';
      return;
    }
    document.body.style.backgroundImage = window.WALLPAPER_OVERLAY + 'url(' + dataUrl + ')';
    document.body.style.backgroundSize = 'cover';
    document.body.style.backgroundPosition = 'center';
    document.body.style.backgroundAttachment = 'fixed';
  }
  function loadWallpaper() {
    try {
      var dataUrl = localStorage.getItem(window.WALLPAPER_KEY);
      if (dataUrl) applyWallpaper(dataUrl);
    } catch (e) {}
  }
  window.applyWallpaper = applyWallpaper;
  loadWallpaper();

  var THEME_KEY = 'eduflow_theme';
  function applyTheme(id) {
    var root = document.documentElement;
    if (!id || id === 'natsume') root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', id);
    try { localStorage.setItem(THEME_KEY, id && id !== 'natsume' ? id : 'natsume'); } catch (e) {}
  }
  function loadTheme() {
    try {
      var saved = localStorage.getItem(THEME_KEY) || 'natsume';
      if (saved !== 'natsume') document.documentElement.setAttribute('data-theme', saved);
      var selector = document.getElementById('themeSelector');
      if (selector) {
        var radio = selector.querySelector('input[value="' + saved + '"]');
        if (radio) radio.checked = true;
        else { var def = selector.querySelector('input[value="natsume"]'); if (def) def.checked = true; }
      }
    } catch (e) {}
  }
  window.THEME_KEY = THEME_KEY;
  window.applyTheme = applyTheme;
  loadTheme();

  (function ensureWorkspaceInUrl() {
    syncWorkspaceFromUrl();
    window.addEventListener('popstate', syncWorkspaceFromUrl);
    document.addEventListener('visibilitychange', function() {
      if (document.visibilityState === 'visible') syncWorkspaceFromUrl();
    });
  })();
})();
