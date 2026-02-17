/* EduFlow 前端认证：登录/注册 UI、校验后继续 */
(function() {
  'use strict';
  function getAuthToken() { return window.getAuthToken ? window.getAuthToken() : ''; }
  function setAuthToken(t) { if (window.setAuthToken) window.setAuthToken(t); }
  function clearAuthToken() { if (window.clearAuthToken) window.clearAuthToken(); }
  function showAuthScreen() { if (window.showAuthScreen) window.showAuthScreen(); }
  function hideAuthScreen() { if (window.hideAuthScreen) window.hideAuthScreen(); }
  function syncWorkspaceFromUrl() { if (window.syncWorkspaceFromUrl) window.syncWorkspaceFromUrl(); }

  (function initAuthUI() {
    var authScreen = document.getElementById('authScreen');
    if (!authScreen) return;
    var loginForm = document.getElementById('loginForm');
    var registerForm = document.getElementById('registerForm');
    var loginMsg = document.getElementById('loginMsg');
    var registerMsg = document.getElementById('registerMsg');
    document.querySelectorAll('.auth-tab').forEach(function(btn) {
      btn.onclick = function() {
        document.querySelectorAll('.auth-tab').forEach(function(b) { b.classList.remove('active'); });
        btn.classList.add('active');
        var t = btn.getAttribute('data-tab');
        loginForm.style.display = t === 'login' ? 'block' : 'none';
        registerForm.style.display = t === 'register' ? 'block' : 'none';
        if (loginMsg) loginMsg.textContent = '';
        if (registerMsg) registerMsg.textContent = '';
      };
    });
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
    if (loginForm) {
      loginForm.onsubmit = async function(e) {
        e.preventDefault();
        var u = document.getElementById('loginUsername').value.trim();
        var p = document.getElementById('loginPassword').value;
        if (loginMsg) loginMsg.textContent = '';
        var base = (typeof window.API !== 'undefined' && window.API) ? window.API : (window.location.origin || '');
        try {
          var r = await fetch(base.replace(/\/$/, '') + '/api/auth/login', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: u, password: p })
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
        var u = document.getElementById('registerUsername').value.trim();
        var p = document.getElementById('registerPassword').value;
        var pAgain = document.getElementById('registerPasswordAgain').value;
        if (registerMsg) registerMsg.textContent = '';
        if (p !== pAgain) {
          if (registerMsg) registerMsg.textContent = '两次输入的密码不一致，请重新输入。';
          return;
        }
        var base = (typeof window.API !== 'undefined' && window.API) ? window.API : (window.location.origin || '');
        try {
          var r = await fetch(base.replace(/\/$/, '') + '/api/auth/register', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: u, password: p })
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
  })();

  (async function ensureAuthThenRun() {
    if (!getAuthToken()) { showAuthScreen(); return; }
    var ok = await window.checkAuth();
    if (!ok) return;
    var us = document.getElementById('authUserSpan');
    var logoutBtn = document.getElementById('btnLogout');
    if (window.AUTH_USER && us) { us.textContent = window.AUTH_USER.username; }
    if (logoutBtn) { logoutBtn.style.display = 'inline-block'; logoutBtn.onclick = function() { clearAuthToken(); location.reload(); }; }
    syncWorkspaceFromUrl();
  })();
})();
