// ── Auth check ──
let currentUser = null;
(async () => {
  const res = await fetch('/api/me');
  currentUser = await res.json();
  if (!currentUser) { window.location.href = '/login.html'; return; }
  document.getElementById('currentUser').textContent = currentUser.username;
  initApp();
})();

function logout() {
  fetch('/api/logout', { method: 'POST' }).then(() => { window.location.href = '/login.html'; });
}

// ── State ──
let map, routeLayer;
let editing = false;
let currentPoints = [];
let currentRouteId = null;
let allRoutes = [];
let draftMarkers = [];

// ── Init map ──
function initApp() {
  map = L.map('map').setView([39.9042, 116.4074], 11); // Default: Beijing
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19
  }).addTo(map);

  routeLayer = L.layerGroup().addTo(map);
  loadRoutes();

  map.on('click', onMapClick);
}

// ── Load routes ──
async function loadRoutes() {
  const search = document.getElementById('searchInput').value;
  const res = await fetch('/api/routes?search=' + encodeURIComponent(search));
  allRoutes = await res.json();
  renderRouteList();
}

function renderRouteList() {
  const container = document.getElementById('routeList');
  container.innerHTML = allRoutes.map(r => `
    <div class="route-card ${currentRouteId === r.id ? 'active' : ''}" onclick="viewRoute(${r.id})">
      <div class="name">
        ${escapeHtml(r.name)}
        <span class="difficulty ${r.difficulty}">${diffLabel(r.difficulty)}</span>
      </div>
      <div class="meta">${escapeHtml(r.creator_name)} · ${r.created_at?.slice(0, 16)} · ${r.duration || '--'}</div>
      ${r.notes ? `<div class="notes">${escapeHtml(r.notes)}</div>` : ''}
    </div>
  `).join('');
}

function diffLabel(d) {
  return d === 'easy' ? '简单' : d === 'medium' ? '中等' : '困难';
}

function escapeHtml(s) {
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

// ── View route ──
async function viewRoute(id) {
  currentRouteId = id;
  editing = false;
  clearDraftMarkers();
  document.getElementById('mapHint').classList.add('hidden');
  renderRouteList();

  const res = await fetch('/api/routes/' + id);
  const route = await res.json();
  drawRoute(route.points);
  map.fitBounds(L.polyline(route.points).getBounds().pad(0.1));
  showRoutePanel(route);
}

function drawRoute(points) {
  routeLayer.clearLayers();
  if (!points || points.length === 0) return;
  const latlngs = points.map(p => [p.lat, p.lng]);
  L.polyline(latlngs, { color: '#667eea', weight: 4 }).addTo(routeLayer);
  points.forEach((p, i) => {
    L.circleMarker([p.lat, p.lng], {
      radius: 6, color: i === 0 ? '#2ecc71' : i === points.length - 1 ? '#e74c3c' : '#667eea',
      fillOpacity: 1, weight: 2
    }).bindTooltip('' + (i + 1)).addTo(routeLayer);
  });
}

// ── Route panel ──
function showRoutePanel(route) {
  const panel = document.getElementById('routePanel');
  const isOwner = route.creator_id === currentUser.id;
  panel.innerHTML = `
    <h3>${escapeHtml(route.name)}</h3>
    <div style="font-size:12px;color:#999;">
      创建者: ${escapeHtml(route.creator_name)} · ${route.created_at?.slice(0, 16)}<br>
      难度: ${diffLabel(route.difficulty)} · 预计时长: ${route.duration || '--'}
    </div>
    ${route.notes ? `<p style="font-size:13px;margin-top:8px;color:#555;">${escapeHtml(route.notes)}</p>` : ''}
    ${isOwner ? `<div class="actions">
      <button class="btn-primary" onclick="editRoute(${route.id})">编辑</button>
      <button class="btn-danger" onclick="deleteRoute(${route.id})">删除</button>
    </div>` : ''}
    <button class="btn-cancel" style="width:100%;margin-top:8px;" onclick="closePanel()">关闭</button>
    ${renderComments(route.comments || [])}
    <div class="comment-form">
      <input type="text" id="commentInput" placeholder="添加评论/建议..." onkeydown="if(event.key==='Enter')addComment(${route.id})">
      <button onclick="addComment(${route.id})">发送</button>
    </div>
  `;
  panel.classList.remove('hidden');
}

function renderComments(comments) {
  if (!comments.length) return '<div class="comments-section"><h4>尚无评论</h4></div>';
  return `<div class="comments-section"><h4>评论 (${comments.length})</h4>
    ${comments.map(c => `
      <div class="comment">
        <span class="author">${escapeHtml(c.author_name)}</span><span class="time">${c.created_at?.slice(0, 16)}</span>
        <div class="body">${escapeHtml(c.content)}</div>
      </div>
    `).join('')}
  </div>`;
}

function closePanel() {
  document.getElementById('routePanel').classList.add('hidden');
  if (editing) cancelEdit();
}

// ── Comments ──
async function addComment(routeId) {
  const input = document.getElementById('commentInput');
  const content = input.value.trim();
  if (!content) return;
  const res = await fetch('/api/routes/' + routeId + '/comments', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content })
  });
  if (res.ok) viewRoute(routeId);
}

// ── Create new route ──
function startNewRoute() {
  editing = true;
  currentRouteId = null;
  currentPoints = [];
  clearDraftMarkers();
  routeLayer.clearLayers();
  document.getElementById('mapHint').classList.remove('hidden');
  renderRouteList();
  showEditPanel();
}

function onMapClick(e) {
  if (!editing) return;
  currentPoints.push({ lat: e.latlng.lat, lng: e.latlng.lng });
  addDraftMarker(e.latlng.lat, e.latlng.lng, currentPoints.length);
  drawRoute(currentPoints);
  updateEditPanel();
}

function addDraftMarker(lat, lng, num) {
  const marker = L.circleMarker([lat, lng], {
    radius: 8, color: '#fff', fillColor: '#667eea', fillOpacity: 1, weight: 3
  }).bindTooltip('' + num).addTo(map);
  marker.on('click', () => {
    const idx = draftMarkers.indexOf(marker);
    if (idx >= 0 && confirm('删除第 ' + (idx + 1) + ' 个点？')) {
      currentPoints.splice(idx, 1);
      map.removeLayer(marker);
      draftMarkers.splice(idx, 1);
      draftMarkers.forEach((m, i) => m.setTooltipContent('' + (i + 1)));
      drawRoute(currentPoints);
      updateEditPanel();
    }
  });
  draftMarkers.push(marker);
}

function clearDraftMarkers() {
  draftMarkers.forEach(m => map.removeLayer(m));
  draftMarkers = [];
}

// ── Edit panel ──
function showEditPanel(points) {
  const panel = document.getElementById('routePanel');
  panel.innerHTML = `
    <h3>${currentRouteId ? '编辑路线' : '创建新路线'}</h3>
    <div id="editPointCount" style="font-size:12px;color:#999;margin-bottom:8px;">
      已添加 ${currentPoints.length} 个点位
    </div>
    <label>路线名称</label>
    <input type="text" id="editName" placeholder="例如: 周末环湖骑行">
    <label>难度</label>
    <select id="editDifficulty">
      <option value="easy">简单</option>
      <option value="medium" selected>中等</option>
      <option value="hard">困难</option>
    </select>
    <label>预计时长</label>
    <input type="text" id="editDuration" placeholder="例如: 2小时">
    <label>备注/建议</label>
    <textarea id="editNotes" placeholder="添加路线建议、注意事项..."></textarea>
    <div class="actions">
      <button class="btn-primary" onclick="saveRoute()">保存路线</button>
      <button class="btn-cancel" onclick="cancelEdit()">取消</button>
    </div>
  `;
  panel.classList.remove('hidden');
  if (points) {
    document.getElementById('editName').value = points.name || '';
    document.getElementById('editDifficulty').value = points.difficulty || 'medium';
    document.getElementById('editDuration').value = points.duration || '';
    document.getElementById('editNotes').value = points.notes || '';
  }
}

function updateEditPanel() {
  const el = document.getElementById('editPointCount');
  if (el) el.textContent = '已添加 ' + currentPoints.length + ' 个点位';
}

async function editRoute(id) {
  editing = true;
  currentRouteId = id;
  clearDraftMarkers();
  document.getElementById('mapHint').classList.remove('hidden');

  const res = await fetch('/api/routes/' + id);
  const route = await res.json();
  currentPoints = route.points.map(p => ({ lat: p.lat, lng: p.lng }));
  currentPoints.forEach((p, i) => addDraftMarker(p.lat, p.lng, i + 1));
  drawRoute(currentPoints);
  if (currentPoints.length) map.fitBounds(L.polyline(currentPoints).getBounds().pad(0.1));
  showEditPanel(route);
}

function cancelEdit() {
  editing = false;
  currentRouteId = null;
  currentPoints = [];
  clearDraftMarkers();
  routeLayer.clearLayers();
  document.getElementById('mapHint').classList.add('hidden');
  document.getElementById('routePanel').classList.add('hidden');
  renderRouteList();
}

async function saveRoute() {
  const name = document.getElementById('editName').value.trim();
  if (!name) return alert('请输入路线名称');
  if (currentPoints.length < 2) return alert('请至少添加2个点位');

  const body = {
    name,
    difficulty: document.getElementById('editDifficulty').value,
    duration: document.getElementById('editDuration').value.trim(),
    notes: document.getElementById('editNotes').value.trim(),
    points: currentPoints
  };

  if (currentRouteId) {
    await fetch('/api/routes/' + currentRouteId, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
  } else {
    await fetch('/api/routes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
  }

  cancelEdit();
  loadRoutes();
}

async function deleteRoute(id) {
  if (!confirm('确定删除这条路线？')) return;
  await fetch('/api/routes/' + id, { method: 'DELETE' });
  closePanel();
  routeLayer.clearLayers();
  loadRoutes();
}
