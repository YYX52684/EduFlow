/* EduFlow 前端认证：登录/注册 UI、校验后继续 */
(function() {
  'use strict';
  function getAuthToken() { return window.getAuthToken ? window.getAuthToken() : ''; }
  function setAuthToken(t) { if (window.setAuthToken) window.setAuthToken(t); }
  function clearAuthToken() { if (window.clearAuthToken) window.clearAuthToken(); }
  function showAuthScreen() { if (window.showAuthScreen) window.showAuthScreen(); }
  function hideAuthScreen() { if (window.hideAuthScreen) window.hideAuthScreen(); }
  function syncWorkspaceFromUrl() { if (window.syncWorkspaceFromUrl) window.syncWorkspaceFromUrl(); }

  function getApiBase() {
    return (typeof window.API !== 'undefined' && window.API) ? window.API : (window.location.origin || '');
  }

  var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  function setValidationError(errorEl, message) {
    if (!errorEl) return;
    errorEl.textContent = message || '';
    errorEl.style.display = message ? 'block' : 'none';
  }
  function setInputInvalid(input, invalid) {
    if (!input) return;
    if (invalid) input.classList.add('input-invalid');
    else input.classList.remove('input-invalid');
  }

  (function initAuthUI() {
    var authScreen = document.getElementById('authScreen');
    if (!authScreen) return;
    var loginForm = document.getElementById('loginForm');
    var registerForm = document.getElementById('registerForm');
    var forgotForm = document.getElementById('forgotForm');
    var resetForm = document.getElementById('resetForm');
    var loginMsg = document.getElementById('loginMsg');
    var registerMsg = document.getElementById('registerMsg');
    var forgotMsg = document.getElementById('forgotMsg');
    var forgotSuccess = document.getElementById('forgotSuccess');
    var forgotResetLink = document.getElementById('forgotResetLink');
    var resetMsg = document.getElementById('resetMsg');

    function showTab(tab) {
      document.querySelectorAll('.auth-tab').forEach(function(b) {
        b.classList.toggle('active', b.getAttribute('data-tab') === tab);
      });
      var show = { login: loginForm, register: registerForm, forgot: forgotForm };
      if (loginForm) loginForm.style.display = tab === 'login' ? 'block' : 'none';
      if (registerForm) registerForm.style.display = tab === 'register' ? 'block' : 'none';
      if (forgotForm) forgotForm.style.display = tab === 'forgot' ? 'block' : 'none';
      if (resetForm) resetForm.style.display = 'none';
      if (loginMsg) loginMsg.textContent = '';
      if (registerMsg) registerMsg.textContent = '';
      if (forgotMsg) forgotMsg.textContent = '';
      if (forgotSuccess) { forgotSuccess.style.display = 'none'; forgotSuccess.textContent = ''; }
      if (forgotResetLink) { forgotResetLink.style.display = 'none'; forgotResetLink.innerHTML = ''; }
      [['loginIdentifier', 'loginIdentifierError'], ['registerEmail', 'registerEmailError'], ['registerPassword', 'registerPasswordError'], ['registerPasswordAgain', 'registerPasswordAgainError'], ['forgotIdentifier', 'forgotIdentifierError'], ['resetNewPassword', null], ['resetNewPasswordAgain', 'resetPasswordAgainError']].forEach(function(pair) {
        var err = document.getElementById(pair[1]);
        var inp = document.getElementById(pair[0]);
        if (err) setValidationError(err, '');
        if (inp) setInputInvalid(inp, false);
      });
    }

    function validateLoginIdentifier() {
      var v = (document.getElementById('loginIdentifier') && document.getElementById('loginIdentifier').value || '').trim();
      var errEl = document.getElementById('loginIdentifierError');
      var inp = document.getElementById('loginIdentifier');
      if (!v) { setValidationError(errEl, ''); setInputInvalid(inp, false); return true; }
      if (!EMAIL_RE.test(v)) { setValidationError(errEl, '请输入有效的邮箱地址'); setInputInvalid(inp, true); return false; }
      setValidationError(errEl, ''); setInputInvalid(inp, false); return true;
    }
    function validateRegisterEmail() {
      var v = (document.getElementById('registerEmail') && document.getElementById('registerEmail').value || '').trim();
      var errEl = document.getElementById('registerEmailError');
      var inp = document.getElementById('registerEmail');
      if (!v) { setValidationError(errEl, '请填写邮箱'); setInputInvalid(inp, true); return false; }
      if (!EMAIL_RE.test(v)) { setValidationError(errEl, '请输入有效的邮箱地址'); setInputInvalid(inp, true); return false; }
      setValidationError(errEl, ''); setInputInvalid(inp, false); return true;
    }
    function validateRegisterPassword() {
      var v = (document.getElementById('registerPassword') && document.getElementById('registerPassword').value || '');
      var errEl = document.getElementById('registerPasswordError');
      var inp = document.getElementById('registerPassword');
      if (v.length > 0 && v.length < 6) { setValidationError(errEl, '密码至少 6 位'); setInputInvalid(inp, true); return false; }
      setValidationError(errEl, ''); setInputInvalid(inp, false); return true;
    }
    function validateRegisterPasswordAgain() {
      var p = (document.getElementById('registerPassword') && document.getElementById('registerPassword').value || '');
      var v = (document.getElementById('registerPasswordAgain') && document.getElementById('registerPasswordAgain').value || '');
      var errEl = document.getElementById('registerPasswordAgainError');
      var inp = document.getElementById('registerPasswordAgain');
      if (v && v !== p) { setValidationError(errEl, '两次输入的密码不一致'); setInputInvalid(inp, true); return false; }
      setValidationError(errEl, ''); setInputInvalid(inp, false); return true;
    }
    function validateForgotIdentifier() {
      var v = (document.getElementById('forgotIdentifier') && document.getElementById('forgotIdentifier').value || '').trim();
      var errEl = document.getElementById('forgotIdentifierError');
      var inp = document.getElementById('forgotIdentifier');
      if (!v) { setValidationError(errEl, ''); setInputInvalid(inp, false); return true; }
      if (!EMAIL_RE.test(v)) { setValidationError(errEl, '请输入有效的邮箱地址'); setInputInvalid(inp, true); return false; }
      setValidationError(errEl, ''); setInputInvalid(inp, false); return true;
    }
    function validateResetPasswords() {
      var p = (document.getElementById('resetNewPassword') && document.getElementById('resetNewPassword').value || '');
      var v = (document.getElementById('resetNewPasswordAgain') && document.getElementById('resetNewPasswordAgain').value || '');
      var errEl = document.getElementById('resetPasswordAgainError');
      var inpAgain = document.getElementById('resetNewPasswordAgain');
      var inpFirst = document.getElementById('resetNewPassword');
      if (p.length > 0 && p.length < 6) { setValidationError(errEl, '密码至少 6 位'); setInputInvalid(inpFirst, true); setInputInvalid(inpAgain, false); return false; }
      if (v && v !== p) { setValidationError(errEl, '两次输入的密码不一致'); setInputInvalid(inpAgain, true); setInputInvalid(inpFirst, false); return false; }
      setValidationError(errEl, ''); setInputInvalid(inpAgain, false); setInputInvalid(inpFirst, false); return true;
    }

    var loginId = document.getElementById('loginIdentifier');
    if (loginId) { loginId.oninput = validateLoginIdentifier; loginId.onblur = validateLoginIdentifier; }
    var regEmail = document.getElementById('registerEmail');
    if (regEmail) { regEmail.oninput = validateRegisterEmail; regEmail.onblur = validateRegisterEmail; }
    var regPwd = document.getElementById('registerPassword');
    if (regPwd) { regPwd.oninput = function() { validateRegisterPassword(); validateRegisterPasswordAgain(); }; regPwd.onblur = validateRegisterPassword; }
    var regPwdAgain = document.getElementById('registerPasswordAgain');
    if (regPwdAgain) { regPwdAgain.oninput = validateRegisterPasswordAgain; regPwdAgain.onblur = validateRegisterPasswordAgain; }
    var forgotId = document.getElementById('forgotIdentifier');
    if (forgotId) { forgotId.oninput = validateForgotIdentifier; forgotId.onblur = validateForgotIdentifier; }
    var resetPwd = document.getElementById('resetNewPassword');
    if (resetPwd) { resetPwd.oninput = validateResetPasswords; resetPwd.onblur = validateResetPasswords; }
    var resetPwdAgain = document.getElementById('resetNewPasswordAgain');
    if (resetPwdAgain) { resetPwdAgain.oninput = validateResetPasswords; resetPwdAgain.onblur = validateResetPasswords; }

    document.querySelectorAll('.auth-tab').forEach(function(btn) {
      btn.onclick = function() {
        var t = btn.getAttribute('data-tab');
        showTab(t);
      };
    });

    var linkForgot = document.getElementById('linkForgotPassword');
    if (linkForgot) linkForgot.onclick = function(e) { e.preventDefault(); showTab('forgot'); };
    var linkBackToLogin = document.getElementById('linkBackToLogin');
    if (linkBackToLogin) linkBackToLogin.onclick = function(e) { e.preventDefault(); showTab('login'); };
    var btnSkipAuth = document.getElementById('btnSkipAuth');
    if (btnSkipAuth) {
      btnSkipAuth.onclick = function(e) {
        e.preventDefault();
        e.stopPropagation();
        try { sessionStorage.setItem('eduflow_skip_auth', '1'); } catch (err) {}
        hideAuthScreen();
        syncWorkspaceFromUrl();
      };
    }
    var linkResetBackToLogin = document.getElementById('linkResetBackToLogin');
    if (linkResetBackToLogin) linkResetBackToLogin.onclick = function(e) {
      e.preventDefault();
      history.replaceState(null, '', window.location.pathname || '/');
      showTab('login');
    };
    function togglePwdEye(btn, input) {
      if (!input) return;
      var isText = input.type === 'text';
      input.type = isText ? 'password' : 'text';
      btn.title = isText ? '显示密码' : '隐藏密码';
      btn.setAttribute('aria-label', btn.title);
    }
    var loginPwd = document.getElementById('loginPassword');
    var loginEye = document.getElementById('loginPwdEye');
    if (loginEye && loginPwd) { loginEye.onclick = function() { togglePwdEye(loginEye, loginPwd); }; }
    var regPwd = document.getElementById('registerPassword');
    var regPwdAgain = document.getElementById('registerPasswordAgain');
    var regEye = document.getElementById('regPwdEye');
    var regAgainEye = document.getElementById('regPwdAgainEye');
    if (regEye && regPwd) { regEye.onclick = function() { togglePwdEye(regEye, regPwd); }; }
    if (regAgainEye && regPwdAgain) { regAgainEye.onclick = function() { togglePwdEye(regAgainEye, regPwdAgain); }; }
    var resetPwd = document.getElementById('resetNewPassword');
    var resetPwdAgain = document.getElementById('resetNewPasswordAgain');
    var resetEye = document.getElementById('resetPwdEye');
    var resetAgainEye = document.getElementById('resetPwdAgainEye');
    if (resetEye && resetPwd) resetEye.onclick = function() { togglePwdEye(resetEye, resetPwd); };
    if (resetAgainEye && resetPwdAgain) resetAgainEye.onclick = function() { togglePwdEye(resetAgainEye, resetPwdAgain); };

    if (forgotForm) {
      forgotForm.onsubmit = async function(e) {
        e.preventDefault();
        if (!validateForgotIdentifier()) return;
        var id = document.getElementById('forgotIdentifier').value.trim();
        if (forgotMsg) forgotMsg.textContent = '';
        if (forgotSuccess) forgotSuccess.style.display = 'none';
        if (forgotResetLink) forgotResetLink.style.display = 'none';
        if (!id) { if (forgotMsg) forgotMsg.textContent = '请输入邮箱'; return; }
        var base = getApiBase().replace(/\/$/, '');
        try {
          var r = await fetch(base + '/api/auth/forgot-password', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ identifier: id })
          });
          var d = await r.json();
          if (d && d.message) {
            if (forgotSuccess) { forgotSuccess.textContent = d.message; forgotSuccess.style.display = 'block'; }
            if (d.reset_url) {
              if (forgotResetLink) {
                forgotResetLink.innerHTML = '<a href="' + d.reset_url + '" target="_blank" rel="noopener">' + d.reset_url + '</a>';
                forgotResetLink.style.display = 'block';
              }
            } else if (d.reset_token) {
              var origin = window.location.origin || '';
              // 使用查询参数形式，当前页路径 + ?reset_token=...
              var url = origin + (window.location.pathname || '/') + '?reset_token=' + encodeURIComponent(d.reset_token);
              if (forgotResetLink) {
                forgotResetLink.innerHTML = '重置链接（请勿泄露）：<br><a href="' + url + '">' + url + '</a>';
                forgotResetLink.style.display = 'block';
              }
            }
          }
          if (d && d.error && forgotMsg) forgotMsg.textContent = d.message || '请求失败';
        } catch (err) { if (forgotMsg) forgotMsg.textContent = '网络错误'; }
      };
    }

    if (resetForm) {
      resetForm.onsubmit = async function(e) {
        e.preventDefault();
        if (!validateResetPasswords()) return;
        var tokenEl = document.getElementById('resetToken');
        var token = (tokenEl && tokenEl.value) ? tokenEl.value.trim() : '';
        var p = document.getElementById('resetNewPassword').value;
        var pAgain = document.getElementById('resetNewPasswordAgain').value;
        if (resetMsg) resetMsg.textContent = '';
        if (p !== pAgain) { if (resetMsg) resetMsg.textContent = '两次输入的密码不一致'; return; }
        if (p.length < 6) { if (resetMsg) resetMsg.textContent = '密码至少 6 位'; return; }
        if (!token) { if (resetMsg) resetMsg.textContent = '重置链接已失效，请重新申请'; return; }
        var base = getApiBase().replace(/\/$/, '');
        try {
          var r = await fetch(base + '/api/auth/reset-password', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: token, new_password: p })
          });
          var d = await r.json();
          if (d && d.message && !d.error) {
            if (resetMsg) { resetMsg.textContent = ''; resetMsg.classList.remove('err'); resetMsg.classList.add('ok'); resetMsg.textContent = '密码已重置，正在跳转登录…'; }
            history.replaceState(null, '', window.location.pathname || '/');
            setTimeout(function() { showTab('login'); window.location.reload(); }, 800);
            return;
          }
          if (resetMsg) resetMsg.textContent = (d && d.message) ? d.message : '重置失败';
        } catch (err) { if (resetMsg) resetMsg.textContent = '网络错误'; }
      };
    }

    if (loginForm) {
      loginForm.onsubmit = async function(e) {
        e.preventDefault();
        if (!validateLoginIdentifier()) return;
        var id = document.getElementById('loginIdentifier').value.trim();
        var p = document.getElementById('loginPassword').value;
        if (loginMsg) loginMsg.textContent = '';
        var base = getApiBase().replace(/\/$/, '');
        try {
          var r = await fetch(base + '/api/auth/login', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ identifier: id, password: p })
          });
          var d = await r.json();
          if (d && d.token && d.workspace_id) {
            setAuthToken(d.token);
            location.replace('/');
            return;
          }
          if (loginMsg) loginMsg.textContent = (d && d.message) ? d.message : '登录失败';
        } catch (err) { if (loginMsg) loginMsg.textContent = '网络错误'; }
      };
    }
    if (registerForm) {
      registerForm.onsubmit = async function(e) {
        e.preventDefault();
        if (!validateRegisterEmail() || !validateRegisterPassword() || !validateRegisterPasswordAgain()) return;
        var email = document.getElementById('registerEmail').value.trim();
        var p = document.getElementById('registerPassword').value;
        var pAgain = document.getElementById('registerPasswordAgain').value;
        if (registerMsg) registerMsg.textContent = '';
        var base = getApiBase().replace(/\/$/, '');
        var body = { email: email, password: p };
        try {
          var r = await fetch(base + '/api/auth/register', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
          });
          var d = await r.json();
          if (d && d.token && d.workspace_id) {
            setAuthToken(d.token);
            location.replace('/');
            return;
          }
          if (registerMsg) registerMsg.textContent = (d && d.message) ? d.message : '注册失败';
        } catch (err) { if (registerMsg) registerMsg.textContent = '网络错误'; }
      };
    }

    function getResetTokenFromUrl() {
      var search = location.search || '';
      var hash = location.hash || '';
      // 先从查询参数中找 ?reset_token=...，兼容 /?reset_token=xxx
      var m = search.match(/[?&]reset_token=([^&]+)/);
      if (!m) {
        // 兼容历史的 #reset_token=... 形式
        m = hash.match(/(?:#|[&?])reset_token=([^&]+)/);
      }
      return m ? decodeURIComponent(m[1]) : '';
    }
    var urlResetToken = getResetTokenFromUrl();
    if (urlResetToken && resetForm) {
      var tokenInput = document.getElementById('resetToken');
      if (tokenInput) tokenInput.value = urlResetToken;
      if (loginForm) loginForm.style.display = 'none';
      if (registerForm) registerForm.style.display = 'none';
      if (forgotForm) forgotForm.style.display = 'none';
      resetForm.style.display = 'block';
      document.querySelectorAll('.auth-tab').forEach(function(b) { b.classList.remove('active'); });
    }
  })();

  /** 根据是否已登录更新头部：登录按钮 / 用户名、历史文件、退出 */
  function updateAuthHeader(authenticated) {
    var us = document.getElementById('authUserSpan');
    var logoutBtn = document.getElementById('btnLogout');
    var historyFilesBtn = document.getElementById('btnHistoryFiles');
    var showAuthBtn = document.getElementById('btnShowAuth');
    if (showAuthBtn) showAuthBtn.style.display = authenticated ? 'none' : 'inline-block';
    if (us) us.style.display = authenticated ? 'inline' : 'none';
    if (us && window.AUTH_USER) us.textContent = window.AUTH_USER.username || '';
    if (logoutBtn) {
      logoutBtn.style.display = authenticated ? 'inline-block' : 'none';
      logoutBtn.onclick = function() { clearAuthToken(); location.reload(); };
    }
    if (historyFilesBtn) historyFilesBtn.style.display = authenticated ? 'inline-block' : 'none';
  }

  (async function initAuthOptional() {
    var ok = await window.checkAuth();
    updateAuthHeader(!!ok);
    if (ok) syncWorkspaceFromUrl();
    var showAuthBtn = document.getElementById('btnShowAuth');
    if (showAuthBtn) showAuthBtn.onclick = function() { showAuthScreen(); };
    var authScreen = document.getElementById('authScreen');
    if (authScreen) {
      authScreen.onclick = function(e) { if (e.target === authScreen) hideAuthScreen(); };
    }
    window.AUTH_READY = true;
    try { document.dispatchEvent(new CustomEvent('eduflow:authReady')); } catch (e) {}
  })();
})();
