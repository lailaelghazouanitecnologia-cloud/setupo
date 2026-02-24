/**
 * Setupo Dashboard - Client-side JavaScript
 * Manages communication with the orchestrator API
 */

const API = '/api';
let TOKEN = localStorage.getItem('setupo_token') || '';

// ── Auth ────────────────────────────────────────────────────────

function headers() {
    return {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${TOKEN}`,
    };
}

async function api(method, path, body = null) {
    const opts = { method, headers: headers() };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(`${API}${path}`, opts);
    if (res.status === 401) {
        promptToken();
        throw new Error('Unauthorized');
    }
    return res.json();
}

function promptToken() {
    const t = prompt('Enter your Setupo API token:');
    if (t) {
        TOKEN = t.trim();
        localStorage.setItem('setupo_token', TOKEN);
        location.reload();
    }
}

// ── Navigation ──────────────────────────────────────────────────

document.querySelectorAll('.nav-links li').forEach(li => {
    li.addEventListener('click', () => {
        document.querySelector('.nav-links .active').classList.remove('active');
        li.classList.add('active');
        document.querySelector('.section.active').classList.remove('active');
        document.getElementById(`section-${li.dataset.section}`).classList.add('active');
    });
});

// ── Health Check ────────────────────────────────────────────────

async function checkHealth() {
    try {
        const data = await api('GET', '/health');
        document.getElementById('health-status').className = 'status-dot green';
        document.getElementById('health-text').textContent = 'Connected';
        document.getElementById('stat-microvms').textContent =
            data.instances?.running || 0;
        document.getElementById('stat-disk').textContent =
            data.disk?.free_gb || '-';
        return data;
    } catch {
        document.getElementById('health-status').className = 'status-dot red';
        document.getElementById('health-text').textContent = 'Disconnected';
    }
}

// ── Instances ───────────────────────────────────────────────────

async function loadInstances() {
    try {
        const [microvms, vms] = await Promise.all([
            api('GET', '/microvms/'),
            api('GET', '/vms/'),
        ]);
        renderInstancesTable([
            ...(microvms.microvms || []),
            ...(vms.vms || []),
        ]);
        renderInstanceList('microvms-list', microvms.microvms || []);
        renderInstanceList('vms-list', vms.vms || []);
        updateTerminalTargets([
            ...(microvms.microvms || []),
            ...(vms.vms || []),
        ]);
        document.getElementById('stat-microvms').textContent =
            (microvms.microvms || []).length;
        document.getElementById('stat-vms').textContent =
            (vms.vms || []).length;
    } catch (e) {
        console.error('Failed to load instances:', e);
    }
}

function renderInstancesTable(instances) {
    const tbody = document.getElementById('instances-tbody');
    tbody.innerHTML = instances.map(i => `
        <tr>
            <td><code>${i.id}</code></td>
            <td>${i.name}</td>
            <td>${i.vm_type}</td>
            <td><span class="state state-${i.state}">${i.state}</span></td>
            <td><code>${i.ip}</code></td>
            <td>${i.vcpus}</td>
            <td>${i.memory_mb}MB</td>
            <td>
                ${i.state === 'running' ? `<button class="small danger" onclick="stopInstance('${i.id}','${i.vm_type}')">Stop</button>` : ''}
                <button class="small danger" onclick="destroyInstance('${i.id}','${i.vm_type}')">Destroy</button>
            </td>
        </tr>
    `).join('');
}

function renderInstanceList(containerId, instances) {
    const el = document.getElementById(containerId);
    if (!instances.length) {
        el.innerHTML = '<p style="color:var(--text-dim);font-size:0.85em">No instances</p>';
        return;
    }
    el.innerHTML = instances.map(i => `
        <div class="instance-card">
            <div class="instance-info">
                <div class="name">${i.name} <span class="state state-${i.state}">${i.state}</span></div>
                <div class="meta">${i.id} | ${i.ip} | ${i.vcpus}vCPU / ${i.memory_mb}MB / ${i.disk_mb}MB</div>
            </div>
            <div class="instance-actions">
                ${i.state === 'running' ? `<button class="small danger" onclick="stopInstance('${i.id}','${i.vm_type}')">Stop</button>` : ''}
                <button class="small danger" onclick="destroyInstance('${i.id}','${i.vm_type}')">Destroy</button>
            </div>
        </div>
    `).join('');
}

function updateTerminalTargets(instances) {
    const select = document.getElementById('terminal-target');
    const current = select.value;
    select.innerHTML = '<option value="">Select instance...</option>';
    instances.filter(i => i.state === 'running').forEach(i => {
        select.innerHTML += `<option value="${i.id}">${i.name} (${i.id})</option>`;
    });
    select.value = current;
}

// ── Actions ─────────────────────────────────────────────────────

async function stopInstance(id, type) {
    const prefix = type === 'microvm' ? '/microvms' : '/vms';
    await api('POST', `${prefix}/${id}/stop`);
    loadInstances();
}

async function destroyInstance(id, type) {
    if (!confirm(`Destroy ${id}?`)) return;
    const prefix = type === 'microvm' ? '/microvms' : '/vms';
    await api('DELETE', `${prefix}/${id}`);
    loadInstances();
}

// ── Create Forms ────────────────────────────────────────────────

document.getElementById('create-microvm-form').addEventListener('submit', async e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    await api('POST', '/microvms/', {
        name: fd.get('name'),
        vcpus: parseInt(fd.get('vcpus')),
        memory_mb: parseInt(fd.get('memory_mb')),
        disk_mb: parseInt(fd.get('disk_mb')),
    });
    e.target.reset();
    loadInstances();
});

document.getElementById('create-vm-form').addEventListener('submit', async e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    await api('POST', '/vms/', {
        name: fd.get('name'),
        vcpus: parseInt(fd.get('vcpus')),
        memory_mb: parseInt(fd.get('memory_mb')),
        disk_mb: parseInt(fd.get('disk_mb')),
    });
    e.target.reset();
    loadInstances();
});

// ── Terminal ────────────────────────────────────────────────────

const termOutput = document.getElementById('terminal-output');

document.getElementById('terminal-form').addEventListener('submit', async e => {
    e.preventDefault();
    const cmd = document.getElementById('terminal-cmd').value.trim();
    const target = document.getElementById('terminal-target').value;
    if (!cmd || !target) return;

    termOutput.innerHTML += `<span style="color:var(--green)">$ ${cmd}</span>\n`;
    document.getElementById('terminal-cmd').value = '';

    try {
        const data = await api('POST', '/commands/exec', {
            instance_id: target,
            command: cmd,
        });
        const result = data.result;
        if (result.stdout) termOutput.innerHTML += result.stdout + '\n';
        if (result.stderr) termOutput.innerHTML += `<span style="color:var(--red)">${result.stderr}</span>\n`;
        if (result.error) termOutput.innerHTML += `<span style="color:var(--red)">${result.error}</span>\n`;
    } catch (err) {
        termOutput.innerHTML += `<span style="color:var(--red)">Error: ${err.message}</span>\n`;
    }
    termOutput.scrollTop = termOutput.scrollHeight;
});

// ── SSH ─────────────────────────────────────────────────────────

document.getElementById('ssh-form').addEventListener('submit', async e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const output = document.getElementById('ssh-output');
    output.innerHTML += `<span style="color:var(--green)">ssh ${fd.get('host')} "${fd.get('command')}"</span>\n`;

    try {
        const data = await api('POST', '/commands/ssh', {
            host: fd.get('host'),
            command: fd.get('command'),
        });
        if (data.result.stdout) output.innerHTML += data.result.stdout + '\n';
        if (data.result.stderr) output.innerHTML += `<span style="color:var(--red)">${data.result.stderr}</span>\n`;
    } catch (err) {
        output.innerHTML += `<span style="color:var(--red)">Error: ${err.message}</span>\n`;
    }
    output.scrollTop = output.scrollHeight;
});

// ── Capsules ────────────────────────────────────────────────────

async function loadCapsules() {
    try {
        const data = await api('GET', '/capsules/');
        document.getElementById('stat-capsules').textContent =
            (data.capsules || []).length;
        const grid = document.getElementById('capsules-list');
        grid.innerHTML = (data.capsules || []).map(c => `
            <div class="capsule-card">
                <div class="name">${c.name || c}</div>
                <div class="desc">${c.description || 'No description'}</div>
            </div>
        `).join('') || '<p style="color:var(--text-dim);font-size:0.85em">No capsules installed</p>';
    } catch (e) {
        console.error('Failed to load capsules:', e);
    }
}

document.getElementById('upload-capsule-form').addEventListener('submit', async e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const res = await fetch(`${API}/capsules/upload`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${TOKEN}` },
        body: fd,
    });
    if (res.ok) {
        e.target.reset();
        loadCapsules();
    }
});

// ── Init ────────────────────────────────────────────────────────

if (!TOKEN) promptToken();

checkHealth();
loadInstances();
loadCapsules();

// Poll every 10s
setInterval(() => {
    checkHealth();
    loadInstances();
}, 10000);
