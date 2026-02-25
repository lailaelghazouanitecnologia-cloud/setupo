/* ── Setupo Dashboard v0.3 ──────────────────────────────────────
   Connects to the Setupo REST API to manage workspaces, instances,
   and run commands via SSH exec.
*/

const API = '/api';
let TOKEN = localStorage.getItem('setupo_token') || '';
let PROJECT_ID = localStorage.getItem('setupo_project') || '';
let selectedWs = null; // currently selected workspace name

// ── Helpers ─────────────────────────────────────────────────────

function h() {
    return { 'Content-Type': 'application/json', 'Authorization': `Bearer ${TOKEN}` };
}

async function api(method, path, body) {
    const opts = { method, headers: h() };
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(API + path, opts);
    if (r.status === 401) { promptAuth(); throw new Error('Unauthorized'); }
    if (!r.ok) {
        const err = await r.json().catch(() => ({ error: r.statusText }));
        throw new Error(err.error || err.detail || r.statusText);
    }
    return r.json();
}

function promptAuth() {
    const t = prompt('Setupo API Token:');
    if (t) {
        TOKEN = t.trim();
        localStorage.setItem('setupo_token', TOKEN);
    }
    const p = prompt('Project ID (proj_xxxx):');
    if (p) {
        PROJECT_ID = p.trim();
        localStorage.setItem('setupo_project', PROJECT_ID);
    }
    if (TOKEN && PROJECT_ID) location.reload();
}

function esc(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

function fmtSize(bytes) {
    if (bytes < 1024) return bytes + 'B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + 'KB';
    return (bytes / 1048576).toFixed(1) + 'MB';
}

// ── Navigation ──────────────────────────────────────────────────

document.querySelectorAll('.nav-links li').forEach(li => {
    li.addEventListener('click', () => {
        document.querySelector('.nav-links .active').classList.remove('active');
        li.classList.add('active');
        document.querySelector('.section.active').classList.remove('active');
        document.getElementById('section-' + li.dataset.section).classList.add('active');
    });
});

// Tab switching
document.querySelectorAll('.tabs').forEach(tabBar => {
    tabBar.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            tabBar.querySelector('.tab.active').classList.remove('active');
            tab.classList.add('active');
            const parent = tabBar.parentElement;
            parent.querySelector('.tab-content.active').classList.remove('active');
            parent.querySelector('#tab-' + tab.dataset.tab).classList.add('active');
        });
    });
});

// Modals
function showModal(id) {
    document.getElementById(id).classList.remove('hidden');
    populateSelects();
}
function hideModal(id) { document.getElementById(id).classList.add('hidden'); }

// Close modal on backdrop click
document.querySelectorAll('.modal').forEach(m => {
    m.addEventListener('click', e => { if (e.target === m) m.classList.add('hidden'); });
});

// ── API helpers ─────────────────────────────────────────────────

function pApi(path) { return `/projects/${PROJECT_ID}${path}`; }

// ── Health ──────────────────────────────────────────────────────

async function pollHealth() {
    try {
        await api('GET', '/health');
        document.getElementById('health-dot').className = 'dot green';
        document.getElementById('health-text').textContent = 'Online';
    } catch {
        document.getElementById('health-dot').className = 'dot red';
        document.getElementById('health-text').textContent = 'Offline';
    }
}

// ── Overview ────────────────────────────────────────────────────

async function loadOverview() {
    try {
        const [wsData, instData] = await Promise.all([
            api('GET', pApi('/workspaces')),
            api('GET', pApi('/instances')),
        ]);

        const ws = wsData.workspaces || [];
        const inst = instData.instances || [];

        document.getElementById('s-workspaces').textContent = ws.length;
        document.getElementById('s-instances').textContent = inst.length;
        document.getElementById('s-running').textContent = inst.filter(i => i.state === 'running').length;
        document.getElementById('s-ready').textContent = inst.filter(i => i.state === 'ready').length;

        // Recent workspaces
        const ovWs = document.getElementById('ov-workspaces');
        if (ws.length === 0) {
            ovWs.innerHTML = '<p class="dim">No workspaces yet</p>';
        } else {
            ovWs.innerHTML = ws.slice(0, 5).map(w => `
                <div class="file-item" style="margin-bottom:2px">
                    <span class="icon">${w.ws_type === 'git' ? '&#9741;' : '&#9783;'}</span>
                    <span class="name">${esc(w.name)}</span>
                    <span class="size">${esc(w.stack || w.ws_type || 'custom')}</span>
                </div>
            `).join('');
        }

        // Instances
        const ovInst = document.getElementById('ov-instances');
        if (inst.length === 0) {
            ovInst.innerHTML = '<p class="dim">No instances yet</p>';
        } else {
            ovInst.innerHTML = inst.slice(0, 5).map(i => `
                <div class="file-item" style="margin-bottom:2px">
                    <span class="icon">&#9654;</span>
                    <span class="name">${esc(i.label || i.id)}</span>
                    <span class="st st-${i.state}">${i.state}</span>
                </div>
            `).join('');
        }
    } catch (e) {
        console.error('Overview load failed:', e);
    }
}

// ── Workspaces ──────────────────────────────────────────────────

let allWorkspaces = [];

async function loadWorkspaces() {
    try {
        const data = await api('GET', pApi('/workspaces'));
        allWorkspaces = data.workspaces || [];

        const list = document.getElementById('ws-list');
        if (allWorkspaces.length === 0) {
            list.innerHTML = '<p class="dim">No workspaces. Create one to get started.</p>';
            return;
        }

        list.innerHTML = allWorkspaces.map(w => `
            <div class="ws-card ${selectedWs === w.name ? 'selected' : ''}" onclick="selectWorkspace('${esc(w.name)}')">
                <div class="ws-name">
                    ${esc(w.name)}
                    <span class="ws-type">${esc(w.stack || w.ws_type || 'custom')}</span>
                    ${w.instance_id ? '<span class="ws-type" style="color:var(--green)">linked</span>' : ''}
                </div>
                ${w.description ? `<div class="ws-desc">${esc(w.description)}</div>` : ''}
                <div class="ws-meta">
                    ${w.git_url ? `<span>git: ${esc(w.git_url.split('/').pop())}</span>` : '<span>local</span>'}
                    ${w.exists === false ? '<span style="color:var(--red)">missing</span>' : ''}
                </div>
            </div>
        `).join('');
    } catch (e) {
        console.error('Workspaces load failed:', e);
    }
}

async function selectWorkspace(name) {
    selectedWs = name;
    loadWorkspaces(); // refresh selection highlight

    const detail = document.getElementById('ws-detail');
    detail.classList.remove('hidden');

    try {
        const data = await api('GET', pApi(`/workspaces/${name}`));
        const ws = data.workspace;

        document.getElementById('ws-detail-name').textContent = ws.name;
        document.getElementById('ws-detail-meta').innerHTML = [
            `type: ${esc(ws.ws_type || 'custom')}`,
            `stack: ${esc(ws.stack || 'auto')}`,
            ws.instance_id ? `instance: ${esc(ws.instance_id)}` : null,
            ws.git_url ? `git: ${esc(ws.git_url)}` : null,
        ].filter(Boolean).join(' &middot; ');

        // Load config
        loadConfig(name);
        // Load files
        loadFiles(name, '.');
    } catch (e) {
        console.error('Failed to load workspace:', e);
    }
}

async function loadConfig(name) {
    try {
        const data = await api('GET', pApi(`/workspaces/${name}/config`));
        document.getElementById('ws-config-raw').textContent = data.raw || 'No config.toml';
    } catch {
        document.getElementById('ws-config-raw').textContent = '# No config.toml found';
    }
}

let currentFilePath = '.';
async function loadFiles(name, path) {
    currentFilePath = path;
    document.getElementById('ws-file-path').textContent = path;

    try {
        const data = await api('GET', pApi(`/workspaces/${name}/files?path=${encodeURIComponent(path)}`));
        const items = data.items || [];

        const el = document.getElementById('ws-files');
        let html = '';

        // Back button
        if (path !== '.') {
            const parent = path.split('/').slice(0, -1).join('/') || '.';
            html += `<div class="file-item dir" onclick="loadFiles('${esc(name)}','${esc(parent)}')">
                <span class="icon">..</span>
                <span class="name">..</span>
            </div>`;
        }

        html += items.map(item => {
            if (item.type === 'dir') {
                return `<div class="file-item dir" onclick="loadFiles('${esc(name)}','${esc(item.path)}')">
                    <span class="icon">&#128193;</span>
                    <span class="name">${esc(item.name)}</span>
                </div>`;
            }
            return `<div class="file-item" onclick="viewFile('${esc(name)}','${esc(item.path)}')">
                <span class="icon">&#128196;</span>
                <span class="name">${esc(item.name)}</span>
                <span class="size">${fmtSize(item.size)}</span>
            </div>`;
        }).join('');

        el.innerHTML = html || '<p class="dim">Empty directory</p>';
    } catch (e) {
        document.getElementById('ws-files').innerHTML = `<p class="dim">Error: ${esc(e.message)}</p>`;
    }
}

async function viewFile(name, path) {
    try {
        const data = await api('GET', pApi(`/workspaces/${name}/files/read?path=${encodeURIComponent(path)}`));
        // Switch to config tab area to show file content
        const raw = document.getElementById('ws-config-raw');
        raw.textContent = data.content;
        // Switch tab
        document.querySelector('.tabs .tab.active').classList.remove('active');
        document.querySelectorAll('.tabs .tab')[1].classList.add('active');
        document.querySelector('.tab-content.active').classList.remove('active');
        document.getElementById('tab-config').classList.add('active');
        raw.scrollTop = 0;
    } catch (e) {
        alert('Failed to read file: ' + e.message);
    }
}

function editConfig() {
    alert('Config editing coming soon. Use the API:\nPUT /api/projects/{id}/workspaces/{name}/config');
}

// Create workspace
document.getElementById('f-create-ws').addEventListener('submit', async e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
        await api('POST', pApi('/workspaces'), {
            name: fd.get('name'),
            stack: fd.get('stack') || '',
            description: fd.get('description') || '',
            git_url: fd.get('git_url') || null,
            branch: fd.get('branch') || 'main',
            instance_id: fd.get('instance_id') || null,
        });
        hideModal('modal-create-ws');
        e.target.reset();
        loadWorkspaces();
        loadOverview();
    } catch (err) {
        alert('Error: ' + err.message);
    }
});

async function deployWorkspace() {
    if (!selectedWs) return;
    if (!confirm(`Deploy workspace "${selectedWs}" to its linked instance?`)) return;
    try {
        const r = await api('POST', pApi(`/workspaces/${selectedWs}/deploy`));
        alert(`Deploy ${r.state}: ${r.url || r.error || ''}`);
        loadInstances();
    } catch (e) {
        alert('Deploy failed: ' + e.message);
    }
}

async function deleteWorkspace() {
    if (!selectedWs) return;
    if (!confirm(`Delete workspace "${selectedWs}"? This removes all files.`)) return;
    try {
        await api('DELETE', pApi(`/workspaces/${selectedWs}`));
        selectedWs = null;
        document.getElementById('ws-detail').classList.add('hidden');
        loadWorkspaces();
        loadOverview();
    } catch (e) {
        alert('Delete failed: ' + e.message);
    }
}

// ── Instances ───────────────────────────────────────────────────

let allInstances = [];

async function loadInstances() {
    try {
        const data = await api('GET', pApi('/instances'));
        allInstances = data.instances || [];

        const tbody = document.getElementById('tbl-instances');
        if (allInstances.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="dim">No instances</td></tr>';
            return;
        }

        tbody.innerHTML = allInstances.map(i => `<tr>
            <td><code>${esc(i.id.substring(0, 14))}</code></td>
            <td>${esc(i.label || '-')}</td>
            <td>${esc(i.region)}</td>
            <td><code>${esc(i.ip || '-')}</code></td>
            <td><span class="st st-${i.state}">${i.state}</span></td>
            <td>${esc(i.workspace || '-')}</td>
            <td>
                ${i.state === 'ready' || i.state === 'running' ? `<button class="small" onclick="execModal('${i.id}')">Exec</button>` : ''}
                ${i.state === 'running' ? `<button class="small" onclick="stopInst('${i.id}')">Stop</button>` : ''}
                ${i.state === 'stopped' ? `<button class="small" onclick="startInst('${i.id}')">Start</button>` : ''}
                <button class="small danger" onclick="deleteInst('${i.id}')">Delete</button>
            </td>
        </tr>`).join('');

        // Update terminal instance selector
        const sel = document.getElementById('term-instance');
        const cur = sel.value;
        sel.innerHTML = '<option value="">Select instance...</option>';
        allInstances.filter(i => i.state === 'ready' || i.state === 'running').forEach(i => {
            sel.innerHTML += `<option value="${i.id}" data-ip="${i.ip || ''}">${esc(i.label || i.id)} (${i.ip || 'no ip'})</option>`;
        });
        sel.value = cur;
    } catch (e) {
        console.error('Instances load failed:', e);
    }
}

// Instance actions
async function stopInst(id) {
    if (!confirm('Stop instance?')) return;
    await api('POST', pApi(`/instances/${id}/stop`));
    loadInstances();
}
async function startInst(id) {
    await api('POST', pApi(`/instances/${id}/start`));
    loadInstances();
}
async function deleteInst(id) {
    if (!confirm('Destroy instance? This is irreversible.')) return;
    await api('DELETE', pApi(`/instances/${id}`));
    loadInstances();
    loadOverview();
}
function execModal(id) {
    // Switch to terminal section with this instance selected
    document.querySelector('.nav-links .active').classList.remove('active');
    document.querySelector('[data-section="terminal"]').classList.add('active');
    document.querySelector('.section.active').classList.remove('active');
    document.getElementById('section-terminal').classList.add('active');
    document.getElementById('term-instance').value = id;
    updateTermIp();
    document.getElementById('term-cmd').focus();
}

// Create instance
document.getElementById('f-create-inst').addEventListener('submit', async e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
        await api('POST', pApi('/instances'), {
            type: fd.get('type'),
            label: fd.get('label'),
            region: fd.get('region'),
            plan: fd.get('plan'),
            domain: fd.get('domain') || null,
            workspace: fd.get('workspace') || null,
        });
        hideModal('modal-create-inst');
        e.target.reset();
        loadInstances();
        loadOverview();
    } catch (err) {
        alert('Error: ' + err.message);
    }
});

// ── Terminal ────────────────────────────────────────────────────

const tout = document.getElementById('term-output');

function updateTermIp() {
    const sel = document.getElementById('term-instance');
    const opt = sel.options[sel.selectedIndex];
    document.getElementById('term-ip').textContent = opt?.dataset?.ip ? `(${opt.dataset.ip})` : '';
}
document.getElementById('term-instance').addEventListener('change', updateTermIp);

document.getElementById('f-term').addEventListener('submit', async e => {
    e.preventDefault();
    const cmd = document.getElementById('term-cmd').value.trim();
    const instId = document.getElementById('term-instance').value;
    if (!cmd || !instId) return;

    tout.innerHTML += `<span style="color:var(--green)">$ ${esc(cmd)}</span>\n`;
    document.getElementById('term-cmd').value = '';

    try {
        const d = await api('POST', pApi(`/instances/${instId}/exec`), { command: cmd });
        if (d.output) tout.innerHTML += esc(d.output);
        if (d.exit_code !== 0) {
            tout.innerHTML += `\n<span style="color:var(--dim)">[exit ${d.exit_code}]</span>`;
        }
        tout.innerHTML += '\n';
    } catch (err) {
        tout.innerHTML += `<span style="color:var(--red)">${esc(err.message)}</span>\n`;
    }
    tout.scrollTop = tout.scrollHeight;
});

// ── Populate select dropdowns ───────────────────────────────────

async function populateSelects() {
    // Instances in workspace create modal
    const wsSel = document.getElementById('ws-instance-select');
    wsSel.innerHTML = '<option value="">None</option>';
    allInstances.filter(i => i.state === 'ready' || i.state === 'running').forEach(i => {
        wsSel.innerHTML += `<option value="${i.id}">${esc(i.label || i.id)} (${i.ip || '?'})</option>`;
    });

    // Workspaces in instance create modal
    const instSel = document.getElementById('inst-ws-select');
    instSel.innerHTML = '<option value="">None (provision only)</option>';
    allWorkspaces.forEach(w => {
        instSel.innerHTML += `<option value="${w.name}">${esc(w.name)}</option>`;
    });
}

// ── Init ────────────────────────────────────────────────────────

if (!TOKEN || !PROJECT_ID) promptAuth();

async function init() {
    await pollHealth();
    await Promise.all([loadOverview(), loadWorkspaces(), loadInstances()]);
}

init();
setInterval(() => { pollHealth(); loadOverview(); }, 15000);
setInterval(() => { loadInstances(); }, 10000);
