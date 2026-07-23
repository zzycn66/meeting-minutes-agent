const API_BASE = '';

class MeetingApp {
    constructor() {
        this.currentMeetingId = null;
        this.currentMinutes = null;
        this.actionItems = [];
        this.currentUser = null;
        this.sessionToken = null;
        this.currentTemplate = null;
        this.templates = [];
        this.isRecording = false;
        this._progressTimers = [];
        this._mediaRecorder = null;
        this._audioChunks = [];
        this._recordStream = null;
        this._analyserStream = null;
        this._recordStartTime = 0;
        this._recordTimerInterval = null;
        this._audioContext = null;
        this._analyser = null;
        this._waveformAnimId = null;
        this._lastRecordingBlob = null;
        this._lastRecordingName = null;
        this.currentAudioFile = null;
        this._ws = null;
        this._subtitleLines = [];
        this._currentSubtitleEl = null;
        this._subtitleNeedNewLine = true;
        this._isWaitingForStop = false;
        this._stopConfirmTimer = null;
    }

    async init() {
        this._bindEvents();
        this._bindKeyboardShortcuts();
        this._loadDraft();
        this._setupAutoSave();
        this._setupInputValidation();
        this._cacheDOMElements();
        await this._checkLoginStatus();
        await this.loadHistory();
        this._drawIdleWaveform();
        this._updateGridLayout();
    }

    _cacheDOMElements() {
        this._els = {
            progressSection: document.getElementById('progressSection'),
            progressLabel: document.getElementById('progressLabel'),
            progressPercent: document.getElementById('progressPercent'),
            progressBar: document.getElementById('progressBar'),
            progressDetail: document.getElementById('progressDetail'),
        };
    }

    requireLogin(action) {
        if (!this.currentUser) {
            this.showLoginModal();
            this.showToast('请先登录', 'warning');
            return false;
        }
        return true;
    }

    // ── Event Binding ──────────────────────────────────
    _bindEvents() {
        const dropZone = document.getElementById('dropZone');
        const fileInput = document.getElementById('fileInput');

        dropZone.addEventListener('click', () => fileInput.click());
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('drag-over');
        });
        dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('drag-over');
            if (e.dataTransfer.files.length) this.handleFile(e.dataTransfer.files[0]);
        });
        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length) this.handleFile(e.target.files[0]);
        });

        document.getElementById('btnSubmitText').addEventListener('click', () => this.submitText());
        document.getElementById('btnSubmitRecord').addEventListener('click', () => this.submitRecordResult());
        document.getElementById('btnGenerateMinutes').addEventListener('click', () => this.generateMinutes());
        document.getElementById('btnExportMD').addEventListener('click', () => this.exportMarkdown());
        document.getElementById('btnExportDocx').addEventListener('click', () => this.exportDocx());
        document.getElementById('btnAddAction').addEventListener('click', () => this.addActionItem());
    }

    // ── Keyboard Shortcuts ──────────────────────────────
    _bindKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                const activeTab = document.querySelector('.tab-content.active');
                if (activeTab && activeTab.id === 'tab-text') {
                    e.preventDefault();
                    this.submitText();
                } else if (activeTab && activeTab.id === 'tab-result') {
                    e.preventDefault();
                    this.submitRecordResult();
                }
            }
        });
    }

    // ── Draft Auto-Save ─────────────────────────────────
    _loadDraft() {
        try {
            const draft = JSON.parse(localStorage.getItem('meetingDraft') || '{}');
            if (draft.title) document.getElementById('meetingTitle').value = draft.title;
            if (draft.participants) document.getElementById('participants').value = draft.participants;
            if (draft.date) document.getElementById('meetingDate').value = draft.date;
            if (draft.text) document.getElementById('textInput').value = draft.text;
            if (draft.isPublic !== undefined) document.getElementById('isPublic').checked = draft.isPublic;
        } catch (e) { /* ignore */ }
    }

    _setupAutoSave() {
        this._autoSaveTimer = null;
        const fields = ['meetingTitle', 'participants', 'meetingDate', 'textInput'];
        fields.forEach(id => {
            document.getElementById(id).addEventListener('input', () => {
                clearTimeout(this._autoSaveTimer);
                this._autoSaveTimer = setTimeout(() => this._saveDraft(), 300);
            });
        });
        const isPublicEl = document.getElementById('isPublic');
        if (isPublicEl) {
            isPublicEl.addEventListener('change', () => {
                clearTimeout(this._autoSaveTimer);
                this._autoSaveTimer = setTimeout(() => this._saveDraft(), 300);
            });
        }
    }

    _saveDraft() {
        const draft = {
            title: document.getElementById('meetingTitle').value,
            participants: document.getElementById('participants').value,
            date: document.getElementById('meetingDate').value,
            text: document.getElementById('textInput').value,
            isPublic: document.getElementById('isPublic')?.checked || false,
        };
        localStorage.setItem('meetingDraft', JSON.stringify(draft));
    }

    _clearDraft() {
        localStorage.removeItem('meetingDraft');
    }

    _clearForm() {
        document.getElementById('meetingTitle').value = '';
        document.getElementById('meetingDate').value = '';
        document.getElementById('participants').value = '';
        document.getElementById('textInput').value = '';
        const isPublicEl = document.getElementById('isPublic');
        if (isPublicEl) isPublicEl.checked = false;
    }

    // ── Input Validation ────────────────────────────────
    _setupInputValidation() {
        const textarea = document.getElementById('textInput');
        const counter = document.createElement('div');
        counter.className = 'char-counter';
        counter.id = 'charCounter';
        textarea.parentNode.insertBefore(counter, textarea.nextSibling);
        this._updateCharCounter();

        textarea.addEventListener('input', () => this._updateCharCounter());
    }

    _updateCharCounter() {
        const textarea = document.getElementById('textInput');
        const counter = document.getElementById('charCounter');
        if (!counter) return;
        const len = textarea.value.trim().length;
        counter.textContent = len > 0 ? `${len} 字` : '';
        counter.classList.toggle('warn', len > 0 && len < 10);
        counter.classList.toggle('ok', len >= 10);
    }

    // ── Tabs ───────────────────────────────────────────
    switchTab(name) {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        const tab = document.querySelector(`.tab[onclick*="${name}"]`);
        if (tab) tab.classList.add('active');
        const content = document.getElementById('tab-' + name);
        if (content) content.classList.add('active');
        if (name === 'record' && !this.isRecording) {
            requestAnimationFrame(() => this._drawIdleWaveform());
        }
    }

    // ── Progress Bar ───────────────────────────────────
    showProgress(label, percent, detail) {
        const el = this._els;
        el.progressSection.style.display = 'block';
        el.progressSection.classList.remove('completed', 'error');
        el.progressLabel.textContent = label;
        el.progressPercent.textContent = percent + '%';
        el.progressBar.style.width = percent + '%';
        el.progressDetail.textContent = detail;
    }

    updateProgress(label, percent, detail) {
        const el = this._els;
        el.progressLabel.textContent = label;
        el.progressPercent.textContent = percent + '%';
        el.progressBar.style.width = percent + '%';
        if (detail) el.progressDetail.textContent = detail;
    }

    completeProgress(detail) {
        const el = this._els;
        el.progressSection.classList.add('completed');
        el.progressBar.classList.remove('animating');
        this.updateProgress('完成', '100', detail);
    }

    errorProgress(detail) {
        const el = this._els;
        el.progressSection.classList.add('error');
        el.progressBar.classList.remove('animating');
        this.updateProgress('失败', '0', detail);
    }

    hideProgress() {
        this._els.progressSection.style.display = 'none';
    }

    _clearProgressTimers() {
        this._progressTimers.forEach(t => clearTimeout(t));
        this._progressTimers = [];
        this._els.progressBar.classList.remove('animating');
    }

    _startProgressAnimation() {
        this._els.progressBar.classList.add('animating');
        const stages = [
            { delay: 3000, pct: 20, detail: '正在处理音频数据...' },
            { delay: 8000, pct: 35, detail: '正在分析语音模式...' },
            { delay: 15000, pct: 50, detail: '正在转换为文字...' },
            { delay: 25000, pct: 65, detail: '正在优化转写结果...' },
            { delay: 40000, pct: 80, detail: '识别进行中，请稍候...' },
            { delay: 60000, pct: 90, detail: '即将完成...' },
        ];
        this._progressTimers = stages.map(s =>
            setTimeout(() => this.updateProgress('识别中', s.pct, s.detail), s.delay)
        );
    }

    // ── File Upload ────────────────────────────────────
    async handleFile(file) {
        console.log('[handleFile] start', file?.name);
        const ext = file.name.split('.').pop().toLowerCase();
        const allowed = ['mp3', 'wav', 'm4a', 'aac', 'wma', 'ogg', 'flac'];
        if (!allowed.includes(ext)) {
            this.showToast('不支持的音频格式：.' + ext, 'error');
            return;
        }

        const fileSize = (file.size / 1024 / 1024).toFixed(1);
        const realtimeToggle = document.getElementById('enableFileRealtime'); const realtime = realtimeToggle ? realtimeToggle.checked : true; if (!this.sessionToken) { this.sessionToken = this._getCookie('session_token') || null; } console.log('[handleFile] realtime=', realtime, 'token=', !!this.sessionToken);

        let transcriptText = '';
        try {
            // 上传阶段：有上传进度
            this.showProgress('上传中…', 0, file.name + ' (' + fileSize + ' MB)');
            const formData = new FormData();
            formData.append('file', file);
            const uploadResult = await this._uploadWithProgress(formData, fileSize);
            const filename = uploadResult.data.filename;
            this.currentAudioFile = filename;

            if (!document.getElementById('meetingTitle').value) {
                const nameWithoutExt = file.name.replace(/\.[^.]+$/, '');
                document.getElementById('meetingTitle').value = nameWithoutExt + ' - Meeting';
            }

            // 默认优先实时流式（WebSocket），用户关闭开关则走同步识别
            if (realtime) {
                try {
                    this._showFileSubtitleBar();
                    this.updateProgress('语音识别中…', 0, '音频已上传，正在连接识别服务…');
                    transcriptText = await this._transcribeFileViaWS(filename, true);
                    if (!transcriptText) throw new Error('实时转写未返回内容');
                } catch (wsErr) {
                    console.warn('[handleFile] WS realtime failed, fallback:', wsErr);
                    this._hideFileSubtitleBar();
                    this.updateProgress('语音识别中…', 0, '实时通道不可用，正在切换识别方式…');
                    transcriptText = '';
                }
            }

            if (!transcriptText) {
                this.hideProgress();
                this.showLoading('正在识别语音，请稍候…');
                const asrEngine = document.getElementById('asrSelect').value;
                const resp = await fetch(API_BASE + '/api/meetings/recognize', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: 'filepath=' + encodeURIComponent(filename) + '&asr_engine=' + encodeURIComponent(asrEngine),
                });
                const data = await resp.json();
                this.hideLoading();
                if (!data.success) throw new Error(data.message);
                transcriptText = data.data.text || '';
            }

            this._updateFileSubtitleStatus('完成');
            this.completeProgress('语音识别完成!');
            document.getElementById('recordResultText').textContent = transcriptText;
            document.getElementById('tabBtnResult').style.display = '';
            this.switchTab('result');
            this.showToast('语音识别完成', 'success');
            document.getElementById('recordResultText').scrollIntoView({ behavior: 'smooth', block: 'center' });
            setTimeout(() => this.hideProgress(), 2000);
        } catch (err) {
            this._hideFileSubtitleBar();
            this.hideLoading();
            this.hideProgress();
            this.showToast('语音识别失败: ' + err.message, 'error');
        }
    }
    _showFileSubtitleBar() {
        const bar = document.getElementById('fileSubtitleBar');
        const content = document.getElementById('fileSubtitleContent');
        bar.style.display = 'block';
        content.innerHTML = '<div class="subtitle-placeholder">等待识别...</div>';
        this._updateFileSubtitleStatus('连接中...');
    }

    _hideFileSubtitleBar() {
        document.getElementById('fileSubtitleBar').style.display = 'none';
    }

    _updateFileSubtitleStatus(text) {
        const statusEl = document.getElementById('fileSubtitleStatus');
        if (statusEl) {
            statusEl.innerHTML = '<span class="connection-dot"></span><span>' + text + '</span>';
        }
    }

    _appendFileSubtitleText(text) {
        const container = document.getElementById('fileSubtitleContent');
        if (!container) return;

        const placeholder = container.querySelector('.subtitle-placeholder');
        if (placeholder) placeholder.remove();

        // 复用录音 tab 的字幕行样式
        let currentLine = container.querySelector('.file-subtitle-line:last-child');
        if (!currentLine || currentLine.dataset.done === '1') {
            currentLine = document.createElement('div');
            currentLine.className = 'subtitle-line confirmed file-subtitle-line';
            currentLine.style.opacity = '0';
            currentLine.style.transform = 'translateY(8px)';
            container.appendChild(currentLine);
            requestAnimationFrame(() => {
                currentLine.style.transition = 'opacity 0.2s ease, transform 0.2s ease';
                currentLine.style.opacity = '1';
                currentLine.style.transform = 'translateY(0)';
            });
        }
        currentLine.textContent += text;
        container.scrollTop = container.scrollHeight;
    }

    _finishFileSubtitleLine() {
        const container = document.getElementById('fileSubtitleContent');
        if (!container) return;
        const lastLine = container.querySelector('.file-subtitle-line:last-child');
        if (lastLine) lastLine.dataset.done = '1';
    }

    _transcribeFileViaWS(filename, realtime) {
        return new Promise((resolve, reject) => {
            const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
            let wsUrl = `${protocol}//${location.host}/ws/transcribe`;
            if (this.sessionToken) {
                wsUrl += '?token=' + encodeURIComponent(this.sessionToken);
            }

            const ws = new WebSocket(wsUrl);
            let fullText = '';
            let settled = false;
            const timeout = setTimeout(() => {
                if (!settled) { settled = true; ws.close(); reject(new Error('转写超时')); }
            }, 600000);

            ws.onopen = () => {
                if (realtime) this._updateFileSubtitleStatus('转写中...');
                ws.send(JSON.stringify({
                    type: 'start',
                    mode: 'file',
                    file_path: filename,
                }));
            };

            ws.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    console.log('[WS] msg:', msg.type, msg.message || msg.text?.substring(0, 50) || msg.progress);
                    if ((msg.type === 'progress' || msg.type === 'status') && typeof msg.progress === 'number') {
                        const pct = Math.round(msg.progress * 100);
                        this.updateProgress('语音识别中…', pct,
                            msg.message || `识别进度 ${pct}%`);
                        if (realtime) this._updateFileSubtitleStatus(`识别中 ${pct}%`);
                    } else if (msg.type === 'transcript' && msg.text) {
                        fullText += msg.text;
                        if (realtime) this._appendFileSubtitleText(msg.text);
                    } else if (msg.type === 'newline') {
                        if (realtime) this._finishFileSubtitleLine();
                    } else if (msg.type === 'status' && msg.message === '处理完成') {
                        if (!settled) { settled = true; clearTimeout(timeout); ws.close(); resolve(fullText); }
                    } else if (msg.type === 'error') {
                        if (!settled) { settled = true; clearTimeout(timeout); ws.close(); reject(new Error(msg.message)); }
                    }
                } catch (e) { /* ignore parse errors */ }
            };

            ws.onerror = () => {
                if (!settled) { settled = true; clearTimeout(timeout); reject(new Error('WebSocket 连接失败')); }
            };

            ws.onclose = () => {
                if (!settled) {
                    // If we already got text, treat close as success (server closed after done)
                    // If no text at all, it's an unexpected disconnect
                    settled = true;
                    clearTimeout(timeout);
                    if (fullText) {
                        resolve(fullText);
                    } else {
                        reject(new Error('WebSocket 连接意外断开'));
                    }
                }
            };
        });
    }
    _uploadWithProgress(formData, fileSizeLabel) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    const pct = Math.round((e.loaded / e.total) * 100);
                    this.updateProgress('上传中…', pct,
                        (e.loaded / 1024 / 1024).toFixed(1) + ' / ' + fileSizeLabel + ' MB');
                }
            });
            xhr.addEventListener('load', () => {
                try {
                    const data = JSON.parse(xhr.responseText);
                    if (data.success) resolve(data);
                    else reject(new Error(data.message || '上传失败'));
                } catch (e) {
                    reject(new Error('无效的服务器响应'));
                }
            });
            xhr.addEventListener('error', () => reject(new Error('网络错误')));
            xhr.open('POST', API_BASE + '/api/meetings/upload-audio');
            xhr.send(formData);
        });
    }

    // ── Text Submission ────────────────────────────────
    async submitText() {
        if (!this.requireLogin()) return;

        const text = document.getElementById('textInput').value.trim();
        const title = document.getElementById('meetingTitle').value.trim() || '会议 ' + new Date().toLocaleDateString('zh-CN');
        const participants = document.getElementById('participants').value.trim();
        const meetingDate = document.getElementById('meetingDate').value;
        const isPublic = document.getElementById('isPublic')?.checked || false;

        if (!text) {
            this.showToast('请输入会议内容', 'warning');
            return;
        }
        if (text.trim().length < 10) {
            this.showToast('会议内容至少需要10个字符', 'warning');
            return;
        }

        this.showLoading('正在创建会议记录…');
        try {
            const resp = await fetch(API_BASE + '/api/meetings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    title,
                    meeting_date: meetingDate || null,
                    participants,
                    input_type: 'text',
                    raw_text: text,
                    is_public: isPublic,
                }),
            });
            const data = await resp.json();
            if (!data.success) throw new Error(data.message);

            this.currentMeetingId = data.data.id;
            this._clearDraft();
            await this.loadHistory();
            this.showToast('会议记录已创建！点击 「生成会议纪要」开始分析', 'success');
            document.getElementById('generateSection').style.display = 'block';
            document.getElementById('resultSection').style.display = 'none';
            this._updateGridLayout();
            document.getElementById('btnGenerateMinutes').scrollIntoView({ behavior: 'smooth', block: 'center' });
        } catch (err) {
            this.showToast('创建失败：' + err.message, 'error');
        }
        this.hideLoading();
    }

    async submitRecordResult() {
        if (!this.requireLogin()) return;

        const text = document.getElementById('recordResultText').textContent.trim();
        const title = document.getElementById('meetingTitle').value.trim() || '会议 ' + new Date().toLocaleDateString('zh-CN');
        const participants = document.getElementById('participants').value.trim();
        const meetingDate = document.getElementById('meetingDate').value;
        const isPublic = document.getElementById('isPublic')?.checked || false;

        if (!text) {
            this.showToast('识别结果为空', 'warning');
            return;
        }
        if (text.trim().length < 10) {
            this.showToast('识别内容至少需要10个字符', 'warning');
            return;
        }

        this.showLoading('正在创建会议记录…');
        try {
            const resp = await fetch(API_BASE + '/api/meetings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    title,
                    meeting_date: meetingDate || null,
                    participants,
                    input_type: 'audio',
                    raw_text: text,
                    is_public: isPublic,
                }),
            });
            const data = await resp.json();
            if (!data.success) throw new Error(data.message);

            this.currentMeetingId = data.data.id;
            this._clearDraft();
            await this.loadHistory();
            this.showToast('会议记录已创建！点击 「生成会议纪要」开始分析', 'success');
            document.getElementById('generateSection').style.display = 'block';
            document.getElementById('resultSection').style.display = 'none';
            this._updateGridLayout();
            document.getElementById('btnGenerateMinutes').scrollIntoView({ behavior: 'smooth', block: 'center' });
        } catch (err) {
            this.showToast('创建失败：' + err.message, 'error');
        }
        this.hideLoading();
    }

    // ── Generate Minutes ───────────────────────────────
    async generateMinutes() {
        if (!this.requireLogin()) return;

        if (!this.currentMeetingId) {
            this.showToast('请先提交会议文本', 'warning');
            return;
        }

        const engine = document.getElementById('engineSelect').value || 'keyword';
        const useProgress = engine === 'qwen';
        this.showLoading('正在智能分析会议内容…', useProgress);

        let ws = null;
        if (useProgress) {
            ws = this._connectInferenceWS(this.currentMeetingId);
        }

        try {
            const maxTokens = document.getElementById('qwenMaxTokens').value || '0';
            let url = API_BASE + '/api/minutes/generate/' + this.currentMeetingId + '?engine=' + engine;
            if (engine === 'qwen' && maxTokens !== '0') {
                url += '&max_tokens=' + maxTokens;
            }
            if (this.currentTemplate && this.currentTemplate.id) {
                url += '&template_id=' + this.currentTemplate.id;
            }
            const resp = await fetch(url, { method: 'POST' });
            if (!resp.ok) {
                let errMsg = `HTTP ${resp.status}`;
                try { const errBody = await resp.json(); errMsg = errBody.detail || errBody.message || errMsg; } catch (_) {}
                throw new Error(errMsg);
            }
            const data = await resp.json();
            if (!data.success) throw new Error(data.message);

            this.currentMinutes = data.data;
            this.actionItems = data.data.action_items || [];
            document.getElementById('minutesContent').innerHTML = DOMPurify.sanitize(data.data.html || data.data.markdown);
            document.getElementById('resultSection').style.display = 'block';
            this._updateGridLayout();
            document.getElementById('actionCount').textContent = this.actionItems.length;
            this.renderActionItems();
            document.getElementById('resultSection').scrollIntoView({ behavior: 'smooth', block: 'start' });
            this.showToast('纪要生成成功', 'success');
        } catch (err) {
            this.showToast('生成失败：' + err.message, 'error');
        } finally {
            this._closeInferenceWS();
            this.hideLoading();
        }
    }

    // ── Action Items ───────────────────────────────────
    renderActionItems() {
        const list = document.getElementById('actionItemsList');
        document.getElementById('actionCount').textContent = this.actionItems.length;

        if (!this.actionItems.length) {
            list.innerHTML = '<li class="empty-state"><p>暂无行动项</p></li>';
            return;
        }

        list.innerHTML = this.actionItems.map((item, i) => `
            <li class="action-item" id="action-${i}">
                <input type="checkbox" class="action-checkbox" onchange="app.toggleAction(${i})">
                <div class="action-content">
                    <div>${this._esc(item.content)}</div>
                    <div class="action-meta">
                        ${item.responsible_person ? `<span>负责人: ${this._esc(item.responsible_person)}</span>` : ''}
                        ${item.deadline ? `<span>截止: ${this._esc(item.deadline)}</span>` : ''}
                        <span class="priority-${item.priority || 'medium'}">优先级: ${item.priority || 'medium'}</span>
                    </div>
                </div>
            </li>
        `).join('');
    }

    toggleAction(index) {
        document.getElementById('action-' + index).classList.toggle('completed');
    }

    async addActionItem() {
        if (!this.requireLogin()) return;

        if (!this.currentMeetingId) {
            this.showToast('请先生成会议纪要', 'warning');
            return;
        }
        document.getElementById('actionItemContent').value = '';
        document.getElementById('actionItemPerson').value = '';
        document.getElementById('actionItemDeadline').value = '';
        document.getElementById('actionItemPriority').value = 'medium';
        document.getElementById('actionItemModal').style.display = 'flex';
    }

    closeActionItemModal() {
        document.getElementById('actionItemModal').style.display = 'none';
    }

    async submitActionItem() {
        const content = document.getElementById('actionItemContent').value.trim();
        if (!content) {
            this.showToast('请输入行动项内容', 'warning');
            return;
        }
        const person = document.getElementById('actionItemPerson').value.trim();
        const deadline = document.getElementById('actionItemDeadline').value.trim();
        const priority = document.getElementById('actionItemPriority').value;

        try {
            const resp = await fetch(API_BASE + '/api/minutes/' + this.currentMeetingId + '/actions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content, responsible_person: person, deadline, priority }),
            });
            const data = await resp.json();
            if (!data.success) throw new Error(data.message);
            this.actionItems.push({ content, responsible_person: person, deadline, priority });
            this.renderActionItems();
            this.closeActionItemModal();
            this.showToast('行动项添加成功', 'success');
        } catch (err) {
            this.showToast('添加失败：' + err.message, 'error');
        }
    }

    // ── Export ─────────────────────────────────────────
    async exportDocx() {
        if (!this.requireLogin()) return;

        if (!this.currentMeetingId) {
            this.showToast('请先生成会议纪要', 'warning');
            return;
        }
        window.open(API_BASE + '/api/export/docx/' + this.currentMeetingId, '_blank');
        this.showToast('正在下载 Word 文档…', 'success');
    }

    async exportMarkdown() {
        if (!this.requireLogin()) return;

        if (!this.currentMeetingId) {
            this.showToast('请先生成会议纪要', 'warning');
            return;
        }
        try {
            const resp = await fetch(API_BASE + '/api/export/markdown/' + this.currentMeetingId);
            const data = await resp.json();
            if (data.success) {
                const blob = new Blob([data.data.markdown], { type: 'text/markdown' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'meeting_minutes_' + this.currentMeetingId + '.md';
                a.click();
                URL.revokeObjectURL(url);
                this.showToast('Markdown 导出成功', 'success');
            }
        } catch (err) {
            this.showToast('导出失败', 'error');
        }
    }

    // ── History ────────────────────────────────────────
    async loadHistory(page = 1) {
        this._historyPage = page;
        const tbody = document.getElementById('historyTableBody');
        try {
            let data;
            if (this.currentUser) {
                const resp = await fetch(API_BASE + `/api/meetings?page=${page}&size=10`, {
                    credentials: 'same-origin'
                });
                data = await resp.json();
            } else {
                const resp = await fetch(API_BASE + `/api/public/meetings?page=${page}&size=10`);
                data = await resp.json();
            }
            if (!data.success) return;

            if (!data.data.items.length) {
                const colCount = this.currentUser ? 6 : 4;
                tbody.innerHTML = `<tr><td colspan="${colCount}" class="empty-state">${this.currentUser ? '暂无会议记录' : '暂无公开会议记录'}</td></tr>`;
                return;
            }

            tbody.innerHTML = data.data.items.map(m => {
                const isOwner = this.currentUser && m.created_by === this.currentUser.id;
                if (this.currentUser) {
                    const statusMap = { completed: '已完成', processing: '处理中', failed: '失败' };
                    const publicLabel = m.is_public ? '<span class="status-badge status-public">公开</span>' : '<span class="status-badge status-private">私有</span>';
                    const publicToggle = `<button class="btn btn-xs btn-outline" onclick="app.togglePublic(${m.id})">${m.is_public ? '取消公开' : '设为公开'}</button>`;
                    return `<tr>
                        <td><strong>${this._esc(m.title)}</strong></td>
                        <td>${m.meeting_date ? new Date(m.meeting_date).toLocaleDateString('zh-CN') : '-'}</td>
                        <td>${m.participants || '-'}</td>
                        <td><span class="status-badge status-${m.status}">${statusMap[m.status] || m.status}</span></td>
                        <td>${publicLabel} ${isOwner ? publicToggle : ''}</td>
                        <td>
                            <button class="btn btn-sm btn-outline" onclick="app.loadMeeting(${m.id})">查看</button>
                            <button class="btn btn-sm btn-outline" onclick="showQAPanel(${m.id})">问答</button>
                            <button class="btn btn-sm btn-outline" style="color:var(--danger)" onclick="app.deleteMeeting(${m.id})">删除</button>
                        </td>
                    </tr>`;
                } else {
                    return `<tr>
                        <td><strong>${this._esc(m.title)}</strong></td>
                        <td>${m.meeting_date ? new Date(m.meeting_date).toLocaleDateString('zh-CN') : '-'}</td>
                        <td>${m.participants || '-'}</td>
                        <td>
                            <button class="btn btn-sm btn-outline" onclick="app.viewPublicDoc(${m.id})">查看</button>
                        </td>
                    </tr>`;
                }
            }).join('');

            const total = data.data.total || 0;
            const totalPages = Math.ceil(total / 10) || 1;
            const colCount = this.currentUser ? 6 : 4;
            const paginationHtml = totalPages > 1 ? `
                <div class="pagination" style="margin-top:12px;text-align:center">
                    <button class="btn btn-sm btn-outline" ${page <= 1 ? 'disabled' : ''} onclick="app.loadHistory(${page - 1})">上一页</button>
                    <span style="margin:0 12px;color:#666">第 ${page} / ${totalPages} 页 (共 ${total} 条)</span>
                    <button class="btn btn-sm btn-outline" ${page >= totalPages ? 'disabled' : ''} onclick="app.loadHistory(${page + 1})">下一页</button>
                </div>
            ` : '';
            tbody.innerHTML += `<tr><td colspan="${colCount}">${paginationHtml}</td></tr>`;
        } catch (err) {
            console.error('Load history failed:', err);
        }
    }

    async loadMeeting(id) {
        this.showLoading('正在加载会议记录…');
        try {
            const resp = await fetch(API_BASE + '/api/meetings/' + id);
            const data = await resp.json();
            if (!data.success) throw new Error(data.message);

            const m = data.data.meeting;
            this.currentMeetingId = m.id;
            document.getElementById('meetingTitle').value = m.title;
            document.getElementById('participants').value = m.participants || '';
            document.getElementById('meetingDate').value = m.meeting_date ? m.meeting_date.split('T')[0] : '';
            document.getElementById('textInput').value = m.raw_text || '';
            const isPublicEl = document.getElementById('isPublic');
            if (isPublicEl) isPublicEl.checked = !!m.is_public;
            this.switchTab('text');
            document.getElementById('generateSection').style.display = 'block';
            document.getElementById('resultSection').style.display = 'none';

            try {
                const resp2 = await fetch(API_BASE + '/api/minutes/' + id);
                const data2 = await resp2.json();
                if (data2.success) {
                    this.currentMinutes = data2.data;
                    document.getElementById('minutesContent').innerHTML = DOMPurify.sanitize(data2.data.html || data2.data.markdown);
                    this.actionItems = data2.data.action_items || [];
                    this.renderActionItems();
                    document.getElementById('resultSection').style.display = 'block';
                }
            } catch (e) { /* minutes may not exist yet */ }
            this._updateGridLayout();

            this.showToast('会议记录加载成功', 'success');
        } catch (err) {
            this.showToast('加载失败：' + err.message, 'error');
        }
        this.hideLoading();
    }

    async deleteMeeting(id) {
        if (!confirm('确定要删除这条会议记录吗？')) return;
        try {
            const resp = await fetch(API_BASE + '/api/meetings/' + id, { method: 'DELETE' });
            const data = await resp.json();
            if (!data.success) throw new Error(data.message);
            this.showToast('已删除', 'success');
            await this.loadHistory();
        } catch (err) {
            this.showToast('删除失败：' + err.message, 'error');
        }
    }

    // ── Public Documents ────────────────────────────────
    async loadPublicDocs() {
        try {
            const resp = await fetch(API_BASE + '/api/public/meetings');
            const data = await resp.json();
            if (!data.success) throw new Error(data.message);

            const tbody = document.getElementById('publicDocsTableBody');
            if (!tbody) return;
            if (!data.data.items.length) {
                tbody.innerHTML = '<tr><td colspan="4" class="empty-state">暂无公开文档</td></tr>';
                return;
            }

            tbody.innerHTML = data.data.items.map(m => `
                <tr>
                    <td>${this._esc(m.title)}</td>
                    <td>${m.meeting_date ? new Date(m.meeting_date).toLocaleDateString() : '-'}</td>
                    <td>${this._esc(m.participants || '-')}</td>
                    <td><button class="btn btn-sm btn-outline" onclick="app.viewPublicDoc(${m.id})">查看</button></td>
                </tr>
            `).join('');
        } catch (err) {
            this.showToast('加载公开文档失败: ' + err.message, 'error');
        }
    }

    async viewPublicDoc(meetingId) {
        try {
            const resp = await fetch(API_BASE + `/api/public/meetings/${meetingId}`);
            const data = await resp.json();
            if (!data.success) throw new Error(data.message);

            const isOwner = this.currentUser && data.data.meeting.created_by === this.currentUser.id;

            let rawText = null;
            if (isOwner) {
                try {
                    const detailResp = await fetch(API_BASE + `/api/meetings/${meetingId}`);
                    const detailData = await detailResp.json();
                    if (detailData.success) {
                        rawText = detailData.data.meeting.raw_text;
                    }
                } catch (e) { /* ignore */ }
            }

            this._showPublicDocModal(data.data, rawText);
        } catch (err) {
            this.showToast('加载文档失败: ' + err.message, 'error');
        }
    }

    _showPublicDocModal(data, rawText) {
        const existing = document.getElementById('publicDocModal');
        if (existing) existing.remove();

        const meeting = data.meeting;

        let html = '';
        if (data.html || data.markdown) {
            html = DOMPurify.sanitize(data.html || data.markdown);
        } else {
            html = '<div class="empty-state"><p>暂无纪要内容</p></div>';
        }

        const rawTextSection = rawText ? `
            <div style="margin-top:16px">
                <h4>原文内容</h4>
                <div style="background:#f5f5f5;padding:12px;border-radius:6px;white-space:pre-wrap;max-height:300px;overflow-y:auto">${this._esc(rawText)}</div>
            </div>
        ` : '';

        const modal = document.createElement('div');
        modal.id = 'publicDocModal';
        modal.className = 'modal';
        modal.style.display = 'flex';
        modal.innerHTML = `
            <div class="modal-content modal-lg">
                <div class="modal-header">
                    <h3>${this._esc(meeting.title)}</h3>
                    <button class="modal-close" onclick="document.getElementById('publicDocModal').remove()">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="meeting-meta" style="margin-bottom:12px;color:#666;font-size:0.9em">
                        <span>日期: ${meeting.meeting_date ? new Date(meeting.meeting_date).toLocaleDateString() : '-'}</span>
                        <span style="margin-left:12px">参会人员: ${this._esc(meeting.participants || '-')}</span>
                    </div>
                    <div class="minutes-preview">${html}</div>
                    ${rawTextSection}
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    }

    async togglePublic(meetingId) {
        try {
            const resp = await fetch(API_BASE + `/api/meetings/${meetingId}/toggle-public`, {
                method: 'PATCH'
            });
            const data = await resp.json();
            if (!data.success) throw new Error(data.message);
            this.showToast(data.message, 'success');
            await this.loadHistory();
        } catch (err) {
            this.showToast('切换公开状态失败: ' + err.message, 'error');
        }
    }

    // ── Authentication ─────────────────────────────────
    async _checkLoginStatus() {
        try {
            const resp = await fetch(API_BASE + '/api/auth/check', {
                credentials: 'same-origin'
            });
            const data = await resp.json();
            if (data.success && data.data.logged_in) {
                this.currentUser = data.data.user;
                this.sessionToken = data.data.token;
            }
        } catch (err) {
            console.error('Check login status failed:', err);
        }
        this._updateUserUI();
    }

    _getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
        return null;
    }

    _updateUserUI() {
        const userSection = document.getElementById('userSection');
        const publicDocsSection = document.getElementById('publicDocsSection');
        const meetingInfoCard = document.getElementById('meetingInfoCard');
        const contentInputCard = document.getElementById('contentInputCard');
        const welcomeBanner = document.getElementById('welcomeBanner');
        if (this.currentUser) {
            userSection.innerHTML = `
                <span class="user-info">欢迎, ${this._esc(this.currentUser.display_name)}</span>
                <button class="btn btn-outline btn-sm" onclick="app.logout()">登出</button>
            `;
            if (meetingInfoCard) meetingInfoCard.style.display = '';
            if (contentInputCard) contentInputCard.style.display = '';
            if (welcomeBanner) welcomeBanner.style.display = 'none';
            document.getElementById('historyTableHead').innerHTML = `<tr>
                <th>标题</th><th>日期</th><th>参会人员</th><th>状态</th><th>公开</th><th>操作</th>
            </tr>`;
        } else {
            userSection.innerHTML = `
                <button class="btn btn-outline btn-sm" onclick="app.showLoginModal()">登录</button>
            `;
            if (meetingInfoCard) meetingInfoCard.style.display = 'none';
            if (contentInputCard) contentInputCard.style.display = 'none';
            if (welcomeBanner) welcomeBanner.style.display = 'block';
            document.getElementById('historyTableHead').innerHTML = `<tr>
                <th>标题</th><th>日期</th><th>参会人员</th><th>操作</th>
            </tr>`;
        }
        if (publicDocsSection) publicDocsSection.style.display = 'none';
    }

    showLoginModal() {
        document.getElementById('authModal').style.display = 'flex';
        document.getElementById('loginForm').style.display = 'block';
        document.getElementById('registerForm').style.display = 'none';
        document.getElementById('authModalTitle').textContent = '登录';
    }

    showRegister() {
        document.getElementById('loginForm').style.display = 'none';
        document.getElementById('registerForm').style.display = 'block';
        document.getElementById('authModalTitle').textContent = '注册';
    }

    showLogin() {
        document.getElementById('loginForm').style.display = 'block';
        document.getElementById('registerForm').style.display = 'none';
        document.getElementById('authModalTitle').textContent = '登录';
    }

    closeAuthModal() {
        document.getElementById('authModal').style.display = 'none';
    }

    async login() {
        const username = document.getElementById('loginUsername').value.trim();
        const password = document.getElementById('loginPassword').value;
        if (!username || !password) {
            this.showToast('请输入用户名和密码', 'warning');
            return;
        }

        try {
            const resp = await fetch(API_BASE + '/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
                credentials: 'same-origin'
            });
            const data = await resp.json();
            if (!data.success) throw new Error(data.message);

            this.sessionToken = data.data.token;
            this.currentUser = data.data.user;
            this._updateUserUI();
            this._clearDraft();
            this._clearForm();
            this.closeAuthModal();
            this.showToast('登录成功', 'success');
            await this.loadHistory();
        } catch (err) {
            this.closeAuthModal();
            this.showToast('登录失败: ' + err.message, 'error');
        }
    }

    async register() {
        const username = document.getElementById('regUsername').value.trim();
        const displayName = document.getElementById('regDisplayName').value.trim();
        const password = document.getElementById('regPassword').value;
        const passwordConfirm = document.getElementById('regPasswordConfirm').value;

        if (!username || !password) {
            this.showToast('请输入用户名和密码', 'warning');
            return;
        }
        if (password !== passwordConfirm) {
            this.showToast('两次输入的密码不一致', 'warning');
            return;
        }

        try {
            const resp = await fetch(API_BASE + '/api/auth/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password, display_name: displayName || username })
            });
            const data = await resp.json();
            if (!data.success) throw new Error(data.message);

            this.showToast('注册成功，请登录', 'success');
            this.showLogin();
        } catch (err) {
            this.closeAuthModal();
            this.showToast('注册失败: ' + err.message, 'error');
        }
    }

    async logout() {
        try {
            await fetch(API_BASE + '/api/auth/logout', { method: 'POST', credentials: 'same-origin' });
            this.sessionToken = null;
            this.currentUser = null;
            this._updateUserUI();
            this.showToast('已登出', 'success');
            await this.loadHistory();
        } catch (err) {
            console.error('Logout failed:', err);
        }
    }

    // ── Meeting Templates ──────────────────────────────
    async showTemplateModal() {
        document.getElementById('templateModal').style.display = 'flex';
        await this._loadTemplates();
    }

    closeTemplateModal() {
        document.getElementById('templateModal').style.display = 'none';
    }

    async _loadTemplates() {
        const typeFilter = document.getElementById('templateTypeFilter').value;
        const search = document.getElementById('templateSearch').value;

        try {
            let url = API_BASE + '/api/templates?';
            if (typeFilter) url += 'template_type=' + typeFilter + '&';
            if (search) url += 'search=' + encodeURIComponent(search);

            const resp = await fetch(url);
            const data = await resp.json();
            if (data.success) {
                this.templates = data.data.items;
                this._renderTemplates();
            }
        } catch (err) {
            this.showToast('加载模板失败', 'error');
        }
    }

    filterTemplates() {
        this._loadTemplates();
    }

    _renderTemplates() {
        const list = document.getElementById('templateList');
        if (!this.templates.length) {
            list.innerHTML = '<div class="empty-state">暂无模板</div>';
            return;
        }

        list.innerHTML = this.templates.map(t => `
            <div class="template-item" onclick="app.selectTemplate(${t.id})">
                <div class="template-name">${this._esc(t.name)}</div>
                <div class="template-desc">${this._esc(t.description || '')}</div>
                <div class="template-type">${this._esc(t.template_type || '')}</div>
            </div>
        `).join('');
    }

    async selectTemplate(templateId) {
        const template = this.templates.find(t => t.id === templateId);
        if (!template) return;

        this.currentTemplate = template;
        document.getElementById('selectedTemplate').style.display = 'flex';
        document.getElementById('selectedTemplateName').textContent = template.name;

        if (template.content_structure) {
            const textInput = document.getElementById('textInput');
            if (!textInput.value.trim()) {
                textInput.value = template.content_structure;
            }
        }

        this.closeTemplateModal();
        this.showToast('已选择模板: ' + template.name, 'success');
    }

    clearTemplate() {
        this.currentTemplate = null;
        document.getElementById('selectedTemplate').style.display = 'none';
    }

    async createTemplate() {
        document.getElementById('templateName').value = '';
        document.getElementById('templateDescription').value = '';
        document.getElementById('templateContent').value = '';
        document.getElementById('templateType').value = 'weekly';
        document.getElementById('createTemplateModal').style.display = 'flex';
    }

    closeCreateTemplateModal() {
        document.getElementById('createTemplateModal').style.display = 'none';
    }

    async submitCreateTemplate() {
        const name = document.getElementById('templateName').value.trim();
        if (!name) {
            this.showToast('请输入模板名称', 'warning');
            return;
        }
        const description = document.getElementById('templateDescription').value.trim();
        const content = document.getElementById('templateContent').value.trim();
        const templateType = document.getElementById('templateType').value;

        try {
            const resp = await fetch(API_BASE + '/api/templates', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name,
                    description,
                    content_structure: content,
                    template_type: templateType,
                    is_public: true
                })
            });
            const data = await resp.json();
            if (!data.success) throw new Error(data.message);

            this.closeCreateTemplateModal();
            this.showToast('模板创建成功', 'success');
            await this._loadTemplates();
        } catch (err) {
            this.showToast('创建失败: ' + err.message, 'error');
        }
    }

    // ── WebSocket Real-time Transcription ──────────────
    _connectWebSocket() {
        if (this._ws && this._ws.readyState === WebSocket.OPEN) return;

        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        let wsUrl = `${protocol}//${location.host}/ws/transcribe`;
        if (this.sessionToken) {
            wsUrl += '?token=' + encodeURIComponent(this.sessionToken);
        }

        this._ws = new WebSocket(wsUrl);
        
        this._ws.onopen = () => {
            console.log('WebSocket connected');
            this._ws.send(JSON.stringify({
                type: 'start',
                mode: 'record',
                sample_rate: 16000
            }));
        };
        
        this._ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            this._handleWsMessage(msg);
        };
        
        this._ws.onclose = () => {
            console.log('WebSocket disconnected');
        };
        
        this._ws.onerror = (err) => {
            console.error('WebSocket error:', err);
        };
    }

    _disconnectWebSocket() {
        if (this._ws) {
            this._ws.send(JSON.stringify({ type: 'stop' }));
            this._ws.close();
            this._ws = null;
        }
    }

    _sendAudioChunk(chunk) {
        if (this._ws && this._ws.readyState === WebSocket.OPEN) {
            this._ws.send(chunk);
        }
    }

    _handleWsMessage(msg) {
        if (msg.type === 'transcript' && msg.text) {
            this._appendSubtitleText(msg.text);
        } else if (msg.type === 'newline') {
            this._subtitleNeedNewLine = true;
        } else if (msg.type === 'error') {
            this.showToast('转写出错: ' + msg.message, 'error');
        }
    }

    _appendSubtitleText(text) {
        const container = document.getElementById('subtitleContent');
        if (!container) return;

        const placeholder = container.querySelector('.subtitle-placeholder');
        if (placeholder) placeholder.remove();

        if (this._subtitleNeedNewLine || !this._currentSubtitleEl) {
            const line = document.createElement('div');
            line.className = 'subtitle-line confirmed';
            // 添加逐字显示动画效果
            line.style.opacity = '0';
            line.style.transform = 'translateY(8px)';
            container.appendChild(line);
            this._currentSubtitleEl = line;
            this._subtitleLines.push('');
            this._subtitleNeedNewLine = false;

            // 触发动画
            requestAnimationFrame(() => {
                line.style.transition = 'opacity 0.2s ease, transform 0.2s ease';
                line.style.opacity = '1';
                line.style.transform = 'translateY(0)';
            });
        }

        this._currentSubtitleEl.textContent += text;
        this._subtitleLines[this._subtitleLines.length - 1] = this._currentSubtitleEl.textContent;

        container.scrollTop = container.scrollHeight;
    }

    _addSubtitleLine(text, isFinal = true) {
        const container = document.getElementById('subtitleContent');
        if (!container) return;

        const line = document.createElement('div');
        line.className = `subtitle-line ${isFinal ? 'confirmed' : 'pending'}`;
        line.textContent = text;
        container.appendChild(line);

        this._subtitleLines.push(text);
        this._currentSubtitleEl = null;
        this._subtitleNeedNewLine = true;

        container.scrollTop = container.scrollHeight;
    }

    _clearSubtitles() {
        const container = document.getElementById('subtitleContent');
        if (container) {
            container.innerHTML = '<div class="subtitle-placeholder">等待语音输入...</div>';
        }
        this._subtitleLines = [];
        this._currentSubtitleEl = null;
        this._subtitleNeedNewLine = true;
        const overlay = document.getElementById('subtitleFinishOverlay');
        if (overlay) overlay.style.display = 'none';
        // 重置连接状态
        this._updateConnectionStatus('disconnected');
    }

    _getSubtitleText() {
        return this._subtitleLines.join('');
    }

    _startRealtimeCapture(source) {
        const bufferSize = 4096;
        const processor = this._audioContext.createScriptProcessor(bufferSize, 1, 1);

        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        let wsUrl = `${protocol}//${location.host}/ws/transcribe`;
        if (this.sessionToken) {
            wsUrl += '?token=' + encodeURIComponent(this.sessionToken);
        }

        // 连接状态管理
        this._wsReconnectAttempts = 0;
        this._wsMaxReconnectAttempts = 3;
        this._wsReconnectDelay = 1000;

        const connectWs = () => {
            this._ws = new WebSocket(wsUrl);

            this._ws.onopen = () => {
                console.log('[Realtime] WebSocket connected');
                this._wsReconnectAttempts = 0;
                const sampleRate = this._audioContext.sampleRate;
                this._ws.send(JSON.stringify({ type: 'start', mode: 'record', sample_rate: sampleRate }));
                // Buffer 4 seconds of audio before sending for better accuracy
                this._recordBuffer = new Float32Array(0);
                this._recordBufferTarget = sampleRate * 4; // 4 seconds in samples
                this._updateConnectionStatus('connected');
                document.getElementById('subtitleBar').style.display = 'block';
            };

            this._ws.onmessage = (event) => {
                const msg = JSON.parse(event.data);
                if (msg.type === 'transcript' && msg.text) {
                    this._appendSubtitleText(msg.text);
                    this._updateConnectionStatus('connected');
                    const statusEl = document.getElementById('subtitleStatus');
                    if (statusEl) {
                        statusEl.innerHTML = `<span class="connection-dot" style="background:#10b981"></span>已识别 ${msg.audio_duration || 0}秒`;
                    }
                } else if (msg.type === 'newline') {
                    this._subtitleNeedNewLine = true;
                } else if (msg.type === 'progress') {
                    this._updateConnectionStatus('transcribing');
                    const statusEl = document.getElementById('subtitleStatus');
                    if (statusEl) {
                        const duration = msg.audio_duration || 0;
                        statusEl.innerHTML = `<span class="connection-dot" style="background:#3b82f6;animation:pulse 1s infinite"></span>识别中... (${duration}秒)`;
                    }
                } else if (msg.type === 'status' && msg.message === '实时转写已停止') {
                    if (this._isWaitingForStop) {
                        this._isWaitingForStop = false;
                        this._closeRealtimeWs();
                        this._onRealtimeStopComplete();
                    }
                } else if (msg.type === 'error') {
                    this.showToast('转写出错: ' + msg.message, 'error');
                    if (this._isWaitingForStop) {
                        this._isWaitingForStop = false;
                        this._closeRealtimeWs();
                        this._onRealtimeStopComplete();
                    }
                }
            };

            this._ws.onclose = (event) => {
                console.log('[Realtime] WebSocket closed', event.code, event.reason);
                this._updateConnectionStatus('disconnected');

                // 非正常关闭且未在等待停止时尝试重连
                if (!this._isWaitingForStop && this.isRecording &&
                    event.code !== 1000 && this._wsReconnectAttempts < this._wsMaxReconnectAttempts) {
                    this._wsReconnectAttempts++;
                    const delay = this._wsReconnectDelay * Math.pow(2, this._wsReconnectAttempts - 1);
                    console.log(`[Realtime] Reconnecting in ${delay}ms (attempt ${this._wsReconnectAttempts})`);
                    this._updateConnectionStatus('reconnecting');
                    setTimeout(connectWs, delay);
                } else if (this._isWaitingForStop) {
                    this._isWaitingForStop = false;
                    this._onRealtimeStopComplete();
                }
            };

            this._ws.onerror = (err) => {
                console.error('[Realtime] WebSocket error:', err);
                this._updateConnectionStatus('error');
            };
        };

        // 建立WebSocket连接
        connectWs();

        // 音频处理 - 缓冲后发送，带高通滤波和归一化
        processor.onaudioprocess = (e) => {
            if (!this.isRecording || !this._ws || this._ws.readyState !== WebSocket.OPEN) return;

            const inputData = e.inputBuffer.getChannelData(0);

            // Append to buffer
            const prev = this._recordBuffer || new Float32Array(0);
            const merged = new Float32Array(prev.length + inputData.length);
            merged.set(prev);
            merged.set(inputData, prev.length);
            this._recordBuffer = merged;

            // Send when buffer reaches target length
            if (this._recordBuffer.length >= (this._recordBufferTarget || 64000)) {
                const buf = this._recordBuffer;
                this._recordBuffer = new Float32Array(0);

                // Step 1: High-pass filter (remove DC offset and low-freq noise below 80Hz)
                // Simple 1st-order IIR: y[n] = x[n] - x[n-1] + 0.995 * y[n-1]
                const filtered = new Float32Array(buf.length);
                const hpCoeff = 0.97; // ~80Hz cutoff at 48kHz
                filtered[0] = buf[0];
                for (let i = 1; i < buf.length; i++) {
                    filtered[i] = buf[i] - buf[i-1] + hpCoeff * filtered[i-1];
                }

                // Step 2: RMS-based gain normalization (more stable than peak)
                let sumSq = 0;
                for (let i = 0; i < filtered.length; i++) {
                    sumSq += filtered[i] * filtered[i];
                }
                const rms = Math.sqrt(sumSq / filtered.length);
                const targetRms = 0.15; // target RMS level
                const gain = rms > 0.001 ? Math.min(targetRms / rms, 5.0) : 1.0;

                // Step 3: Soft clip (tanh) to prevent hard clipping
                const int16 = new Int16Array(filtered.length);
                for (let i = 0; i < filtered.length; i++) {
                    const s = Math.tanh(filtered[i] * gain); // soft clip [-1, 1]
                    int16[i] = Math.round(s * 32767);
                }
                this._ws.send(int16.buffer);
            }
        };

        source.connect(processor);
        processor.connect(this._audioContext.destination);
        this._realtimeProcessor = processor;
    }

    _updateConnectionStatus(status) {
        const statusEl = document.getElementById('recordStatus');
        if (!statusEl) return;

        const statusMap = {
            'connected': { text: '已连接 - 等待语音...', color: '#10b981' },
            'transcribing': { text: '转写中...', color: '#3b82f6' },
            'disconnected': { text: '连接断开', color: '#ef4444' },
            'reconnecting': { text: '重新连接中...', color: '#f59e0b' },
            'error': { text: '连接错误', color: '#ef4444' },
        };

        const info = statusMap[status] || statusMap['connected'];
        statusEl.innerHTML = `
            <span class="connection-dot" style="background:${info.color};animation:pulse 1.5s infinite"></span>
            ${info.text}
        `;

        // 移除脉冲动画当停止转写时
        if (status === 'disconnected' || status === 'error') {
            statusEl.querySelector('.connection-dot')?.style.setProperty('animation', 'none');
        }
    }

    _stopRealtimeCapture() {
        if (this._realtimeProcessor) {
            this._realtimeProcessor.disconnect();
            this._realtimeProcessor = null;
        }
        if (this._ws && this._ws.readyState === WebSocket.OPEN) {
            this._isWaitingForStop = true;
            this._ws.send(JSON.stringify({ type: 'stop' }));
            const overlay = document.getElementById('subtitleFinishOverlay');
            if (overlay) overlay.style.display = 'flex';
            this._stopConfirmTimer = setTimeout(() => {
                if (this._isWaitingForStop) {
                    this._isWaitingForStop = false;
                    this._closeRealtimeWs();
                    this._onRealtimeStopComplete();
                }
            }, 15000);
        } else {
            this._isWaitingForStop = false;
        }
    }

    _closeRealtimeWs() {
        if (this._stopConfirmTimer) {
            clearTimeout(this._stopConfirmTimer);
            this._stopConfirmTimer = null;
        }
        if (this._ws) {
            const wsRef = this._ws;
            this._ws = null;
            setTimeout(() => { try { wsRef.close(); } catch(e) {} }, 100);
        }
    }

    async _uploadRecordingStreaming(blob, duration) {
        console.log('[Realtime] _uploadRecordingStreaming called, duration:', duration);
        const statusEl = document.getElementById('recordStatus');
        statusEl.textContent = '录音完成, 上传中...';

        const progressSection = document.getElementById('recordProgressSection');
        progressSection.style.display = 'block';
        document.getElementById('recordProgressLabel').textContent = '上传中...';
        document.getElementById('recordProgressPct').textContent = '0%';
        document.getElementById('recordProgressBar').style.width = '0%';

        this._clearSubtitles();
        this._addSubtitleLine('正在上传音频...', false);

        try {
            const formData = new FormData();
            const ext = this._mediaRecorder.mimeType.includes('webm') ? 'webm' : 'wav';
            formData.append('file', blob, 'recording_' + Date.now() + '.' + ext);

            console.log('[Realtime] Uploading file...');
            const data = await new Promise((resolve, reject) => {
                const xhr = new XMLHttpRequest();
                xhr.upload.addEventListener('progress', (e) => {
                    if (e.lengthComputable) {
                        const pct = Math.round((e.loaded / e.total) * 50);
                        document.getElementById('recordProgressPct').textContent = pct + '%';
                        document.getElementById('recordProgressBar').style.width = pct + '%';
                    }
                });
                xhr.addEventListener('load', () => {
                    try { resolve(JSON.parse(xhr.responseText)); }
                    catch (e) { reject(new Error('无效的服务器响应')); }
                });
                xhr.addEventListener('error', () => reject(new Error('网络错误')));
                xhr.open('POST', API_BASE + '/api/meetings/upload-audio');
                xhr.send(formData);
            });

            console.log('[Realtime] Upload result:', data);
            if (!data.success) throw new Error(data.message);

            this._clearSubtitles();
            this._addSubtitleLine('音频上传完成，正在识别...', false);
            document.getElementById('recordProgressLabel').textContent = '语音识别中...';
            document.getElementById('recordProgressPct').textContent = '50%';
            document.getElementById('recordProgressBar').style.width = '50%';
            document.getElementById('recordProgressDetail').textContent = '正在使用语音识别引擎处理...';

            const asrEngine = document.getElementById('asrSelectRecord').value;
            console.log('[Realtime] Calling recognize API, engine:', asrEngine);
            const resp2 = await fetch(API_BASE + '/api/meetings/recognize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: 'filepath=' + encodeURIComponent(data.data.filename) + '&asr_engine=' + encodeURIComponent(asrEngine),
            });
            const data2 = await resp2.json();
            console.log('[Realtime] Recognize result:', data2);

            if (!data2.success) throw new Error(data2.message);

            this._clearSubtitles();
            this._addSubtitleLine(data2.data.text, true);

            document.getElementById('recordProgressLabel').textContent = '识别完成';
            document.getElementById('recordProgressPct').textContent = '100%';
            document.getElementById('recordProgressBar').style.width = '100%';
            document.getElementById('recordProgressDetail').textContent = '语音识别完成';

            const subtitleText = this._getSubtitleText();
            document.getElementById('textInput').value = subtitleText;

            statusEl.textContent = '识别完成, 已切换到录音结果';
            this.showToast('语音识别完成', 'success');
            setTimeout(() => { progressSection.style.display = 'none'; }, 1500);
        } catch (err) {
            console.error('[Realtime] Error:', err);
            this._clearSubtitles();
            this._addSubtitleLine('识别失败: ' + err.message, true);
            this.showToast('上传或识别失败: ' + err.message, 'error');
            progressSection.style.display = 'none';
        }
    }

    _useStreamingForFile(filename) {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        let wsUrl = `${protocol}//${location.host}/ws/transcribe`;
        if (this.sessionToken) {
            wsUrl += '?token=' + encodeURIComponent(this.sessionToken);
        }

        const ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            ws.send(JSON.stringify({
                type: 'start',
                mode: 'file',
                file_path: filename
            }));
        };

        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            if (msg.type === 'transcript' && msg.text) {
                const resultEl = document.getElementById('recordResultText');
                if (resultEl) {
                    resultEl.textContent += msg.text;
                }
            } else if (msg.type === 'status' && msg.progress !== undefined) {
                const pct = Math.round(msg.progress * 100);
                document.getElementById('recordProgressPct').textContent = pct + '%';
                document.getElementById('recordProgressBar').style.width = pct + '%';
            } else if (msg.type === 'error') {
                this.showToast('转写出错: ' + msg.message, 'error');
            }
        };

        ws.onclose = () => {
            document.getElementById('tabBtnResult').style.display = '';
            this.switchTab('result');
        };
    }

    // ── Recording ──────────────────────────────────────
    async toggleRecord() {
        if (this.isRecording) {
            this.stopRecord();
        } else {
            await this.startRecord();
        }
    }

    async startRecord() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            this._recordStream = stream;
            this._analyserStream = stream;
            this._audioChunks = [];

            this._audioContext = new (window.AudioContext || window.webkitAudioContext)();
            await this._audioContext.resume();

            this._analyser = this._audioContext.createAnalyser();
            this._analyser.fftSize = 2048;
            this._analyser.smoothingTimeConstant = 0.85;

            const source = this._audioContext.createMediaStreamSource(stream);
            source.connect(this._analyser);

            const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
                ? 'audio/webm;codecs=opus'
                : MediaRecorder.isTypeSupported('audio/webm')
                    ? 'audio/webm'
                    : 'audio/wav';

            this._mediaRecorder = new MediaRecorder(stream, { mimeType });
            this._mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) this._audioChunks.push(e.data);
            };
            this._mediaRecorder.onstop = () => this._onRecordStop();
            this._mediaRecorder.start(1000);

            const realtimeEnabled = document.getElementById('enableRealtime').checked;
            if (realtimeEnabled) {
                this._clearSubtitles();
                document.getElementById('subtitleBar').style.display = 'block';
                this._startRealtimeCapture(source);
            }

            this.isRecording = true;
            this._recordStartTime = Date.now();
            this._lastRecordingBlob = null;
            this._lastRecordingName = null;
            document.getElementById('btnDownloadRecording').style.display = 'none';
            this._updateRecordUI(true);
            this._startRecordTimer();
            requestAnimationFrame(() => this._drawWaveform());
        } catch (err) {
            this.showToast('无法访问麦克风: ' + err.message, 'error');
        }
    }

    stopRecord() {
        this._stopRealtimeCapture();
        this.isRecording = false;
        if (this._mediaRecorder && this._mediaRecorder.state !== 'inactive') {
            this._mediaRecorder.stop();
        }
        this._updateRecordUI(false);
        this._stopRecordTimer();
        if (this._waveformAnimId) {
            cancelAnimationFrame(this._waveformAnimId);
            this._waveformAnimId = null;
        }
        this._drawIdleWaveform();
    }

    _onRecordStop() {
        console.log('[Realtime] _onRecordStop called');
        const duration = Math.round((Date.now() - this._recordStartTime) / 1000);
        if (duration < 2) {
            this._cleanupRecording();
            this.showToast('录音时间太短', 'warning');
            return;
        }

        const blob = new Blob(this._audioChunks, { type: this._mediaRecorder.mimeType });
        const ext = this._mediaRecorder.mimeType.includes('webm') ? 'webm' : 'wav';
        const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        this._lastRecordingBlob = blob;
        this._lastRecordingName = 'recording_' + ts + '.' + ext;

        this._cleanupRecording();
        document.getElementById('btnDownloadRecording').style.display = 'inline-flex';

        const realtimeEnabled = document.getElementById('enableRealtime').checked;

        if (realtimeEnabled) {
            if (this._isWaitingForStop) {
                console.log('[Realtime] Waiting for backend to finish transcription...');
                return;
            }
            this._onRealtimeStopComplete();
        } else {
            this._uploadRecording(blob, duration);
        }
    }

    _onRealtimeStopComplete() {
        if (this._stopConfirmTimer) {
            clearTimeout(this._stopConfirmTimer);
            this._stopConfirmTimer = null;
        }

        const overlay = document.getElementById('subtitleFinishOverlay');
        if (overlay) overlay.style.display = 'none';

        const subtitleText = this._getSubtitleText();
        if (subtitleText) {
            document.getElementById('recordResultText').textContent = subtitleText;
            document.getElementById('tabBtnResult').style.display = '';
            document.getElementById('subtitleBar').style.display = 'none';
            this.switchTab('result');
            this.showToast('实时转写完成', 'success');
        } else if (this._lastRecordingBlob) {
            const duration = Math.round((Date.now() - this._recordStartTime) / 1000);
            this._uploadRecordingStreaming(this._lastRecordingBlob, duration);
        }
    }

    _cleanupRecording() {
        if (this._recordStream) {
            this._recordStream.getTracks().forEach(t => t.stop());
            this._recordStream = null;
        }
        this._analyserStream = null;
        this._analyser = null;
        if (this._audioContext && this._audioContext.state !== 'closed') {
            try { this._audioContext.close(); } catch(e) {}
            this._audioContext = null;
        }
    }

    downloadRecording() {
        if (!this._lastRecordingBlob) {
            this.showToast('没有可下载的录音', 'warning');
            return;
        }
        const url = URL.createObjectURL(this._lastRecordingBlob);
        const a = document.createElement('a');
        a.href = url;
        a.download = this._lastRecordingName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        this.showToast('录音已下载', 'success');
    }

    async _uploadRecording(blob, duration) {
        const mins = Math.floor(duration / 60);
        const secs = duration % 60;
        const timeStr = String(mins).padStart(2, '0') + ':' + String(secs).padStart(2, '0');

        const statusEl = document.getElementById('recordStatus');
        statusEl.textContent = '录音 ' + timeStr + ', 上传中...';

        const progressSection = document.getElementById('recordProgressSection');
        progressSection.style.display = 'block';
        document.getElementById('recordProgressLabel').textContent = '上传中...';
        document.getElementById('recordProgressPct').textContent = '0%';
        document.getElementById('recordProgressBar').style.width = '0%';
        document.getElementById('recordProgressDetail').textContent = '正在上传录音文件...';

        try {
            const formData = new FormData();
            const ext = this._mediaRecorder.mimeType.includes('webm') ? 'webm' : 'wav';
            formData.append('file', blob, 'recording_' + Date.now() + '.' + ext);

            const data = await new Promise((resolve, reject) => {
                const xhr = new XMLHttpRequest();
                xhr.upload.addEventListener('progress', (e) => {
                    if (e.lengthComputable) {
                        const pct = Math.round((e.loaded / e.total) * 50);
                        document.getElementById('recordProgressPct').textContent = pct + '%';
                        document.getElementById('recordProgressBar').style.width = pct + '%';
                    }
                });
                xhr.addEventListener('load', () => {
                    try { resolve(JSON.parse(xhr.responseText)); }
                    catch (e) { reject(new Error('无效的服务器响应')); }
                });
                xhr.addEventListener('error', () => reject(new Error('网络错误')));
                xhr.open('POST', API_BASE + '/api/meetings/upload-audio');
                xhr.send(formData);
            });

            if (!data.success) throw new Error(data.message);
            const filename = data.data.filename;

            document.getElementById('recordProgressLabel').textContent = '语音识别中...';
            document.getElementById('recordProgressPct').textContent = '50%';
            document.getElementById('recordProgressBar').style.width = '50%';
            document.getElementById('recordProgressDetail').textContent = '音频已上传, 正在识别...';

            let pct = 50;
            const animInterval = setInterval(() => {
                if (pct < 90) {
                    pct += 2;
                    document.getElementById('recordProgressPct').textContent = pct + '%';
                    document.getElementById('recordProgressBar').style.width = pct + '%';
                }
            }, 1000);

            const asrEngine = document.getElementById('asrSelectRecord').value;
            const resp2 = await fetch(API_BASE + '/api/meetings/recognize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: 'filepath=' + encodeURIComponent(filename) + '&asr_engine=' + encodeURIComponent(asrEngine),
            });
            const data2 = await resp2.json();
            clearInterval(animInterval);

            if (!data2.success) throw new Error(data2.message);

            document.getElementById('recordProgressLabel').textContent = '识别完成';
            document.getElementById('recordProgressPct').textContent = '100%';
            document.getElementById('recordProgressBar').style.width = '100%';
            document.getElementById('recordProgressDetail').textContent = '语音识别完成';

            document.getElementById('recordResultText').textContent = data2.data.text;
            document.getElementById('tabBtnResult').style.display = '';
            this.switchTab('result');

            if (!document.getElementById('meetingTitle').value) {
                document.getElementById('meetingTitle').value = '录音 ' + new Date().toLocaleDateString('zh-CN');
            }

            statusEl.textContent = '识别完成, 已切换到录音结果';
            this.showToast('语音识别完成', 'success');
            document.getElementById('recordResultText').scrollIntoView({ behavior: 'smooth', block: 'center' });
            setTimeout(() => { progressSection.style.display = 'none'; }, 2000);
        } catch (err) {
            document.getElementById('recordProgressLabel').textContent = '识别失败';
            document.getElementById('recordProgressBar').style.width = '0%';
            document.getElementById('recordProgressDetail').textContent = err.message;
            statusEl.textContent = '识别失败: ' + err.message;
            this.showToast('识别失败: ' + err.message, 'error');
            setTimeout(() => { progressSection.style.display = 'none'; }, 3000);
        }
    }

    _updateRecordUI(recording) {
        const btn = document.getElementById('btnRecord');
        const text = document.getElementById('recordBtnText');
        if (recording) {
            btn.classList.add('recording');
            text.textContent = '停止录音';
            document.getElementById('recordStatus').textContent = '正在录音...';
        } else {
            btn.classList.remove('recording');
            text.textContent = '开始录音';
        }
    }

    _startRecordTimer() {
        const timerEl = document.getElementById('recordTimer');
        this._recordTimerInterval = setInterval(() => {
            const elapsed = Math.floor((Date.now() - this._recordStartTime) / 1000);
            const m = Math.floor(elapsed / 60);
            const s = elapsed % 60;
            timerEl.textContent = String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
        }, 500);
    }

    _stopRecordTimer() {
        clearInterval(this._recordTimerInterval);
        document.getElementById('recordTimer').textContent = '00:00';
    }

    // ── Waveform ───────────────────────────────────────
    _drawWaveform() {
        const canvas = document.getElementById('recordWaveform');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;
        const rect = canvas.getBoundingClientRect();
        const w = rect.width || canvas.parentElement.clientWidth || 300;
        const h = rect.height || 100;
        const newWidth = w * dpr;
        const newHeight = h * dpr;

        if (canvas.width !== newWidth || canvas.height !== newHeight) {
            canvas.width = newWidth;
            canvas.height = newHeight;
        }
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

        const width = w;
        const height = h;
        const centerY = height / 2;

        const bufferLength = this._analyser.frequencyBinCount;
        if (!this._waveformPrevData || this._waveformPrevData.length !== bufferLength) {
            this._waveformPrevData = new Float32Array(bufferLength).fill(centerY);
        }
        if (!this._dataArray) {
            this._dataArray = new Uint8Array(bufferLength);
        }
        const prevData = this._waveformPrevData;
        const dataArray = this._dataArray;

        // 计算音频能量用于颜色变化
        let energy = 0;
        for (let i = 0; i < bufferLength; i++) {
            energy += Math.abs(dataArray[i] - 128);
        }
        energy = energy / bufferLength / 128;

        // 基于能量的颜色渐变
        const getColor = (alpha) => {
            const r = Math.round(26 + energy * 200);
            const g = Math.round(26 + energy * 50);
            const b = Math.round(26 + energy * 100);
            return `rgba(${r}, ${g}, ${b}, ${alpha})`;
        };

        const draw = () => {
            if (!this.isRecording || !this._analyser) {
                this._waveformPrevData = null;
                this._dataArray = null;
                return;
            }
            this._waveformAnimId = requestAnimationFrame(draw);

            this._analyser.getByteTimeDomainData(dataArray);
            ctx.clearRect(0, 0, width, height);

            // 背景线
            ctx.beginPath();
            ctx.moveTo(0, centerY);
            ctx.lineTo(width, centerY);
            ctx.strokeStyle = 'rgba(200, 200, 200, 0.3)';
            ctx.lineWidth = 1;
            ctx.stroke();

            // 主波形 - 带渐变效果
            ctx.beginPath();
            const step = width / bufferLength;
            let x = 0;
            for (let i = 0; i < bufferLength; i++) {
                const v = dataArray[i] / 128.0;
                const y = v * centerY;
                const sy = prevData[i] * 0.3 + y * 0.7;
                prevData[i] = sy;
                if (i === 0) ctx.moveTo(x, sy);
                else ctx.lineTo(x, sy);
                x += step;
            }

            // 创建渐变笔触
            const gradient = ctx.createLinearGradient(0, 0, width, 0);
            gradient.addColorStop(0, getColor(0.6));
            gradient.addColorStop(0.5, getColor(1));
            gradient.addColorStop(1, getColor(0.6));

            ctx.strokeStyle = gradient;
            ctx.lineWidth = 2.5;
            ctx.lineJoin = 'round';
            ctx.lineCap = 'round';
            ctx.stroke();

            // 填充区域
            ctx.lineTo(width, centerY);
            ctx.lineTo(0, centerY);
            ctx.closePath();
            const fillGradient = ctx.createLinearGradient(0, 0, 0, height);
            fillGradient.addColorStop(0, getColor(0.1));
            fillGradient.addColorStop(0.5, getColor(0.05));
            fillGradient.addColorStop(1, getColor(0.1));
            ctx.fillStyle = fillGradient;
            ctx.fill();

            // 镜像波形
            ctx.beginPath();
            x = 0;
            for (let i = 0; i < bufferLength; i++) {
                const mirrorY = centerY * 2 - prevData[i];
                if (i === 0) ctx.moveTo(x, mirrorY);
                else ctx.lineTo(x, mirrorY);
                x += step;
            }
            ctx.strokeStyle = getColor(0.2);
            ctx.lineWidth = 1;
            ctx.stroke();

            // 能量指示点
            if (energy > 0.05) {
                const dotX = width / 2;
                const dotRadius = 4 + energy * 8;
                ctx.beginPath();
                ctx.arc(dotX, centerY, dotRadius, 0, Math.PI * 2);
                ctx.fillStyle = getColor(0.3 + energy * 0.4);
                ctx.fill();
            }
        };
        draw();
    }

    _drawIdleWaveform() {
        const canvas = document.getElementById('recordWaveform');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;
        const rect = canvas.getBoundingClientRect();
        const w = rect.width || canvas.parentElement.clientWidth || 300;
        const h = rect.height || 100;
        const newWidth = w * dpr;
        const newHeight = h * dpr;

        if (canvas.width !== newWidth || canvas.height !== newHeight) {
            canvas.width = newWidth;
            canvas.height = newHeight;
        }
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

        const centerY = h / 2;
        ctx.clearRect(0, 0, w, h);
        ctx.beginPath();
        ctx.moveTo(0, centerY);
        ctx.lineTo(w, centerY);
        ctx.strokeStyle = '#d0d0d0';
        ctx.lineWidth = 1;
        ctx.stroke();
    }

    // ── Utilities ──────────────────────────────────────
    _updateGridLayout() {
        const visible = document.getElementById('resultSection').style.display !== 'none';
        document.querySelector('.content-layout').classList.toggle('has-result', visible);
    }

    showLoading(msg, showProgress = false) {
        document.getElementById('loadingText').textContent = msg || '处理中…';
        const wrap = document.getElementById('progressBarWrap');
        if (showProgress) {
            wrap.style.display = 'flex';
            document.getElementById('progressBarFill').style.width = '0%';
            document.getElementById('progressText').textContent = '0%';
            document.getElementById('tokenPreview').textContent = '';
        } else {
            wrap.style.display = 'none';
        }
        document.getElementById('loadingOverlay').classList.add('active');
    }

    hideLoading() {
        document.getElementById('loadingOverlay').classList.remove('active');
        document.getElementById('progressBarWrap').style.display = 'none';
        document.getElementById('tokenPreview').textContent = '';
    }

    _connectInferenceWS(meetingId) {
        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${proto}//${location.host}/ws/inference/${meetingId}`;
        const ws = new WebSocket(url);
        this._inferenceWs = ws;
        this._inferenceStartTime = Date.now() / 1000;

        ws.onmessage = (e) => {
            try {
                const msg = JSON.parse(e.data);
                if (msg.type === 'progress') {
                    const elapsed = Math.round(Date.now() / 1000 - this._inferenceStartTime);
                    if (msg.progress < 0) {
                        document.getElementById('loadingText').textContent = `处理输入中...（${elapsed}s）`;
                        document.getElementById('progressBarFill').style.width = '5%';
                        document.getElementById('progressText').textContent = '...';
                    } else {
                        const pct = Math.round(msg.progress * 100);
                        document.getElementById('progressBarFill').style.width = pct + '%';
                        document.getElementById('progressText').textContent = pct + '%';
                        document.getElementById('loadingText').textContent =
                            `推理中... ${msg.current_tokens}/${msg.max_tokens} tokens（${elapsed}s）`;
                    }
                    if (msg.text) {
                        const el = document.getElementById('tokenPreview');
                        el.textContent = msg.text;
                        el.scrollTop = el.scrollHeight;
                    }
                } else if (msg.type === 'done') {
                    document.getElementById('progressBarFill').style.width = '100%';
                    document.getElementById('progressText').textContent = '100%';
                    document.getElementById('loadingText').textContent = '生成纪要中...';
                }
            } catch (_) {}
        };
        ws.onerror = () => {};
        return ws;
    }

    _closeInferenceWS() {
        if (this._inferenceWs) {
            try { this._inferenceWs.close(); } catch (_) {}
            this._inferenceWs = null;
        }
    }

    showToast(msg, type) {
        const container = document.getElementById('toastContainer');
        const toast = document.createElement('div');
        toast.className = 'toast ' + (type || 'info');

        const icons = { success: '\u2713', error: '\u2717', warning: '\u26A0', info: '\u2139' };
        const icon = document.createElement('span');
        icon.className = 'toast-icon';
        icon.textContent = icons[type] || icons.info;

        const text = document.createElement('span');
        text.className = 'toast-text';
        text.textContent = msg;

        const closeBtn = document.createElement('button');
        closeBtn.className = 'toast-close';
        closeBtn.innerHTML = '&times;';
        closeBtn.onclick = () => toast.remove();

        toast.appendChild(icon);
        toast.appendChild(text);
        toast.appendChild(closeBtn);
        container.appendChild(toast);
        setTimeout(() => toast.remove(), 4000);
    }

    _esc(str) {
        if (!str) return '';
        if (!this._escDiv) this._escDiv = document.createElement('div');
        this._escDiv.textContent = str;
        return this._escDiv.innerHTML;
    }
}

const app = new MeetingApp();
document.addEventListener('DOMContentLoaded', () => app.init());

// Q&A Panel Functions
let currentMeetingId = null;
let currentQARow = null;

function toggleQAPanel() {
    if (currentQARow) {
        currentQARow.remove();
        currentQARow = null;
        currentMeetingId = null;
    }
}

function showQAPanel(meetingId) {
    // 关闭之前的面板
    if (currentQARow) {
        currentQARow.remove();
        currentQARow = null;
    }

    currentMeetingId = meetingId;

    // 找到点击按钮所在的行，获取会议标题
    const tbody = document.getElementById('historyTableBody');
    const buttons = tbody.querySelectorAll('button');
    let targetRow = null;
    let meetingTitle = '会议';
    for (const btn of buttons) {
        if (btn.onclick && btn.onclick.toString().includes('showQAPanel(' + meetingId + ')')) {
            targetRow = btn.closest('tr');
            if (targetRow) {
                const titleCell = targetRow.querySelector('td:first-child strong');
                if (titleCell) meetingTitle = titleCell.textContent.trim();
            }
            break;
        }
    }

    // 创建问答行
    const qaRow = document.createElement('tr');
    qaRow.id = 'qa-row';
    qaRow.innerHTML = `
        <td colspan="6" style="padding:0; border:none;">
            <div class="qa-panel">
                <div class="qa-header">
                    <h3>智能问答 - ${meetingTitle}</h3>
                    <button onclick="toggleQAPanel()" class="btn-close">&times;</button>
                </div>
                <div id="qa-messages" class="qa-messages">
                    <div class="qa-message system">基于会议内容，您可以提问任何问题</div>
                </div>
                <div class="qa-input-area">
                    <input type="text" id="qa-input" placeholder="输入您的问题..." onkeypress="if(event.key==='Enter')sendQA()">
                    <button onclick="sendQA()" class="btn-send">发送</button>
                </div>
            </div>
        </td>
    `;

    if (targetRow && targetRow.nextSibling) {
        tbody.insertBefore(qaRow, targetRow.nextSibling);
    } else if (targetRow) {
        tbody.appendChild(qaRow);
    }
    currentQARow = qaRow;

    qaRow.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function sendQA() {
    const input = document.getElementById('qa-input');
    const question = input.value.trim();
    if (!question || !currentMeetingId) return;
    addMessage(question, 'user');
    input.value = '';
    const aiMsgId = addMessage('', 'ai');
    const aiMsg = document.getElementById(aiMsgId);

    try {
        const response = await fetch(`/api/meetings/${currentMeetingId}/qa/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        if (data.text) {
                            fullText += data.text;
                            aiMsg.textContent = fullText;
                        }
                        if (data.error) {
                            aiMsg.textContent = '错误: ' + data.error;
                            aiMsg.className = 'qa-message ai error';
                        }
                        if (data.done) {
                            aiMsg.className = 'qa-message ai';
                        }
                    } catch (e) {}
                }
            }
            const messages = document.getElementById('qa-messages');
            if (messages) messages.scrollTop = messages.scrollHeight;
        }

        if (!fullText) {
            aiMsg.textContent = '未收到回答';
        }
    } catch (error) {
        aiMsg.textContent = '网络错误，请稍后重试';
        aiMsg.className = 'qa-message ai error';
    }
}
function addMessage(text, type) {
    const messages = document.getElementById('qa-messages');
    if (!messages) return;
    const id = 'msg-' + Date.now();
    const div = document.createElement('div');
    div.id = id;
    div.className = 'qa-message ' + type;
    if (!text && type === 'ai') {
        div.innerHTML = '<span class="typing-indicator"><span></span><span></span><span></span></span>';
    } else {
        div.textContent = text;
    }
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
    return id;
}
function removeMessage(id) { const msg = document.getElementById(id); if (msg) msg.remove(); }

