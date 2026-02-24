const API = '/api';
let TOKEN = localStorage.getItem('mms_token') || '';
let ws = null;

function h() { return { 'Content-Type': 'application/json', 'Authorization': `Bearer ${TOKEN}` }; }

async function api(method, path, body) {
    const opts = { method, headers: h() };
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(API + path, opts);
    if (r.status === 401) { promptToken(); throw new Error('Unauthorized'); }
    return r.json();
}

function promptToken() {
    const t = prompt('MMS API Token:');
    if (t) { TOKEN = t.trim(); localStorage.setItem('mms_token', TOKEN); location.reload(); }
}

// Nav
document.querySelectorAll('.nav-links li').forEach(li => {
    li.addEventListener('click', () => {
        document.querySelector('.nav-links .active').classList.remove('active');
        li.classList.add('active');
        document.querySelector('.section.active').classList.remove('active');
        document.getElementById('section-' + li.dataset.section).classList.add('active');
    });
});

// Health
async function poll() {
    try {
        const d = await api('GET', '/health');
        document.getElementById('health-dot').className = 'dot green';
        document.getElementById('health-text').textContent = 'Online';
        document.getElementById('s-capsules').textContent = d.capsules_total || 0;
        document.getElementById('s-running').textContent = d.capsules_running || 0;
        document.getElementById('s-envs').textContent = d.environments || 0;
        document.getElementById('s-disk').textContent = d.disk_free_gb || '-';
    } catch {
        document.getElementById('health-dot').className = 'dot red';
        document.getElementById('health-text').textContent = 'Offline';
    }
}

// Capsules
async function loadCapsules() {
    try {
        const d = await api('GET', '/capsules/');
        const caps = d.capsules || [];
        // Table
        document.getElementById('tbl-capsules').innerHTML = caps.map(c => `<tr>
            <td><code>${c.id}</code></td>
            <td>${c.name}</td>
            <td>${c.manifest?.runtime || '-'}</td>
            <td><span class="st st-${c.state}">${c.state}</span></td>
            <td>
                ${c.state === 'created' || c.state === 'ready' || c.state === 'stopped' ? `<button class="small" onclick="startCap('${c.id}')">Start</button>` : ''}
                ${c.state === 'running' ? `<button class="small danger" onclick="stopCap('${c.id}')">Stop</button>` : ''}
                <button class="small danger" onclick="destroyCap('${c.id}')">Destroy</button>
            </td></tr>`).join('');
        // Cards
        document.getElementById('capsules-grid').innerHTML = caps.map(c => `
            <div class="capsule-card">
                <div class="name">${c.name} <span class="st st-${c.state}">${c.state}</span></div>
                <div class="meta">${c.id} | ${c.manifest?.runtime || '?'} | ${c.manifest?.isolation || '?'}</div>
                <div class="actions">
                    ${c.state !== 'running' ? `<button class="small" onclick="startCap('${c.id}')">Start</button>` : ''}
                    ${c.state === 'running' ? `<button class="small danger" onclick="stopCap('${c.id}')">Stop</button>` : ''}
                    <button class="small danger" onclick="destroyCap('${c.id}')">Destroy</button>
                    <button class="small" onclick="viewLogs('${c.id}')">Logs</button>
                </div>
            </div>`).join('');
        // Terminal targets
        const sel = document.getElementById('term-target');
        const cur = sel.value;
        sel.innerHTML = '<option value="">Select capsule...</option>';
        caps.filter(c => c.state === 'running').forEach(c => {
            sel.innerHTML += `<option value="${c.id}">${c.name} (${c.id})</option>`;
        });
        sel.value = cur;
    } catch (e) { console.error(e); }
}

async function startCap(id) { await api('POST', `/capsules/${id}/start`); loadCapsules(); }
async function stopCap(id) { await api('POST', `/capsules/${id}/stop`); loadCapsules(); }
async function destroyCap(id) { if (!confirm('Destroy?')) return; await api('DELETE', `/capsules/${id}`); loadCapsules(); }
async function viewLogs(id) { const d = await api('GET', `/capsules/${id}/logs`); alert(JSON.stringify(d.logs, null, 2)); }

// Create capsule
document.getElementById('f-create-capsule').addEventListener('submit', async e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const deps = fd.get('dependencies').split(',').map(s => s.trim()).filter(Boolean);
    await api('POST', '/capsules/', {
        name: fd.get('name'),
        runtime: fd.get('runtime'),
        isolation: fd.get('isolation'),
        entrypoint: fd.get('entrypoint') || 'main.py',
        code: fd.get('code') || null,
        dependencies: deps,
    });
    e.target.reset();
    loadCapsules();
});

// Environments
async function loadEnvs() {
    try {
        const d = await api('GET', '/envs/');
        document.getElementById('envs-list').innerHTML = (d.environments || []).map(e => `
            <div class="card"><b>${e.name}</b> (${e.runtime}) - packages: ${e.packages || '[]'}
            <button class="small danger" onclick="delEnv('${e.id}')">Delete</button></div>
        `).join('') || '<p style="color:var(--dim)">No environments</p>';
    } catch (e) { console.error(e); }
}
async function delEnv(id) { await api('DELETE', `/envs/${id}`); loadEnvs(); }

document.getElementById('f-create-env').addEventListener('submit', async e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    await api('POST', '/envs/', {
        name: fd.get('name'),
        runtime: fd.get('runtime'),
        packages: fd.get('packages').split(',').map(s => s.trim()).filter(Boolean),
    });
    e.target.reset();
    loadEnvs();
});

// Pipelines
async function loadPipelines() {
    try {
        const d = await api('GET', '/pipelines/');
        document.getElementById('pipelines-list').innerHTML = (d.pipelines || []).map(p =>
            `<div class="card"><b>${p.name}</b> - ${p.state}</div>`
        ).join('') || '<p style="color:var(--dim)">No pipelines</p>';
    } catch (e) { console.error(e); }
}

document.getElementById('f-run-pipeline').addEventListener('submit', async e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
        const steps = JSON.parse(fd.get('steps'));
        await api('POST', '/pipelines/', { name: fd.get('name'), steps });
        loadPipelines();
    } catch (err) { alert('Invalid JSON: ' + err.message); }
});

// Terminal
const tout = document.getElementById('term-output');

document.getElementById('f-term').addEventListener('submit', async e => {
    e.preventDefault();
    const cmd = document.getElementById('term-cmd').value.trim();
    const target = document.getElementById('term-target').value;
    if (!cmd || !target) return;
    tout.innerHTML += `<span style="color:var(--green)">$ ${cmd}</span>\n`;
    document.getElementById('term-cmd').value = '';
    try {
        const d = await api('POST', '/commands/exec', { capsule_id: target, command: cmd });
        const r = d.result || {};
        if (r.stdout) tout.innerHTML += r.stdout;
        if (r.stderr) tout.innerHTML += `<span style="color:var(--red)">${r.stderr}</span>`;
        if (r.error) tout.innerHTML += `<span style="color:var(--red)">${r.error}</span>`;
        tout.innerHTML += '\n';
    } catch (err) { tout.innerHTML += `<span style="color:var(--red)">${err.message}</span>\n`; }
    tout.scrollTop = tout.scrollHeight;
});

// WebSocket terminal
document.getElementById('btn-ws-connect').addEventListener('click', () => {
    const id = document.getElementById('term-target').value;
    if (!id) return;
    if (ws) ws.close();
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${proto}//${location.host}/ws/terminal/${id}?token=${TOKEN}`);
    ws.onmessage = e => {
        const d = JSON.parse(e.data);
        if (d.type === 'output') {
            if (d.stdout) tout.innerHTML += d.stdout;
            if (d.stderr) tout.innerHTML += `<span style="color:var(--red)">${d.stderr}</span>`;
        } else if (d.type === 'connected') {
            tout.innerHTML += `<span style="color:var(--accent2)">${d.data}</span>\n`;
        }
        tout.scrollTop = tout.scrollHeight;
    };
    ws.onclose = () => { tout.innerHTML += '<span style="color:var(--dim)">Disconnected</span>\n'; };
});

// Protocol
document.getElementById('btn-proto-run').addEventListener('click', async () => {
    const code = document.getElementById('proto-code').value;
    const out = document.getElementById('proto-output');
    try {
        const d = await api('POST', '/commands/protocol', { code });
        out.innerHTML = JSON.stringify(d.results, null, 2);
    } catch (err) { out.innerHTML = `<span style="color:var(--red)">${err.message}</span>`; }
});

// Init
if (!TOKEN) promptToken();
poll(); loadCapsules(); loadEnvs(); loadPipelines();
setInterval(() => { poll(); loadCapsules(); }, 8000);
