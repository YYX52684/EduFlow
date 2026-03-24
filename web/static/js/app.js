    /* 使用 common.js / auth.js / settings.js 提供的全局 API；仅保留应用逻辑 */
    /** 从接口响应中取可安全展示给用户的错误文案，无则用 fallback */
    function getUserMsg(d, fallback) {
      if (d && typeof d === 'object' && (d.user_message || d.message)) return String(d.user_message || d.message);
      return fallback;
    }
    var handleStack = [];
    var pathNames = [];
    var treeRoot = null;
    var ALLOWED_SCRIPT_EXT = ['.md', '.docx', '.doc', '.pdf', '.json'];
    var IDB_NAME = 'EduFlowIDB';
    var IDB_STORE = 'handles';
    var LAST_DIR_KEY = 'lastDir';

    function openIDB() {
      return new Promise(function(res, rej) {
        var r = indexedDB.open(IDB_NAME, 1);
        r.onerror = function() { rej(r.error); };
        r.onsuccess = function() { res(r.result); };
        r.onupgradeneeded = function() {
          if (!r.result.objectStoreNames.contains(IDB_STORE)) r.result.createObjectStore(IDB_STORE);
        };
      });
    }
    function saveLastDir(handle) {
      openIDB().then(function(db) {
        return new Promise(function(res, rej) {
          var t = db.transaction(IDB_STORE, 'readwrite');
          t.objectStore(IDB_STORE).put(handle, LAST_DIR_KEY);
          t.oncomplete = res;
          t.onerror = rej;
        });
      }).catch(function() {});
    }
    async function restoreLastDir() {
      try {
        if (typeof showDirectoryPicker !== 'function') return;
        var db = await openIDB();
        var handle = await new Promise(function(res, rej) {
          var t = db.transaction(IDB_STORE, 'readonly');
          var req = t.objectStore(IDB_STORE).get(LAST_DIR_KEY);
          req.onsuccess = function() { res(req.result); };
          t.onerror = function() { rej(t.error); };
        });
        if (!handle || typeof handle.queryPermission !== 'function') return;
        var state = await handle.queryPermission({ mode: 'read' });
        if (state === 'granted') {
          treeRoot = { name: handle.name, handle: handle, kind: 'dir', children: null, expanded: true };
          await loadTreeChildren(treeRoot);
          renderTree();
          return;
        }
        if (state === 'prompt') {
          state = await handle.requestPermission({ mode: 'read' });
          if (state === 'granted') {
            treeRoot = { name: handle.name, handle: handle, kind: 'dir', children: null, expanded: true };
            await loadTreeChildren(treeRoot);
            renderTree();
            return;
          }
        }
        var db2 = await openIDB();
        await new Promise(function(res, rej) {
          var t = db2.transaction(IDB_STORE, 'readwrite');
          t.objectStore(IDB_STORE).delete(LAST_DIR_KEY);
          t.oncomplete = res;
          t.onerror = rej;
        });
      } catch (e) {}
    }

    async function loadDirEntries(handle) {
      var dirs = [], files = [];
      for (var it = handle.entries(); true;) {
        var next = await it.next();
        if (next.done) break;
        var name = next.value[0];
        var entry = next.value[1];
        if (entry.kind === 'directory') dirs.push({ name: name, handle: entry });
        else if (ALLOWED_SCRIPT_EXT.some(function(ext) { return name.toLowerCase().endsWith(ext); }))
          files.push({ name: name, handle: entry });
      }
      dirs.sort(function(a, b) { return a.name.localeCompare(b.name); });
      files.sort(function(a, b) { return a.name.localeCompare(b.name); });
      return { dirs: dirs, files: files };
    }
    async function loadTreeChildren(dirNode) {
      if (dirNode.children !== null) return;
      var ent = await loadDirEntries(dirNode.handle);
      dirNode.children = [];
      ent.dirs.forEach(function(d) {
        dirNode.children.push({ name: d.name, handle: d.handle, kind: 'dir', children: null, expanded: false });
      });
      ent.files.forEach(function(f) {
        dirNode.children.push({ name: f.name, handle: f.handle, kind: 'file' });
      });
    }
    function esc(s) {
      return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }
    function renderTree() {
      var el = document.getElementById('localFileList');
      if (!el) return;
      var folderLabel = document.getElementById('sidebarCurrentFolder');
      if (!treeRoot) {
        if (folderLabel) folderLabel.textContent = '未择定';
        el.innerHTML = '<div class="file-list-item tree-depth-0" style="color:var(--natsume-ink-light)">请先选择本地目录</div>';
        el._treeNodes = [];
        el._fileHandles = [];
        return;
      }
      if (folderLabel) folderLabel.textContent = treeRoot.name;
      var flat = [];
      function collect(node, depth, parentPath) {
        if (!node) return;
        var path = parentPath ? parentPath + '/' + node.name : node.name;
        flat.push({ node: node, depth: depth, path: path });
        if (node.kind === 'dir' && node.expanded && node.children) {
          node.children.forEach(function(c) { collect(c, depth + 1, path); });
        }
      }
      collect(treeRoot, 0, '');
      var fileIndex = 0;
      var html = '';
      flat.forEach(function(item, idx) {
        var node = item.node;
        var depth = item.depth;
        var path = item.path;
        var depthStyle = depth === 0 ? '' : ' style="--tree-depth:' + depth + '"';
        var pathAttr = ' data-path="' + esc(path) + '" data-depth="' + depth + '"';
        if (node.kind === 'dir') {
          var arrow = node.expanded ? '▼' : '▶';
          var expClass = node.expanded ? ' expanded' : '';
          html += '<div class="file-list-item folder' + expClass + (depth === 0 ? ' tree-depth-0' : '') + '" data-kind="dir" data-name="' + esc(node.name) + '" data-tidx="' + idx + '"' + pathAttr + depthStyle + ' draggable="true"><span class="tree-arrow">' + arrow + '</span><span class="tree-icon">📁</span>' + esc(node.name) + '</div>';
        } else {
          html += '<div class="file-list-item file' + (depth === 0 ? ' tree-depth-0' : '') + '" data-name="' + esc(node.name) + '" data-kind="file" data-fidx="' + fileIndex + '" data-tidx="' + idx + '"' + pathAttr + depthStyle + ' draggable="true"><span class="tree-icon" style="margin-left:1em">📄</span>' + esc(node.name) + '</div>';
          fileIndex++;
        }
      });
      el.innerHTML = html || '<div class="file-list-item tree-depth-0" style="color:var(--natsume-ink-light)">（此层无剧本文件）</div>';
      el._treeNodes = flat.map(function(item) { return item.node; });
      el._treePaths = flat.map(function(item) { return item.path; });
      el._fileHandles = flat.filter(function(item) { return item.node.kind === 'file'; }).map(function(item) { return { name: item.node.name, handle: item.node.handle }; });
      document.getElementById('localSelected').textContent = '';
      if (typeof pendingAnalysisHandle !== 'undefined') {
        pendingAnalysisHandle = null;
        var w = document.getElementById('localAnalyzeBtnWrap');
        if (w) w.style.display = 'none';
      }
    }

    (function showDirPickerTipIfUnsupported() {
      var tip = document.getElementById('dirPickerTip');
      var btn = document.getElementById('btnPickLocalDir');
      if (!tip) return;
      if (typeof showDirectoryPicker !== 'function') {
        tip.textContent = '选择目录仅支持 Chrome、Edge 等 Chromium 内核浏览器，当前浏览器不支持。请使用右侧拖拽或选文件上传。';
        tip.style.display = 'block';
        if (btn) { btn.disabled = true; btn.title = '当前浏览器不支持，请用 Chrome/Edge 或右侧拖拽上传'; }
        return;
      }
      if (typeof window.isSecureContext !== 'boolean' || window.isSecureContext) return;
      tip.textContent = '当前为 HTTP 访问，「选择目录」不可用（浏览器安全策略要求 HTTPS 或 localhost）。请用右侧拖拽/选文件上传；配置 HTTPS 后即可使用选择目录（本机：python run_web.py --https；服务器：Nginx + 证书，见 DEPLOY.md）。';
      tip.style.display = 'block';
      if (btn) { btn.disabled = true; btn.title = '需 HTTPS 或 localhost 访问后可用'; }
    })();

    var btnPickLocalDir = document.getElementById('btnPickLocalDir');
    if (btnPickLocalDir) {
      btnPickLocalDir.onclick = async function() {
        if (typeof showDirectoryPicker !== 'function') {
          var listEl = document.getElementById('localFileList');
          if (listEl) {
            listEl.innerHTML = '<div class="file-list-item err">当前浏览器不支持选择目录（请使用 Chrome 或 Edge）。请用右侧拖拽或选文件上传。</div>';
          }
          return;
        }
        try {
          var rootHandle = await showDirectoryPicker({ id: 'eduflow-local-dir' });
          treeRoot = { name: rootHandle.name, handle: rootHandle, kind: 'dir', children: null, expanded: true };
          var el = document.getElementById('localFileList');
          if (el) {
            el.innerHTML = '加载中…';
          }
          await loadTreeChildren(treeRoot);
          renderTree();
          saveLastDir(rootHandle);
        } catch (e) {
          if (e.name !== 'AbortError') {
            var msg = (e.name === 'SecurityError' || (e.message && e.message.indexOf('secure') !== -1))
              ? '当前环境不允许选择目录（需 HTTPS 或 localhost）。请用右侧拖拽/选文件上传，或通过 HTTPS 访问（本机或服务器配置 HTTPS 后即可）。'
              : '未择定目录';
            var listElErr = document.getElementById('localFileList');
            if (listElErr) {
              listElErr.innerHTML = '<div class="file-list-item err">' + msg + '</div>';
            }
          }
        }
      };
      restoreLastDir().catch(function() {});
    }

    function updateScriptDropZoneDisplay(filename) {
      var dz = document.getElementById('scriptDropZone');
      var textEl = document.getElementById('scriptDropZoneText');
      var hintEl = document.getElementById('scriptDropZoneHint');
      var emptyText = (dz && dz.getAttribute('data-empty-text')) || '将 .md / .docx / .pdf 拖至此处，或点击选取';
      if (!dz || !textEl) return;
      if (filename) {
        textEl.textContent = '已加载：' + filename;
        if (hintEl) { hintEl.style.display = 'block'; hintEl.textContent = '点击或拖入新文件可更换'; }
        dz.classList.add('loaded');
      } else {
        textEl.textContent = emptyText;
        if (hintEl) hintEl.style.display = 'none';
        dz.classList.remove('loaded');
      }
    }

    /** 仅上传并解析结构，不生成卡片。解析完成后提示用户点击「生成卡片」。 */
    async function runUploadAndAnalyze(file) {
      var msg = document.getElementById('uploadMsg');
      msg.textContent = '解析文件中…';
      msg.classList.remove('err');
      lastUploadData = null;
      window.lastScriptFile = file || null;
      updateScriptDropZoneDisplay(null);
      var genBtn = document.getElementById('btnGenCards');
      var personaBtn = document.getElementById('btnGenPersonaFromScript');
      if (genBtn) genBtn.disabled = true;
      if (personaBtn) personaBtn.disabled = !window.lastScriptFile;
      try {
        var fd = new FormData();
        fd.append('file', file);
        msg.textContent = '解析与分幕中…（首次约 10–30 秒，同内容会走缓存）';
        var r = await apiFetch('/api/script/upload', { method: 'POST', body: fd });
        var d = await safeResponseJson(r);
        if (!r.ok) throw new Error(getUserMsg(d, '上传解析失败，请稍后重试'));
        lastUploadData = d;
        var fn = file && file.name ? file.name : (d.filename || '');
        updateScriptDropZoneDisplay(fn);
        var tc = d.trainset_count != null ? d.trainset_count : 0;
        msg.textContent = '分析完成：识别出 ' + (d.stages_count || 0) + ' 个阶段。' + (tc ? ' Trainset 已更新（共 ' + tc + ' 条），闭环优化时将使用。' : '') + ' 现在可点击「生成卡片」。';
        if (typeof window.updateSimProgress === 'function') window.updateSimProgress({1: true});
        if (genBtn) genBtn.disabled = false;
        if (personaBtn) personaBtn.disabled = !window.lastScriptFile;
        if (tc && typeof refreshTrainsetSelect === 'function') refreshTrainsetSelect();
      } catch (err) {
        msg.classList.add('err');
        msg.innerHTML = '<span class="err">' + esc(err.message || '上传解析失败，请稍后重试') + '</span>';
        lastUploadData = null;
        if (genBtn) genBtn.disabled = true;
        if (personaBtn) personaBtn.disabled = !window.lastScriptFile;
      }
    }

    async function runAnalysisForFile(fileHandle) {
      try {
        var file = await fileHandle.getFile();
        if (file) await runUploadAndAnalyze(file);
      } catch (err) {
        var msg = document.getElementById('uploadMsg');
        msg.innerHTML = '<span class="err">' + esc(err.message || '解析失败，请稍后重试') + '</span>';
      }
    }

    function getFileHandleFromItem(listEl, item) {
      if (item.getAttribute('data-kind') !== 'file') return null;
      var idx = parseInt(item.getAttribute('data-fidx'), 10);
      var files = listEl._fileHandles || [];
      return files[idx] ? files[idx].handle : null;
    }

    function showContextMenu(x, y, opts) {
      var fileHandle = opts.fileHandle;
      var fileName = opts.fileName || '';
      var folderName = opts.folderName || '';
      var path = opts.path || '';
      var existing = document.getElementById('ctxMenu');
      if (existing) existing.remove();
      var menu = document.createElement('div');
      menu.id = 'ctxMenu';
      menu.className = 'ctx-menu';
      menu.style.left = x + 'px';
      menu.style.top = y + 'px';
      var copyPathItem = document.createElement('div');
      copyPathItem.className = 'ctx-menu-item';
      copyPathItem.textContent = '复制路径';
      copyPathItem.onclick = function() {
        if (path && navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(path).catch(function() {});
        }
        document.getElementById('ctxMenu') && document.getElementById('ctxMenu').remove();
      };
      menu.appendChild(copyPathItem);
      if (folderName) {
        var setWsItem = document.createElement('div');
        setWsItem.className = 'ctx-menu-item';
        setWsItem.textContent = '设为当前工作区';
        setWsItem.onclick = function() {
          setWorkspaceFromFolderName(folderName);
          document.getElementById('ctxMenu') && document.getElementById('ctxMenu').remove();
        };
        menu.appendChild(setWsItem);
      }
      if (fileHandle) {
        var lower = fileName.toLowerCase();
        if (lower.endsWith('.md') || lower.endsWith('.docx') || lower.endsWith('.doc')) {
          var previewItem = document.createElement('div');
          previewItem.className = 'ctx-menu-item';
          previewItem.textContent = '在页面内预览';
          previewItem.onclick = function() {
            openCardEditFromFile(fileHandle, fileName);
            document.getElementById('ctxMenu') && document.getElementById('ctxMenu').remove();
          };
          menu.appendChild(previewItem);
        }
        var openItem = document.createElement('div');
        openItem.className = 'ctx-menu-item';
        openItem.textContent = '用默认方式打开';
        openItem.onclick = async function() {
          try {
            var file = await fileHandle.getFile();
            var url = URL.createObjectURL(file);
            var a = document.createElement('a');
            a.href = url;
            a.download = file.name || fileName;
            a.click();
            URL.revokeObjectURL(url);
          } catch (e) { }
          document.getElementById('ctxMenu') && document.getElementById('ctxMenu').remove();
        };
        var analyzeItem = document.createElement('div');
        analyzeItem.className = 'ctx-menu-item';
        analyzeItem.textContent = '开始分析';
        analyzeItem.onclick = function() {
          runAnalysisForFile(fileHandle);
          document.getElementById('ctxMenu') && document.getElementById('ctxMenu').remove();
        };
        menu.appendChild(openItem);
        menu.appendChild(analyzeItem);
      }
      document.body.appendChild(menu);
      function closeMenu() {
        var m = document.getElementById('ctxMenu');
        if (m) m.remove();
        document.removeEventListener('click', closeMenu);
      }
      setTimeout(function() { document.addEventListener('click', closeMenu); }, 0);
    }

    async function openPreview(fileHandle, fileName) {
      var modal = document.getElementById('previewModal');
      var titleEl = document.getElementById('previewModalTitle');
      var bodyEl = document.getElementById('previewModalBody');
      titleEl.textContent = fileName || '预览';
      bodyEl.innerHTML = '<p style="color:var(--natsume-ink-light)">加载中…</p>';
      openModal(modal, null);
      try {
        var file = await fileHandle.getFile();
        var lower = (fileName || '').toLowerCase();
        if (lower.endsWith('.md')) {
          var text = await file.text();
          if (typeof marked !== 'undefined') {
            marked.setOptions({ gfm: true });
            bodyEl.innerHTML = marked.parse(text || '');
          } else {
            bodyEl.textContent = text || '';
          }
        } else if (lower.endsWith('.docx')) {
          var buf = await file.arrayBuffer();
          if (typeof mammoth !== 'undefined') {
            var result = await mammoth.convertToHtml({ arrayBuffer: buf });
            bodyEl.innerHTML = result.value || '<p>（无内容）</p>';
          } else {
            bodyEl.innerHTML = '<p class="err">需要 mammoth.js 才能预览 Word 文档</p>';
          }
        } else if (lower.endsWith('.doc')) {
          bodyEl.innerHTML = '<p>.doc 格式暂不支持页面内预览，请另存为 .docx 后预览，或下载后用 Word 打开。</p>';
        } else {
          bodyEl.textContent = '不支持预览该格式';
        }
      } catch (e) {
        bodyEl.innerHTML = '<p class="err">预览失败，请稍后重试</p>';
      }
    }
    function renderContentEditPreview() {
      var ta = document.getElementById('contentEditModalTextarea');
      var prevEl = document.getElementById('contentEditModalPreview');
      if (!ta || !prevEl) return;
      var content = ta.value || '';
      var editType = ta.dataset.editType || 'card';
      if (editType === 'persona') {
        prevEl.innerHTML = '<pre style="margin:0;white-space:pre-wrap;word-break:break-word;font-size:0.9rem;">' + (content || '（无内容）').replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</pre>';
      } else if (typeof marked !== 'undefined') {
        marked.setOptions({ gfm: true });
        prevEl.innerHTML = marked.parse(content);
      } else {
        prevEl.textContent = content;
      }
    }
    function setContentEditMode(mode) {
      var ta = document.getElementById('contentEditModalTextarea');
      var prevEl = document.getElementById('contentEditModalPreview');
      document.querySelectorAll('.content-edit-tab').forEach(function(t) {
        t.classList.toggle('active', t.getAttribute('data-mode') === mode);
      });
      if (mode === 'preview') {
        renderContentEditPreview();
        if (ta) ta.style.display = 'none';
        if (prevEl) { prevEl.style.display = 'block'; prevEl.style.flex = '1'; }
      } else {
        if (ta) ta.style.display = 'block';
        if (prevEl) prevEl.style.display = 'none';
      }
    }
    /** 打开卡片查看/编辑（统一弹窗） */
    async function openCardEditModal(outputPath) {
      if (!outputPath || !outputPath.trim()) return;
      var path = outputPath.trim();
      if (!path.startsWith('output/')) path = 'output/' + path;
      var modal = document.getElementById('contentEditModal');
      var titleEl = document.getElementById('contentEditModalTitle');
      var ta = document.getElementById('contentEditModalTextarea');
      var prevEl = document.getElementById('contentEditModalPreview');
      var msgEl = document.getElementById('contentEditModalMsg');
      var saveBtn = document.getElementById('btnContentEditSave');
      var extraWrap = document.getElementById('contentEditExtra');
      titleEl.textContent = '卡片：' + path;
      ta.value = '';
      ta.placeholder = '加载中…';
      ta.dataset.editType = 'card';
      ta.dataset.editPath = '';
      var dlBtn = document.getElementById('btnContentEditDownload');
      if (dlBtn) dlBtn.style.display = 'none';
      if (prevEl) prevEl.innerHTML = '';
      if (msgEl) msgEl.textContent = '';
      if (saveBtn) saveBtn.style.display = '';
      if (extraWrap) extraWrap.style.display = 'none';
      setContentEditMode('edit');
      openModal(modal, null);
      try {
        var r = await apiFetch('/api/output/read?path=' + encodeURIComponent(path));
        var d = await safeResponseJson(r);
        if (!r.ok) throw new Error(getUserMsg(d, '加载失败，请稍后重试'));
        ta.value = (d && d.content) || '';
        ta.placeholder = '在此编辑卡片内容…';
        ta.dataset.editPath = path;
        var dlBtn = document.getElementById('btnContentEditDownload');
        if (dlBtn) {
          dlBtn.style.display = (path && path.indexOf('output/') === 0) ? '' : 'none';
          dlBtn.onclick = function() { if (typeof downloadOutputFile === 'function') downloadOutputFile(path); };
        }
      } catch (e) {
        ta.placeholder = '';
        if (msgEl) msgEl.innerHTML = '<span class="err">' + esc(e.message || '加载失败，请稍后重试') + '</span>';
      }
    }
    /** 从左侧栏文件打开查看/编辑（.md 支持预览+编辑，.docx 仅预览） */
    async function openCardEditFromFile(fileHandle, fileName) {
      document.querySelectorAll('.content-edit-tab').forEach(function(t) { t.style.display = ''; });
      var modal = document.getElementById('contentEditModal');
      var titleEl = document.getElementById('contentEditModalTitle');
      var ta = document.getElementById('contentEditModalTextarea');
      var prevEl = document.getElementById('contentEditModalPreview');
      var msgEl = document.getElementById('contentEditModalMsg');
      var saveBtn = document.getElementById('btnContentEditSave');
      var extraWrap = document.getElementById('contentEditExtra');
      titleEl.textContent = fileName || '预览';
      ta.value = '';
      ta.placeholder = '加载中…';
      ta.dataset.editType = 'card';
      ta.dataset.editPath = '';
      if (prevEl) prevEl.innerHTML = '';
      if (msgEl) msgEl.textContent = '';
      if (saveBtn) saveBtn.style.display = 'none';
      if (extraWrap) extraWrap.style.display = 'none';
      setContentEditMode('edit');
      openModal(modal, null);
      try {
        var file = await fileHandle.getFile();
        var lower = (fileName || '').toLowerCase();
        if (lower.endsWith('.md')) {
          var text = await file.text();
          ta.value = text || '';
          ta.placeholder = '在此编辑（本地文件无法保存回原文件）';
          setContentEditMode('edit');
        } else if (lower.endsWith('.docx')) {
          var buf = await file.arrayBuffer();
          if (typeof mammoth !== 'undefined') {
            var result = await mammoth.convertToHtml({ arrayBuffer: buf });
            ta.value = '';
            if (prevEl) { prevEl.innerHTML = result.value || '<p>（无内容）</p>'; prevEl.style.display = 'block'; }
            if (ta) ta.style.display = 'none';
            document.querySelectorAll('.content-edit-tab').forEach(function(t) {
              t.classList.toggle('active', t.getAttribute('data-mode') === 'preview');
              t.style.display = t.getAttribute('data-mode') === 'preview' ? '' : 'none';
            });
          } else {
            if (msgEl) msgEl.innerHTML = '<span class="err">需要 mammoth.js 才能预览 Word 文档</span>';
          }
        } else if (lower.endsWith('.doc')) {
          if (msgEl) msgEl.innerHTML = '<span class="err">.doc 格式请另存为 .docx 后预览</span>';
        } else {
          if (msgEl) msgEl.innerHTML = '<span class="err">不支持该格式</span>';
        }
      } catch (e) {
        if (msgEl) msgEl.innerHTML = '<span class="err">加载失败，请稍后重试</span>';
      }
    }
    function setWorkspaceFromFolderName(folderName) {
      var id = (folderName || '').trim().replace(/[\\/:*?"<>|]/g, '_').slice(0, 64) || 'folder';
      window.WORKSPACE_ID = id;
      history.replaceState(null, '', '/w/' + encodeURIComponent(id));
      var el = document.getElementById('currentWorkspaceLabel');
      if (el) el.textContent = id;
      if (typeof showWorkspaceToast === 'function') showWorkspaceToast(id);
    }
    function switchWorkspaceByProjectName(name) {
      var id = (name || '').trim().replace(/[\\/:*?"<>|]/g, '_').slice(0, 64) || 'default';
      window.WORKSPACE_ID = id;
      history.replaceState(null, '', '/w/' + encodeURIComponent(id));
      var el = document.getElementById('currentWorkspaceLabel');
      if (el) el.textContent = id;
      if (typeof showWorkspaceToast === 'function') showWorkspaceToast(id);
    }
    (function initPreviewModal() {
      var modal = document.getElementById('previewModal');
      document.getElementById('btnClosePreview').onclick = function() { closeModal(modal); };
      modal.onclick = function(e) { if (e.target === modal) closeModal(modal); };
    })();
    document.addEventListener('click', function(e) {
      var link = e.target.closest('.card-path-link');
      if (link) {
        e.preventDefault();
        var path = link.getAttribute('data-path');
        if (path) openCardEditModal(path);
      }
    });
    (function initContentEditModal() {
      var modal = document.getElementById('contentEditModal');
      var ta = document.getElementById('contentEditModalTextarea');
      var msgEl = document.getElementById('contentEditModalMsg');
      var saveBtn = document.getElementById('btnContentEditSave');
      var extraWrap = document.getElementById('contentEditExtra');
      if (!modal || !ta) return;
      document.getElementById('btnCloseContentEdit').onclick = function() { closeModal(modal); };
      modal.onclick = function(e) { if (e.target === modal) closeModal(modal); };
      document.querySelectorAll('.content-edit-tab').forEach(function(btn) {
        btn.onclick = function() { setContentEditMode(btn.getAttribute('data-mode')); };
      });
      saveBtn.onclick = async function() {
        var editType = ta.dataset.editType || '';
        var content = ta.value || '';
        if (editType === 'card') {
          var path = ta.dataset.editPath;
          if (!path) { if (msgEl) msgEl.innerHTML = '<span class="err">无有效路径</span>'; return; }
          msgEl.textContent = '保存中…';
          try {
            var r = await apiFetch('/api/output/write', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: path, content: content }) });
            var d = await safeResponseJson(r);
            if (!r.ok) throw new Error(getUserMsg(d, '保存失败，请稍后重试'));
            if (msgEl) msgEl.textContent = '已保存';
            if (typeof refreshWorkspaceFileList === 'function') refreshWorkspaceFileList();
          } catch (e) {
            if (msgEl) msgEl.innerHTML = '<span class="err">' + esc(e.message || '保存失败，请稍后重试') + '</span>';
          }
          return;
        }
        if (editType === 'persona') {
          var personaId = ta.dataset.personaId || '';
          if (ta.dataset.readOnly === 'true') {
            if (msgEl) msgEl.innerHTML = '<span class="err">预设人设不可覆盖，请用下方「保存」保存为新名称。</span>';
            return;
          }
          if (!personaId.startsWith('custom/')) {
            if (msgEl) msgEl.innerHTML = '<span class="err">仅可保存自定义人设</span>';
            return;
          }
          msgEl.textContent = '保存中…';
          try {
            var r = await apiFetch('/api/personas/content', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ persona_id: personaId, content: content }) });
            var d = await safeResponseJson(r);
            if (!r.ok) throw new Error(getUserMsg(d, '保存失败，请稍后重试'));
            if (msgEl) msgEl.textContent = '已保存';
            if (typeof loadPersonas === 'function') loadPersonas();
          } catch (e) {
            if (msgEl) msgEl.innerHTML = '<span class="err">' + esc(e.message || '保存失败，请稍后重试') + '</span>';
          }
        }
      };
      document.getElementById('btnContentEditSaveAs').onclick = async function() {
        if (ta.dataset.editType !== 'persona') return;
        var content = ta.value || '';
        var name = '';
        try {
          if (content.trim()) {
            var lines = content.split('\n');
            for (var i = 0; i < lines.length; i++) {
              var line = lines[i].trim();
              var colon = line.indexOf(':');
              if (colon > 0 && line.substring(0, colon).trim().toLowerCase() === 'name') {
                name = line.slice(colon + 1).trim().replace(/^["']|["']$/g, '');
                break;
              }
            }
          }
        } catch (e) {}
        name = name.trim().replace(/[\\/:*?"<>|]/g, '_').slice(0, 64) || '';
        if (!name) { if (msgEl) msgEl.innerHTML = '<span class="err">请在编辑区 YAML 中配置 name 字段作为人设名称</span>'; return; }
        var personaId = 'custom/' + name;
        msgEl.textContent = '保存中…';
        try {
          var r = await apiFetch('/api/personas/content', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ persona_id: personaId, content: content }) });
          var d = await safeResponseJson(r);
          if (!r.ok) throw new Error(getUserMsg(d, '保存失败，请稍后重试'));
          if (msgEl) msgEl.textContent = '已保存为 ' + personaId;
          if (typeof loadPersonas === 'function') loadPersonas();
        } catch (e) {
          if (msgEl) msgEl.innerHTML = '<span class="err">' + esc(e.message || '保存失败，请稍后重试') + '</span>';
        }
      };
      var newPersonaTemplate = 'name: 新人设\npersona_type: custom\nbackground: ""\npersonality: ""\ngoal: ""\nengagement_level: normal\nresponse_length: medium\n';
      window.openPersonaEditModal = async function() {
        var sel = document.getElementById('personaId');
        var personaId = (sel && sel.value) ? sel.value.trim() : 'excellent';
        document.getElementById('contentEditModalTitle').textContent = '学生人设编辑：' + personaId;
        ta.value = '';
        ta.placeholder = '加载中…';
        ta.dataset.editType = 'persona';
        ta.dataset.personaId = '';
        ta.dataset.readOnly = 'false';
        document.getElementById('contentEditModalPreview').innerHTML = '';
        if (msgEl) msgEl.textContent = '';
        if (saveBtn) saveBtn.style.display = '';
        if (extraWrap) extraWrap.style.display = 'none';
        setContentEditMode('edit');
        openModal(modal, null);
        try {
          var r = await apiFetch('/api/personas/content?persona_id=' + encodeURIComponent(personaId));
          var d = await safeResponseJson(r);
          if (!r.ok) throw new Error(getUserMsg(d, '加载失败，请稍后重试'));
          ta.value = (d && d.content) || '';
          ta.placeholder = 'YAML 格式，编辑后点击保存。预设人设只读，可保存为自定义。';
          ta.dataset.personaId = personaId;
          ta.dataset.readOnly = d.read_only ? 'true' : 'false';
          if (d.read_only) {
            if (saveBtn) saveBtn.style.display = 'none';
            if (extraWrap) extraWrap.style.display = 'flex';
          }
        } catch (e) {
          ta.placeholder = '';
          if (msgEl) msgEl.innerHTML = '<span class="err">' + esc(e.message || '加载失败，请稍后重试') + '</span>';
        }
      };
      window.openNewPersonaModal = function() {
        document.getElementById('contentEditModalTitle').textContent = '学生人设编辑：新建';
        ta.value = newPersonaTemplate;
        ta.placeholder = 'YAML 格式，填写 name 等字段后点击下方「保存」保存为自定义人设。';
        ta.dataset.editType = 'persona';
        ta.dataset.personaId = '';
        ta.dataset.readOnly = 'false';
        document.getElementById('contentEditModalPreview').innerHTML = '';
        if (msgEl) msgEl.textContent = '';
        if (saveBtn) saveBtn.style.display = 'none';
        if (extraWrap) extraWrap.style.display = 'flex';
        setContentEditMode('edit');
        openModal(modal, null);
      };
    })();
    document.getElementById('btnEditPersona').onclick = function() { if (typeof window.openPersonaEditModal === 'function') window.openPersonaEditModal(); };
    var btnAddNew = document.getElementById('btnAddNewPersona');
    if (btnAddNew) btnAddNew.onclick = function() { if (typeof window.openNewPersonaModal === 'function') window.openNewPersonaModal(); };

    (function setupGenPersonaFromScript() {
      var btnGen = document.getElementById('btnGenPersonaFromScript');
      var msgEl = document.getElementById('personaGenMsg');
      if (!btnGen) return;
      btnGen.onclick = async function() {
        var file = window.lastScriptFile;
        if (!file) {
          if (msgEl) msgEl.innerHTML = '<span class="err">请先上传剧本</span>';
          return;
        }
        var fn = file.name || '';
        if (msgEl) msgEl.textContent = fn ? '正在根据《' + fn + '》生成学生人设…' : '生成中…';
        btnGen.disabled = true;
        try {
          var fd = new FormData();
          fd.append('file', file);
          fd.append('num_personas', '3');
          var r = await apiFetch('/api/personas/generate', { method: 'POST', body: fd });
          var d = await safeResponseJson(r);
          if (!r.ok) throw new Error(getUserMsg(d, '生成人设失败，请稍后重试'));
          var n = (d && d.count) || 0;
          if (typeof loadPersonas === 'function') loadPersonas();
          if (msgEl) msgEl.innerHTML = '<span class="ok">已生成 ' + n + ' 个人设并已保存，可直接在「人设」下拉中选择使用。</span>';
        } catch (e) {
          if (msgEl) msgEl.innerHTML = '<span class="err">' + esc(e.message || '生成人设失败，请稍后重试') + '</span>';
        }
        btnGen.disabled = !window.lastScriptFile;
      };
    })();

    var localFileListEl = document.getElementById('localFileList');
    if (localFileListEl) localFileListEl.onclick = async function(e) {
      var item = e.target.closest('.file-list-item');
      if (!item) return;
      var kind = item.getAttribute('data-kind');
      var name = item.getAttribute('data-name');
      if (kind === 'dir') {
        var tidx = parseInt(item.getAttribute('data-tidx'), 10);
        var node = this._treeNodes && this._treeNodes[tidx];
        if (!node || node.kind !== 'dir') return;
        if (node.expanded) {
          node.expanded = false;
          renderTree();
        } else {
          var arrowSpan = item.querySelector('.tree-arrow');
          if (arrowSpan) { arrowSpan.textContent = '…'; item.classList.add('loading'); }
          await loadTreeChildren(node);
          node.expanded = true;
          renderTree();
        }
        return;
      }
      if (kind === 'file') {
        this.querySelectorAll('.file-list-item.selected').forEach(function(n) { n.classList.remove('selected'); });
        item.classList.add('selected');
        document.getElementById('localSelected').textContent = '已择定：' + name;
      }
    };

    if (localFileListEl) localFileListEl.ondblclick = async function(e) {
      var item = e.target.closest('.file-list-item');
      if (!item) return;
      var kind = item.getAttribute('data-kind');
      var name = item.getAttribute('data-name');
      if (kind === 'dir') {
        var tidx = parseInt(item.getAttribute('data-tidx'), 10);
        var node = this._treeNodes && this._treeNodes[tidx];
        if (!node || node.kind !== 'dir') return;
        if (node.expanded) {
          node.expanded = false;
          renderTree();
        } else {
          var arrowSpan = item.querySelector('.tree-arrow');
          if (arrowSpan) { arrowSpan.textContent = '…'; item.classList.add('loading'); }
          await loadTreeChildren(node);
          node.expanded = true;
          renderTree();
        }
        return;
      }
      if (kind === 'file') {
        var fh = getFileHandleFromItem(this, item);
        if (fh) {
          runAnalysisForFile(fh);
        }
      }
    };

    if (localFileListEl) localFileListEl.ondragstart = function(e) {
      var item = e.target.closest('.file-list-item[data-kind="file"], .file-list-item[data-kind="dir"]');
      if (!item) return;
      e.dataTransfer.setData('text/plain', 'eduflow-file');
      e.dataTransfer.effectAllowed = 'copy';
      window._eduflowDraggedPath = item.getAttribute('data-path') || '';
      if (item.getAttribute('data-kind') === 'file') {
        var idx = parseInt(item.getAttribute('data-fidx'), 10);
        var handles = this._fileHandles;
        window._eduflowDraggedFileHandle = handles && handles[idx] ? handles[idx].handle : null;
      } else {
        window._eduflowDraggedFileHandle = null;
      }
    };
    if (localFileListEl) localFileListEl.ondragend = function() {
      window._eduflowDraggedFileHandle = null;
      window._eduflowDraggedPath = null;
    };
    if (localFileListEl) localFileListEl.oncontextmenu = function(e) {
      var item = e.target.closest('.file-list-item');
      if (!item || item.classList.contains('up')) return;
      var kind = item.getAttribute('data-kind');
      if (kind !== 'file' && kind !== 'dir') return;
      e.preventDefault();
      var path = item.getAttribute('data-path') || '';
      var opts = { path: path };
      if (kind === 'file') {
        var fh = getFileHandleFromItem(this, item);
        opts.fileHandle = fh;
        opts.fileName = item.getAttribute('data-name');
      } else if (kind === 'dir') {
        opts.folderName = item.getAttribute('data-name');
      }
      showContextMenu(e.clientX, e.clientY, opts);
    };

    var lastFocusedPathInput = null;
    var workspaceFilesCache = { input: [], output: [] };
    function refreshWorkspaceFileList() {
      Promise.all([
        apiFetch('/api/input/files').then(function(r) { if (r.status === 401 && window.showAuthScreen) window.showAuthScreen(); return safeResponseJson(r); }),
        apiFetch('/api/output/files').then(function(r) { if (r.status === 401 && window.showAuthScreen) window.showAuthScreen(); return safeResponseJson(r); })
      ]).then(function(results) {
        var inputList = (results[0] && results[0].files) ? results[0].files : [];
        var outputList = (results[1] && results[1].files) ? results[1].files : [];
        workspaceFilesCache = { input: inputList, output: outputList };
        renderWorkspaceFileList();
      }).catch(function() {});
    }
    function downloadOutputFile(path) {
      if (!path || typeof apiFetch !== 'function') return;
      apiFetch('/api/output/download?path=' + encodeURIComponent(path)).then(function(r) { return r.blob(); }).then(function(blob) {
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = path.split('/').pop() || 'download';
        a.click();
        URL.revokeObjectURL(url);
      }).catch(function() {});
    }
    function renderWorkspaceFileList() {
      var listEl = document.getElementById('workspaceFileList');
      var inp = workspaceFilesCache.input || [];
      var out = workspaceFilesCache.output || [];
      var html = '';
      if (inp.length || out.length) {
        if (out.length) {
          html += '<div class="file-list-item tree-depth-0" style="color:var(--natsume-ink-light);font-weight:bold">output/</div>';
          out.forEach(function(f) {
            var path = (f.path || '').replace(/^output\/?/, 'output/');
            var name = f.name || path.split('/').pop();
            var escPath = String(path).replace(/"/g, '&quot;');
            var escName = String(name).replace(/</g, '&lt;').replace(/>/g, '&gt;');
            html += '<div class="file-list-item file tree-depth-0" data-path="' + escPath + '" data-name="' + escName + '" data-output="1" draggable="true"><span class="tree-icon" style="margin-left:1em">📄</span><span class="workspace-file-name">' + escName + '</span> <a href="#" class="workspace-file-dl" data-path="' + escPath + '" title="下载">下载</a></div>';
          });
        }
        if (inp.length) {
          html += '<div class="file-list-item tree-depth-0" style="color:var(--natsume-ink-light);font-weight:bold;margin-top:0.5rem">input/</div>';
          inp.forEach(function(f) {
            var path = (f.path || '').replace(/^input\/?/, 'input/');
            var name = f.name || path.split('/').pop();
            var escPath = String(path).replace(/"/g, '&quot;');
            var escName = String(name).replace(/</g, '&lt;').replace(/>/g, '&gt;');
            html += '<div class="file-list-item file tree-depth-0" data-path="' + escPath + '" data-name="' + escName + '" draggable="true"><span class="tree-icon" style="margin-left:1em">📄</span><span class="workspace-file-name">' + escName + '</span></div>';
          });
        }
      } else {
        var emptyIcon = '<svg class="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>';
        html = '<div class="empty-state" id="workspaceEmptyState">' + emptyIcon +
          '<p class="empty-state-title">工作区暂无文件</p>' +
          '<p class="empty-state-desc">上传并解析剧本后可生成卡片，或从闭环优化导出</p>' +
          '<button type="button" class="btn-primary empty-state-cta" data-action="scrollToScript">去上传剧本</button></div>';
      }
      if (listEl) {
        listEl.innerHTML = html || '';
        var cta = listEl.querySelector('.empty-state-cta[data-action="scrollToScript"]');
        if (cta) cta.onclick = function() {
          var section = document.querySelector('[data-section="script"]') || document.getElementById('scriptDropZone');
          if (section) section.scrollIntoView({ behavior: 'smooth', block: 'center' });
        };
        listEl.onclick = function(e) {
          var dl = e.target.closest('.workspace-file-dl');
          if (dl) {
            e.preventDefault();
            var p = dl.getAttribute('data-path');
            if (p) downloadOutputFile(p);
            return;
          }
          var item = e.target.closest('.file-list-item.file[data-path]');
          if (!item) return;
          var path = item.getAttribute('data-path');
          if (path && lastFocusedPathInput) {
            lastFocusedPathInput.value = (typeof normalizePathForBackend === 'function' ? normalizePathForBackend(path) : path);
            lastFocusedPathInput = null;
          }
        };
        listEl.ondblclick = function(e) {
          var item = e.target.closest('.file-list-item.file[data-path]');
          if (!item) return;
          var path = item.getAttribute('data-path');
          if (path && typeof openCardEditModal === 'function') openCardEditModal(path);
        };
        listEl.ondragstart = function(e) {
          var item = e.target.closest('.file-list-item.file[data-path]');
          if (!item) return;
          e.dataTransfer.setData('text/plain', 'eduflow-file');
          e.dataTransfer.effectAllowed = 'copy';
          window._eduflowDraggedPath = item.getAttribute('data-path') || '';
        };
        listEl.ondragend = function() { window._eduflowDraggedPath = null; };
      }
      updatePathDatalists();
      if (typeof refreshTrainsetSelect === 'function') refreshTrainsetSelect();
    }
    var btnRefreshWorkspaceFiles = document.getElementById('btnRefreshWorkspaceFiles');
    if (btnRefreshWorkspaceFiles) btnRefreshWorkspaceFiles.onclick = refreshWorkspaceFileList;
    function refreshTrainsetSelect() {
      var sel = document.getElementById('optimizerTrainsetSelect');
      var infoEl = document.getElementById('optimizerTrainsetInfo');
      if (!sel) return;
      apiFetch('/api/trainset/list').then(function(r) {
        if (r.status === 401 && window.showAuthScreen) window.showAuthScreen();
        return safeResponseJson(r);
      }).then(function(d) {
        var files = (d && d.files) ? d.files : [];
        var opts = '<option value="">默认（最新）</option>';
        files.forEach(function(f) {
          var path = (f.path || '').replace(/^output\/?/, 'output/');
          var name = f.name || path.split('/').pop() || path;
          var escPath = String(path).replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
          var escName = String(name).replace(/</g, '&lt;').replace(/>/g, '&gt;');
          opts += '<option value="' + escPath + '">' + escName + '</option>';
        });
        sel.innerHTML = opts;
        if (infoEl) infoEl.textContent = files.length ? '共 ' + files.length + ' 个 Trainset，可选其一用于闭环优化。' : '暂无 Trainset，上传并解析剧本后会生成。';
      }).catch(function() {
        sel.innerHTML = '<option value="">默认（最新）</option>';
        if (infoEl) infoEl.textContent = '';
      });
    }
    function updatePathDatalists() {
      var out = workspaceFilesCache.output || [];
      var cardsDl = document.getElementById('cardsPathOptions');
      if (cardsDl) {
        cardsDl.innerHTML = out.filter(function(f) { return (f.path || '').toLowerCase().endsWith('.md'); }).map(function(f) {
          var p = (f.path || '').replace(/^output\/?/, 'output/');
          return '<option value="' + p.replace(/"/g, '&quot;') + '">';
        }).join('');
      }
    }

    (function initHistoryFilesModal() {
      var modal = document.getElementById('historyFilesModal');
      var btnOpen = document.getElementById('btnHistoryFiles');
      var btnClose = document.getElementById('btnCloseHistoryFiles');
      var btnRefresh = document.getElementById('btnRefreshHistoryFiles');
      var sortSelect = document.getElementById('historyFilesSortOrder');
      var tabs = document.querySelectorAll('.history-files-tab');
      var listCards = document.getElementById('historyFilesCards');
      var listReports = document.getElementById('historyFilesReports');
      var listTrainset = document.getElementById('historyFilesTrainset');
      var listPersonas = document.getElementById('historyFilesPersonas');
      var listOther = document.getElementById('historyFilesOther');
      var emptyHint = document.getElementById('historyFilesEmpty');
      if (!modal || !btnOpen || !listCards) return;

      var historyFilesCache = [];
      var currentCategory = 'cards';
      var historySearchQuery = '';
      function forceClearHistorySearch() {
        var input = document.getElementById('historyFilesSearch');
        historySearchQuery = '';
        if (input) input.value = '';
      }

      var emptyStateIconSvg = '<svg class="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M8 4v4M16 4v4M2 12h20"/></svg>';
      function getHistoryEmptyStateHTML(cat) {
        var config = { cards: { title: '暂无卡片', desc: '上传剧本并点击「生成卡片」即可生成', btn: '去生成卡片', action: 'scrollToScript' },
          reports: { title: '暂无评估报告', desc: '运行闭环优化后可在此查看报告', btn: '去运行优化', action: 'scrollToOptimizer' },
          trainset: { title: '暂无 Trainset', desc: '上传并解析剧本后会自动写入 Trainset 库', btn: '去上传剧本', action: 'scrollToScript' },
          personas: { title: '暂无人设文件', desc: '生成学生人设后会出现在人设库', btn: '去生成人设', action: 'scrollToScript' },
          other: { title: '暂无其他文件', desc: '上传或生成文件后会出现在此处', btn: '去上传', action: 'scrollToScript' } }[cat] || { title: '暂无数据', desc: '完成对应步骤后会出现文件', btn: '去创建', action: 'scrollToScript' };
        return '<div class="empty-state">' + emptyStateIconSvg +
          '<p class="empty-state-title">' + config.title + '</p>' +
          '<p class="empty-state-desc">' + config.desc + '</p>' +
          '<button type="button" class="btn-primary empty-state-cta" data-action="' + config.action + '">' + config.btn + '</button></div>';
      }
      function bindHistoryEmptyStateButton(wrap, cat) {
        if (!wrap) return;
        var btn = wrap.querySelector('.empty-state-cta');
        if (!btn) return;
        btn.onclick = function() {
          if (typeof closeModal === 'function') closeModal(modal);
          var action = btn.getAttribute('data-action');
          if (action === 'scrollToOptimizer') {
            var el = document.querySelector('[data-section="optimizer"]') || document.getElementById('btnRunOptimizer');
            if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          } else {
            var section = document.querySelector('[data-section="script"]') || document.getElementById('scriptDropZone');
            if (section) section.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }
        };
      }

      function classifyFile(f) {
        var path = (f.path || '').replace(/^output\/?/, 'output/');
        var name = (f.name || path.split('/').pop() || '').toLowerCase();
        var pathLower = path.toLowerCase();
        if (pathLower.indexOf('trainset_lib') !== -1 && path.toLowerCase().endsWith('.json')) return 'trainset';
        if (pathLower.indexOf('persona_lib') !== -1) return 'personas';
        if ((path.endsWith('.md') && (name.indexOf('cards') !== -1 || /^output\/[^/]+\.md$/.test(path))) ||
            (pathLower.indexOf('cards') !== -1 && path.endsWith('.md')))
          return 'cards';
        if (path.endsWith('.md') || path.endsWith('.json') || path.endsWith('.txt')) {
          if (name.indexOf('export_score') !== -1 || name.indexOf('report') !== -1 || name.indexOf('closed_loop') !== -1 ||
              name.indexOf('evaluation') !== -1 || name.indexOf('score') !== -1 || pathLower.indexOf('optimizer') !== -1 ||
              pathLower.indexOf('simulator_output') !== -1 || pathLower.indexOf('reports') !== -1)
            return 'reports';
        }
        return 'other';
      }

      function sortFiles(files, order) {
        var list = files.slice();
        list.sort(function(a, b) {
          var ma = a.mtime != null ? a.mtime : 0, mb = b.mtime != null ? b.mtime : 0;
          return order === 'newest' ? (mb - ma) : (ma - mb);
        });
        return list;
      }

      function formatTime(ts) {
        if (ts == null || ts <= 0) return '—';
        var d = new Date(ts * 1000);
        var y = d.getFullYear(), m = String(d.getMonth() + 1).padStart(2, '0'), day = String(d.getDate()).padStart(2, '0');
        var h = String(d.getHours()).padStart(2, '0'), min = String(d.getMinutes()).padStart(2, '0');
        return y + '-' + m + '-' + day + ' ' + h + ':' + min;
      }

      function renderList(container, files) {
        if (!container) return;
        var order = sortSelect && sortSelect.value ? sortSelect.value : 'newest';
        var sorted = sortFiles(files, order);
        var q = (historySearchQuery || '').trim().toLowerCase();
        if (q) sorted = sorted.filter(function(f) {
          var path = (f.path || '').replace(/^output\/?/, '');
          var name = (f.name || path.split('/').pop() || '');
          return (path + ' ' + name).toLowerCase().indexOf(q) !== -1;
        });
        var html = '';
        sorted.forEach(function(f) {
          var path = (f.path || '').replace(/^output\/?/, 'output/');
          var name = (f.name || path.split('/').pop() || '');
          var timeStr = formatTime(f.mtime);
          var escPath = String(path).replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
          var escName = String(name).replace(/</g, '&lt;').replace(/>/g, '&gt;');
          html += '<div class="history-file-item" data-path="' + escPath + '">';
          html += '<span class="history-file-name" title="' + escPath + '">' + escName + '</span>';
          html += '<span class="history-file-time">' + timeStr + '</span>';
          html += '<span class="history-file-actions">';
          html += '<button type="button" class="history-file-open" data-path="' + escPath + '">打开</button>';
          html += '<button type="button" class="history-file-dl" data-path="' + escPath + '">下载</button>';
          html += '<button type="button" class="history-file-del" data-path="' + escPath + '" data-name="' + escName + '">删除</button>';
          html += '</span></div>';
        });
        container.innerHTML = html || '';
        container.querySelectorAll('.history-file-open').forEach(function(btn) {
          btn.onclick = function() {
            var p = btn.getAttribute('data-path');
            if (p && typeof openCardEditModal === 'function') { openCardEditModal(p); closeModal(modal); }
          };
        });
        container.querySelectorAll('.history-file-dl').forEach(function(btn) {
          btn.onclick = function() {
            var p = btn.getAttribute('data-path');
            if (p && typeof downloadOutputFile === 'function') downloadOutputFile(p);
          };
        });
        container.querySelectorAll('.history-file-del').forEach(function(btn) {
          btn.onclick = async function() {
            var p = btn.getAttribute('data-path');
            var n = btn.getAttribute('data-name') || p;
            if (!p) return;
            if (!confirm('确定删除「' + n + '」？此操作不可撤销。')) return;
            try {
              var r = await apiFetch('/api/output/delete', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: p }),
              });
              var d = await safeResponseJson(r);
              if (!r.ok) throw new Error(getUserMsg(d, '删除失败'));
              loadHistoryFiles();
              if (typeof refreshWorkspaceFileList === 'function') refreshWorkspaceFileList();
              if (typeof loadPersonas === 'function') loadPersonas();
            } catch (e) {
              alert('删除失败：' + (e.message || '未知错误'));
            }
          };
        });
      }

      function renderAll() {
        var cards = historyFilesCache.filter(function(f) { return classifyFile(f) === 'cards'; });
        var reports = historyFilesCache.filter(function(f) { return classifyFile(f) === 'reports'; });
        var trainset = historyFilesCache.filter(function(f) { return classifyFile(f) === 'trainset'; });
        var personas = historyFilesCache.filter(function(f) { return classifyFile(f) === 'personas'; });
        var other = historyFilesCache.filter(function(f) { return classifyFile(f) === 'other'; });
        renderList(listCards, cards);
        renderList(listReports, reports);
        if (listTrainset) renderList(listTrainset, trainset);
        if (listPersonas) renderList(listPersonas, personas);
        renderList(listOther, other);
        var fullList = currentCategory === 'cards' ? cards : currentCategory === 'reports' ? reports
          : currentCategory === 'trainset' ? trainset : currentCategory === 'personas' ? personas : other;
        var q = (historySearchQuery || '').trim();
        var filteredCount = q ? fullList.filter(function(f) {
          var path = (f.path || '').replace(/^output\/?/, '');
          var name = (f.name || path.split('/').pop() || '');
          return (path + ' ' + name).toLowerCase().indexOf(q.toLowerCase()) !== -1;
        }).length : fullList.length;
        if (emptyHint) {
          if (filteredCount === 0) {
            emptyHint.innerHTML = fullList.length === 0
              ? getHistoryEmptyStateHTML(currentCategory)
              : '<div class="empty-state">' + emptyStateIconSvg + '<p class="empty-state-title">无匹配结果</p><p class="empty-state-desc">试试其他关键词或清空搜索</p><button type="button" class="btn-secondary empty-state-cta" data-action="clearSearch">清空搜索</button></div>';
            emptyHint.style.display = 'block';
            emptyHint.classList.add('empty-state-wrap');
            if (fullList.length === 0) bindHistoryEmptyStateButton(emptyHint, currentCategory);
            else {
              var clearBtn = emptyHint.querySelector('.empty-state-cta[data-action="clearSearch"]');
              if (clearBtn) clearBtn.onclick = function() { historySearchQuery = ''; var inp = document.getElementById('historyFilesSearch'); if (inp) inp.value = ''; renderAll(); };
            }
          } else {
            emptyHint.style.display = 'none';
          }
        }
      }

      function loadHistoryFiles() {
        apiFetch('/api/output/files?with_mtime=1').then(function(r) {
          if (r.status === 401 && window.showAuthScreen) window.showAuthScreen();
          return safeResponseJson(r);
        }).then(function(d) {
          historyFilesCache = (d && d.files) ? d.files : [];
          renderAll();
        }).catch(function() {
          historyFilesCache = [];
          renderAll();
        });
      }

      btnOpen.onclick = function() {
        // 每次打开都重置；并在弹窗打开后延迟多次清空，覆盖浏览器延迟自动填充
        forceClearHistorySearch();
        loadHistoryFiles();
        if (typeof refreshTrainsetSelect === 'function') refreshTrainsetSelect();
        if (typeof window.openModal === 'function') window.openModal(modal, null);
        setTimeout(forceClearHistorySearch, 0);
        setTimeout(forceClearHistorySearch, 120);
        setTimeout(forceClearHistorySearch, 500);
      };
      if (btnClose) btnClose.onclick = function() { if (typeof window.closeModal === 'function') window.closeModal(modal); };
      if (modal) modal.onclick = function(e) { if (e.target === modal && typeof window.closeModal === 'function') window.closeModal(modal); };
      if (btnRefresh) btnRefresh.onclick = loadHistoryFiles;
      if (sortSelect) sortSelect.onchange = renderAll;
      var searchInput = document.getElementById('historyFilesSearch');
      function unlockHistorySearchInput() {
        if (!searchInput) return;
        if (searchInput.hasAttribute('readonly')) searchInput.removeAttribute('readonly');
      }
      if (searchInput && typeof debounce === 'function') {
        searchInput.onfocus = unlockHistorySearchInput;
        searchInput.onmousedown = unlockHistorySearchInput;
        searchInput.ontouchstart = unlockHistorySearchInput;
        searchInput.oninput = debounce(function() {
          historySearchQuery = searchInput.value || '';
          renderAll();
        }, 300);
      }
      tabs.forEach(function(tab) {
        tab.onclick = function() {
          tabs.forEach(function(t) { t.classList.remove('active'); });
          tab.classList.add('active');
          currentCategory = tab.getAttribute('data-category') || 'cards';
          if (listCards) listCards.style.display = currentCategory === 'cards' ? 'block' : 'none';
          if (listReports) listReports.style.display = currentCategory === 'reports' ? 'block' : 'none';
          if (listTrainset) listTrainset.style.display = currentCategory === 'trainset' ? 'block' : 'none';
          if (listPersonas) listPersonas.style.display = currentCategory === 'personas' ? 'block' : 'none';
          if (listOther) listOther.style.display = currentCategory === 'other' ? 'block' : 'none';
          renderAll();
        };
      });
    })();

    async function loadPersonas() {
      const r = await apiFetch('/api/personas');
      if (r.status === 401) return;
      if (r.status === 403) return;
      const d = await safeResponseJson(r);
      const sel = document.getElementById('personaId');
      if (!sel) return;
      const opts = (d.presets || []).map(p => '<option value="' + p + '">' + p + '</option>');
      (d.custom || []).forEach(c => opts.push('<option value="' + c + '">' + c + '</option>'));
      sel.innerHTML = opts.join('') || '<option value="excellent">excellent</option>';
      var cardEditSel = document.getElementById('cardEditPersonaId');
      if (cardEditSel) cardEditSel.innerHTML = sel.innerHTML;
    }
    function runLoadPersonasWhenReady() {
      if (window.AUTH_READY) {
        loadPersonas();
        return;
      }
      document.addEventListener('eduflow:authReady', function onReady() {
        document.removeEventListener('eduflow:authReady', onReady);
        loadPersonas();
      }, { once: true });
      setTimeout(function() {
        if (!window.AUTH_READY) loadPersonas();
      }, 3000);
    }
    runLoadPersonasWhenReady();

    /** 根据当前登录用户是否具备优化器高级权限，控制「优化器类型」选择器的可见性。 */
    function applyOptimizerAdminVisibility() {
      var sel = document.getElementById('optimizerType');
      if (!sel) return;
      var label = null;
      try {
        var wrapper = sel.parentNode;
        if (wrapper && wrapper.previousElementSibling && wrapper.previousElementSibling.tagName === 'LABEL') {
          label = wrapper.previousElementSibling;
        }
      } catch (e) {}
      var isAdmin = !!(window.AUTH_USER && window.AUTH_USER.is_optimizer_admin);
      if (!isAdmin) {
        if (sel) sel.style.display = 'none';
        if (sel && sel.parentNode && sel.parentNode.style) sel.parentNode.style.display = 'none';
        if (label) label.style.display = 'none';
      } else {
        if (sel) sel.style.display = '';
        if (sel && sel.parentNode && sel.parentNode.style) sel.parentNode.style.display = '';
        if (label) label.style.display = '';
      }
    }
    (function setupOptimizerAdminVisibility() {
      if (window.AUTH_READY) {
        applyOptimizerAdminVisibility();
        return;
      }
      document.addEventListener('eduflow:authReady', function onReady() {
        document.removeEventListener('eduflow:authReady', onReady);
        applyOptimizerAdminVisibility();
      }, { once: true });
    })();

    var lastLoadedPlatformConfig = {};
    function setPlatformFormValues(d) {
      lastLoadedPlatformConfig = {
        base_url: d.base_url || 'https://cloudapi.polymas.com',
        cookie: d.cookie || '',
        authorization: d.authorization || '',
        start_node_id: d.start_node_id || '',
        end_node_id: d.end_node_id || '',
      };
      var cfgLoadUrl = document.getElementById('cfgLoadUrl');
      if (cfgLoadUrl) cfgLoadUrl.value = '';
      var el;
      (el = document.getElementById('cfgAuthorization')) && (el.value = lastLoadedPlatformConfig.authorization);
      (el = document.getElementById('cfgCookie')) && (el.value = lastLoadedPlatformConfig.cookie);
      (el = document.getElementById('cfgStartNodeId')) && (el.value = lastLoadedPlatformConfig.start_node_id);
      (el = document.getElementById('cfgEndNodeId')) && (el.value = lastLoadedPlatformConfig.end_node_id);
    }
    async function fetchPlatformConfig() {
      if (!(typeof getWorkspaceId === 'function' ? getWorkspaceId() : (window.WORKSPACE_ID || ''))) return;
      var msgEl = document.getElementById('configMsg');
      try {
        const r = await apiFetch('/api/platform/config');
        if (r.status === 401) { if (msgEl) msgEl.textContent = ''; if (window.showAuthScreen) window.showAuthScreen(); return; }
        const d = await safeResponseJson(r);
        if (r.status === 403 || r.status === 400) { if (msgEl) msgEl.textContent = ''; return; }
        if (!r.ok) throw new Error(getUserMsg(d, '加载配置失败，请稍后重试'));
        setPlatformFormValues(d);
        if (msgEl) msgEl.textContent = '已加载当前配置';
      } catch (e) {
        if (msgEl) msgEl.innerHTML = '<span class="err">' + esc(e.message || '加载配置失败，请稍后重试') + '</span>';
      }
    }
    document.getElementById('btnLoadConfig').onclick = async () => {
      const msg = document.getElementById('configMsg');
      const url = (document.getElementById('cfgLoadUrl') && document.getElementById('cfgLoadUrl').value || '').trim();
      const jwt = (document.getElementById('cfgAuthorization') && document.getElementById('cfgAuthorization').value || '').trim();
      const cookie = (document.getElementById('cfgCookie') && document.getElementById('cfgCookie').value || '').trim();
      const startNode = (document.getElementById('cfgStartNodeId') && document.getElementById('cfgStartNodeId').value || '').trim();
      const endNode = (document.getElementById('cfgEndNodeId') && document.getElementById('cfgEndNodeId').value || '').trim();
      const body = {
        url: url || undefined,
        authorization: jwt || undefined,
        cookie: cookie || undefined,
        start_node_id: startNode || undefined,
        end_node_id: endNode || undefined,
      };
      msg.textContent = '加载中…';
      try {
        const r = await apiFetch('/api/platform/load-config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const d = await safeResponseJson(r);
        if (!r.ok) throw new Error(getUserMsg(d, '加载配置失败，请稍后重试'));
        setPlatformFormValues(d);
        msg.textContent = d.message || '已加载配置';
      } catch (e) {
        msg.innerHTML = '<span class="err">' + esc(e.message || '加载配置失败，请稍后重试') + '</span>';
      }
    };
    document.getElementById('btnRunOptimizer').onclick = async function() {
      const msg = document.getElementById('optimizerMsg');
      const pre = document.getElementById('optimizerResult');
      const optBtn = document.getElementById('btnRunOptimizer');
      const progressWrap = document.getElementById('optimizerProgressWrap');
      const progressBar = document.getElementById('optimizerProgressBar');
      const progressMsg = document.getElementById('optimizerProgressMsg');
      const progressPct = document.getElementById('optimizerProgressPct');
      msg.textContent = '';
      pre.style.display = 'none';
      if (optBtn) optBtn.disabled = true;
      if (progressWrap) {
        progressWrap.style.display = 'block';
        if (progressBar) progressBar.style.width = '0%';
        if (progressMsg) progressMsg.textContent = '准备中…';
        if (progressPct) progressPct.textContent = '0%';
      }
      try {
        var roundsDefault = document.querySelector('input[name="optimizerRoundsMode"][value="default"]');
        var maxRounds = (roundsDefault && roundsDefault.checked) ? null : (parseInt(document.getElementById('optimizerMaxRoundsInput').value, 10) || 1);
        var trainsetSel = document.getElementById('optimizerTrainsetSelect');
        var trainsetPath = (trainsetSel && trainsetSel.value) ? trainsetSel.value.trim() : null;
        var isAdmin = !!(window.AUTH_USER && window.AUTH_USER.is_optimizer_admin);
        var optimizerTypeSelect = document.getElementById('optimizerType');
        var optimizerType = (isAdmin && optimizerTypeSelect && optimizerTypeSelect.value) || 'bootstrap';
        const body = {
          trainset_path: trainsetPath || null,
          devset_path: null,
          cards_output_path: null,
          export_path: null,
          optimizer_type: optimizerType,
          use_auto_eval: true,
          max_rounds: maxRounds,
          persona_id: (document.getElementById('personaId') && document.getElementById('personaId').value) || 'excellent',
        };
        const r = await apiFetch('/api/optimizer/run-stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!r.ok) throw new Error('请求失败');
        const reader = r.body.getReader();
        const decoder = new TextDecoder();
        let buf = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const chunks = buf.split('\n\n');
          buf = chunks.pop() || '';
          for (const chunk of chunks) {
            let event = null, data = null;
            for (const line of chunk.split('\n')) {
              if (line.startsWith('event: ')) event = line.slice(7).trim();
              else if (line.startsWith('data: ')) data = line.slice(6);
            }
            if (!event || !data) continue;
            try {
              const d = JSON.parse(data);
              if (event === 'progress') {
                const pct = d.percent != null ? d.percent : (d.total ? Math.round(100 * d.current / d.total) : 0);
                if (progressBar) progressBar.style.width = pct + '%';
                if (progressMsg) progressMsg.textContent = d.message || '评估中…';
                if (progressPct) progressPct.textContent = pct + '%';
              } else if (event === 'done') {
                if (progressBar) progressBar.style.width = '100%';
                if (progressMsg) progressMsg.textContent = '完成';
                if (progressPct) progressPct.textContent = '100%';
                msg.textContent = d.message || '优化完成';
                var reportPath = d.evaluation_report_path || '';
                var cardsPath = d.cards_output_path || '';
                pre.textContent = (d.hint || '') + (reportPath ? '\n\n评估报告: ' + reportPath : '') + (cardsPath ? '\n生成卡片: ' + cardsPath : '') + '\n\n' + JSON.stringify(d, null, 2);
                pre.style.display = 'block';
                var wrap = pre.parentNode;
                var btnsId = 'optimizerResultBtns';
                var existingBtns = document.getElementById(btnsId);
                if (existingBtns) existingBtns.remove();
                var btnWrap = document.createElement('div');
                btnWrap.id = btnsId;
                btnWrap.style.marginTop = '0.5rem';
                btnWrap.style.display = 'flex';
                btnWrap.style.flexWrap = 'wrap';
                btnWrap.style.gap = '0.5rem';
                if (reportPath && typeof openCardEditModal === 'function') {
                  var openReport = document.createElement('button');
                  openReport.className = 'btn secondary';
                  openReport.textContent = '查看评估报告';
                  openReport.onclick = function() { openCardEditModal(reportPath); };
                  btnWrap.appendChild(openReport);
                }
                if (cardsPath) {
                  var viewCards = document.createElement('button');
                  viewCards.className = 'btn secondary';
                  viewCards.textContent = '查看卡片';
                  viewCards.onclick = function() { if (typeof openCardEditModal === 'function') openCardEditModal(cardsPath); };
                  btnWrap.appendChild(viewCards);
                  if (typeof downloadOutputFile === 'function') {
                    var dlCards = document.createElement('button');
                    dlCards.className = 'btn secondary';
                    dlCards.textContent = '下载卡片';
                    dlCards.onclick = function() { downloadOutputFile(cardsPath); };
                    btnWrap.appendChild(dlCards);
                  }
                  var useInject = document.createElement('button');
                  useInject.className = 'btn secondary';
                  useInject.textContent = '用于注入';
                  useInject.onclick = function() {
                    var inp = document.getElementById('injectCardsPath');
                    if (inp) inp.value = cardsPath;
                  };
                  btnWrap.appendChild(useInject);
                }
                if (btnWrap.childNodes.length) wrap.insertBefore(btnWrap, pre.nextSibling);
                if (typeof refreshWorkspaceFileList === 'function') refreshWorkspaceFileList();
                if (typeof window.updateSimProgress === 'function') window.updateSimProgress({3: true});
              } else if (event === 'error') {
                throw new Error(getUserMsg(d, '优化失败，请稍后重试'));
              }
            } catch (parseErr) {
              if (event === 'error') throw new Error('优化失败，请稍后重试');
            }
          }
        }
      } catch (e) {
        msg.innerHTML = '<span class="err">' + esc(e.message || '优化失败，请稍后重试') + '</span>';
        pre.style.display = 'none';
      } finally {
        if (optBtn) optBtn.disabled = false;
        if (progressWrap) setTimeout(function() { progressWrap.style.display = 'none'; }, 2000);
      }
    };

    (function setupExportReportDropZone() {
      var dz = document.getElementById('exportReportDropZone');
      var fileInput = document.getElementById('exportReportFile');
      var msg = document.getElementById('uploadExportReportMsg');
      if (!dz || !fileInput || !msg) return;
      function doUpload(file) {
        if (!file) return;
        var ext = (file.name || '').toLowerCase();
        if (!ext.endsWith('.md') && !ext.endsWith('.json') && !ext.endsWith('.txt')) {
          msg.classList.add('err');
          msg.innerHTML = '<span class="err">仅支持 .md / .json / .txt</span>';
          return;
        }
        msg.textContent = '上传中…';
        msg.classList.remove('err');
        var fd = new FormData();
        fd.append('file', file);
        fd.append('subpath', 'optimizer');
        fd.append('save_as', 'export_score.json');
        apiFetch('/api/output/upload', { method: 'POST', body: fd }).then(function(r) { return safeResponseJson(r).then(function(d) { return { r: r, d: d }; }); }).then(function(o) {
          if (!o.r.ok) throw new Error(getUserMsg(o.d, '上传失败，请稍后重试'));
          msg.textContent = '已上传至 output/optimizer/export_score.json';
          if (typeof refreshWorkspaceFileList === 'function') refreshWorkspaceFileList();
        }).catch(function(e) {
          msg.classList.add('err');
          msg.innerHTML = '<span class="err">' + esc(e.message || '上传失败，请稍后重试') + '</span>';
        });
      }
      dz.onclick = function() { fileInput.click(); };
      fileInput.onchange = function() { doUpload(this.files && this.files[0]); this.value = ''; };
      dz.ondragover = function(e) { e.preventDefault(); this.classList.add('dragover'); };
      dz.ondragleave = function() { this.classList.remove('dragover'); };
      dz.ondrop = function(e) {
        e.preventDefault();
        this.classList.remove('dragover');
        doUpload(e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]);
      };
    })();

    var scriptDZ = document.getElementById('scriptDropZone');
    var scriptFileInput = document.getElementById('scriptFile');
    scriptDZ.onclick = function() { scriptFileInput.click(); };

    async function handleScriptFile(file) {
      if (!file) return;
      await runUploadAndAnalyze(file);
      scriptFileInput.value = '';
    }

    document.getElementById('btnGenCards').onclick = async function() {
      var msg = document.getElementById('uploadMsg');
      var genBtn = document.getElementById('btnGenCards');
      var qaEl = document.getElementById('uploadQuickActions');
      var progressWrap = document.getElementById('cardGenProgressWrap');
      var progressBar = document.getElementById('cardGenProgressBar');
      var progressMsg = document.getElementById('cardGenProgressMsg');
      var progressPct = document.getElementById('cardGenProgressPct');
      var streamPreview = document.getElementById('cardGenStreamPreview');
      if (!lastUploadData) {
        msg.innerHTML = '<span class="err">请先上传并解析剧本</span>';
        return;
      }
      msg.textContent = '';
      if (qaEl) qaEl.style.display = 'none';
      if (genBtn) genBtn.disabled = true;
      var srcName = (lastUploadData && lastUploadData.filename) ? lastUploadData.filename : (window.lastScriptFile && window.lastScriptFile.name ? window.lastScriptFile.name : '');
      if (progressWrap) {
        progressWrap.style.display = 'block';
        if (progressBar) progressBar.style.width = '0%';
        if (progressMsg) progressMsg.textContent = srcName ? '正在根据《' + srcName + '》生成卡片…' : '正在连接…';
        if (progressPct) progressPct.textContent = '0%';
      }
      if (streamPreview) streamPreview.textContent = '';
      try {
        var r = await apiFetch('/api/cards/generate-stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            full_content: lastUploadData.full_content,
            stages: lastUploadData.stages,
            framework_id: 'dspy',
            source_filename: lastUploadData.filename || null,
          }),
        });
        if (!r.ok) throw new Error(r.status === 502 ? '生成失败，请检查 LLM 配置与网络' : '请求失败');
        var reader = r.body.getReader();
        var decoder = new TextDecoder();
        var buf = '';
        var d = null;
        while (true) {
          var chunk = await reader.read();
          if (chunk.done) break;
          buf += decoder.decode(chunk.value, { stream: true });
          var parts = buf.split('\n\n');
          buf = parts.pop() || '';
          for (var i = 0; i < parts.length; i++) {
            var event = null, dataStr = null;
            parts[i].split('\n').forEach(function(line) {
              if (line.startsWith('event: ')) event = line.slice(7).trim();
              else if (line.startsWith('data: ')) dataStr = line.slice(6);
            });
            if (!event || !dataStr) continue;
            try {
              var data = JSON.parse(dataStr);
              if (event === 'progress') {
                var pct = data.percent != null ? data.percent : (data.total ? Math.round(100 * data.current / data.total) : 0);
                if (progressBar) progressBar.style.width = pct + '%';
                if (progressMsg) progressMsg.textContent = srcName ? '正在根据《' + srcName + '》生成卡片… ' + (data.message || '') : (data.message || '生成中…');
                if (progressPct) progressPct.textContent = pct + '%';
              } else if (event === 'card') {
                if (streamPreview) {
                  if (streamPreview.textContent) streamPreview.textContent += '\n\n---\n\n';
                  streamPreview.textContent += data.content || '';
                  streamPreview.scrollTop = streamPreview.scrollHeight;
                }
              } else if (event === 'done') {
                d = data;
                if (progressBar) progressBar.style.width = '100%';
                if (progressMsg) progressMsg.textContent = '完成';
                if (progressPct) progressPct.textContent = '100%';
              } else if (event === 'error') {
                throw new Error(getUserMsg(data, '生成失败，请稍后重试'));
              }
            } catch (parseErr) {
              if (event === 'error') throw new Error('生成失败，请稍后重试');
            }
          }
        }
        if (!d) throw new Error('未收到完成数据');
        var outputPath = d.output_path || d.output_filename || '';
        var escPath = (outputPath || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        msg.innerHTML = '已完成生成。卡片文件：<a href="#" class="card-path-link" data-path="' + escPath + '">' + escPath + '</a>（点击可查看并编辑）';
        if (typeof window.updateSimProgress === 'function') window.updateSimProgress({2: true});
        if (d.output_path) {
          var injectCardsPathInput = document.getElementById('injectCardsPath');
          if (injectCardsPathInput) injectCardsPathInput.value = d.output_path;
        }
      } catch (e) {
        msg.innerHTML = '<span class="err">' + esc(e.message || '生成失败，请稍后重试') + '</span>';
      } finally {
        if (genBtn) genBtn.disabled = false;
        if (progressWrap) setTimeout(function() { progressWrap.style.display = 'none'; }, 8000);
      }
    };
    scriptFileInput.onchange = function() { handleScriptFile(this.files[0]); };
    scriptDZ.ondragover = function(e) { e.preventDefault(); this.classList.add('dragover'); };
    scriptDZ.ondragleave = function() { this.classList.remove('dragover'); };
    scriptDZ.ondrop = async function(e) {
      e.preventDefault();
      this.classList.remove('dragover');
      if (window._eduflowDraggedFileHandle) {
        try {
          var file = await window._eduflowDraggedFileHandle.getFile();
          if (file) handleScriptFile(file);
        } catch (err) {}
        window._eduflowDraggedFileHandle = null;
        return;
      }
      var f = e.dataTransfer.files[0];
      if (f) handleScriptFile(f);
    };

    /** 将任意路径规范为后端可用的形式：只保留 output/... 或 input/... 或相对文件名，去掉多余前缀 */
    function normalizePathForBackend(path) {
      if (!path || typeof path !== 'string') return '';
      var p = path.replace(/\\/g, '/').trim().replace(/^\/+/, '');
      var o = p.indexOf('output/');
      var i = p.indexOf('input/');
      if (o !== -1) return p.substring(o);
      if (i !== -1) return p.substring(i);
      return p;
    }
    (function setupPathDropTargets() {
      document.querySelectorAll('.path-drop-target').forEach(function(inp) {
        inp.onfocus = function() { lastFocusedPathInput = inp; };
        inp.ondragover = function(e) {
          e.preventDefault();
          if (e.dataTransfer.types.indexOf('text/plain') !== -1) inp.classList.add('drag-over');
          e.dataTransfer.dropEffect = 'copy';
        };
        inp.ondragleave = function() { inp.classList.remove('drag-over'); };
        inp.ondrop = function(e) {
          e.preventDefault();
          inp.classList.remove('drag-over');
          if (window._eduflowDraggedPath) {
            inp.value = normalizePathForBackend(window._eduflowDraggedPath);
          }
        };
      });
    })();

    (function setupSimSidebar() {
      var sidebar = document.getElementById('simSidebar');
      var tab = document.getElementById('simSidebarTab');
      var closeBtn = document.getElementById('simSidebarClose');
      function openSidebar() {
        if (sidebar) sidebar.classList.add('open');
        document.body.classList.add('sim-sidebar-open');
      }
      function closeSidebar() {
        if (sidebar) sidebar.classList.remove('open');
        document.body.classList.remove('sim-sidebar-open');
      }
      if (tab) tab.onclick = openSidebar;
      if (closeBtn) closeBtn.onclick = closeSidebar;
      var navBtn = document.getElementById('btnSimNav');
      if (navBtn) navBtn.onclick = function() {
        if (sidebar && sidebar.classList.contains('open')) closeSidebar();
        else openSidebar();
      };
      window.toggleSimSidebar = function() {
        if (sidebar && sidebar.classList.contains('open')) closeSidebar();
        else openSidebar();
      };
      (function setupSimSidebarSwipe() {
        if (!sidebar) return;
        var dragPx = 0, touchStartX = null, wheelAccum = 0, wheelEndTimer = null;
        var COMMIT_RATIO = 0.35;
        var WHEEL_END_MS = 120;
        var transitionEase = 'cubic-bezier(0.16, 1, 0.3, 1)';
        function getWidth() { return sidebar.getBoundingClientRect().width || 380; }
        function applyDrag(px) {
          sidebar.style.transition = 'none';
          sidebar.style.transform = 'translateX(' + Math.max(0, Math.min(px, getWidth())) + 'px)';
        }
        function endDrag(commit) {
          if (commit) {
            sidebar.style.transition = 'transform 0.25s ' + transitionEase;
            sidebar.style.transform = '';
            closeSidebar();
          } else {
            sidebar.style.transition = 'transform 0.3s ' + transitionEase;
            sidebar.style.transform = 'translateX(0)';
            var onEnd = function() {
              sidebar.removeEventListener('transitionend', onEnd);
              sidebar.style.transition = '';
              sidebar.style.transform = '';
            };
            sidebar.addEventListener('transitionend', onEnd);
          }
          dragPx = 0;
          wheelAccum = 0;
          touchStartX = null;
        }
        sidebar.addEventListener('wheel', function(e) {
          if (!sidebar.classList.contains('open')) return;
          if (Math.abs(e.deltaX) < Math.abs(e.deltaY)) return;
          e.preventDefault();
          wheelAccum -= e.deltaX;
          wheelAccum = Math.max(0, Math.min(wheelAccum, getWidth()));
          applyDrag(wheelAccum);
          clearTimeout(wheelEndTimer);
          wheelEndTimer = setTimeout(function() {
            wheelEndTimer = null;
            var th = getWidth() * COMMIT_RATIO;
            endDrag(wheelAccum >= th);
          }, WHEEL_END_MS);
        }, { passive: false });
        sidebar.addEventListener('touchstart', function(e) {
          touchStartX = e.touches[0].clientX;
          dragPx = 0;
        }, { passive: true });
        sidebar.addEventListener('touchmove', function(e) {
          if (touchStartX == null || !sidebar.classList.contains('open')) return;
          var dx = e.touches[0].clientX - touchStartX;
          dragPx = Math.max(0, Math.min(dx, getWidth()));
          applyDrag(dragPx);
          if (Math.abs(dx) > 8) e.preventDefault();
        }, { passive: false });
        sidebar.addEventListener('touchend', function(e) {
          if (touchStartX == null) return;
          var th = getWidth() * COMMIT_RATIO;
          endDrag(dragPx >= th);
        }, { passive: true });
      })();
      (function setupSimSidebarResize() {
        var SIM_WIDTH_KEY = 'eduflow_sim_sidebar_width';
        var MIN_W = 280, MAX_W = 600, DEFAULT_W = 380;
        var root = document.documentElement;
        function getW() {
          var w = parseFloat(getComputedStyle(root).getPropertyValue('--sim-sidebar-width'));
          return isNaN(w) ? DEFAULT_W : w;
        }
        function setW(px) {
          px = Math.min(MAX_W, Math.max(MIN_W, px));
          root.style.setProperty('--sim-sidebar-width', px + 'px');
          try { localStorage.setItem(SIM_WIDTH_KEY, String(px)); } catch (e) {}
        }
        try {
          var s = localStorage.getItem(SIM_WIDTH_KEY);
          if (s != null) { var n = parseFloat(s); if (!isNaN(n)) setW(n); }
        } catch (e) {}
        var handle = document.getElementById('simSidebarResizeHandle');
        if (handle) {
          handle.onmousedown = function(e) {
            if (!sidebar || !sidebar.classList.contains('open')) return;
            e.preventDefault();
            var startX = e.clientX, startW = getW();
            function onMove(ev) { setW(startW - (ev.clientX - startX)); }
            function onUp() {
              document.removeEventListener('mousemove', onMove);
              document.removeEventListener('mouseup', onUp);
            }
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
          };
        }
      })();
      window._simProgressSteps = window._simProgressSteps || {1: false, 2: false, 3: false, 4: false};
      window.updateSimProgress = function(steps) {
        if (steps) {
          for (var k in steps) window._simProgressSteps[k] = !!steps[k];
        }
        var list = document.getElementById('simProgressList');
        if (!list) return;
        var items = list.querySelectorAll('.sim-progress-item');
        var s = window._simProgressSteps;
        items.forEach(function(el) {
          var step = el.getAttribute('data-step');
          if (s[step]) {
            el.classList.add('done');
            el.querySelector('span').textContent = '✓';
          } else {
            el.classList.remove('done');
            el.querySelector('span').textContent = '○';
          }
        });
      };
    })();
    function setButtonsEnabled(ids, enabled) {
      (ids || []).forEach(function(id) {
        var el = document.getElementById(id);
        if (el) el.disabled = !enabled;
      });
    }
    // 外部评估模式已移除，统一使用闭环自动评估

    document.getElementById('btnInjectPreview').onclick = async () => {
      const path = document.getElementById('injectCardsPath').value.trim();
      const msg = document.getElementById('injectMsg');
      const pre = document.getElementById('injectResult');
      if (!path) { msg.innerHTML = '<span class="err">请从右侧工作区文件列表拖入或点击文件填入卡片</span>'; return; }
      msg.textContent = '预览中...';
      try {
        const r = await apiFetch( '/api/inject/preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ cards_path: path }),
        });
        const d = await safeResponseJson(r);
        if (!r.ok) throw new Error(getUserMsg(d, '预览失败，请稍后重试'));
        msg.textContent = d.summary || ('A类 ' + d.total_a + '，B类 ' + d.total_b);
        pre.style.display = 'block';
        pre.textContent = JSON.stringify(d, null, 2);
      } catch (e) {
        msg.innerHTML = '<span class="err">' + esc(e.message || '预览失败，请稍后重试') + '</span>';
        pre.style.display = 'none';
      }
    };

    document.getElementById('btnInjectRun').onclick = async () => {
      const path = document.getElementById('injectCardsPath').value.trim();
      const msg = document.getElementById('injectMsg');
      const pre = document.getElementById('injectResult');
      if (!path) { msg.innerHTML = '<span class="err">请从右侧工作区文件列表拖入或点击文件填入卡片</span>'; return; }
      msg.textContent = '注入中...';
      showLongTaskFeedback('注入平台中，请稍候…');
      try {
        const r = await apiFetch( '/api/inject/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ cards_path: path }),
        });
        const d = await safeResponseJson(r);
        if (!r.ok) throw new Error(getUserMsg(d, '注入失败，请稍后重试'));
        msg.textContent = d.message || (d.success ? '注入成功' : '注入完成，请查看详情');
        if (d.success && typeof window.updateSimProgress === 'function') window.updateSimProgress({4: true});
        if (!d.success) msg.innerHTML = '<span class="err">' + esc(msg.textContent) + '</span>';
        pre.style.display = 'block';
        pre.textContent = JSON.stringify(d, null, 2);
      } catch (e) {
        msg.innerHTML = '<span class="err">' + esc(e.message || '注入失败，请稍后重试') + '</span>';
        pre.style.display = 'none';
      } finally {
        hideLongTaskFeedback();
      }
    };
