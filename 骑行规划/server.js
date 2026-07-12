const express = require('express');
const session = require('express-session');
const bcrypt = require('bcryptjs');
const path = require('path');
const { initDB, getDB, saveDB } = require('./database/init');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));
app.use(session({
  secret: 'cycling-planner-secret-' + Date.now(),
  resave: false,
  saveUninitialized: false,
  cookie: { maxAge: 7 * 24 * 60 * 60 * 1000 }
}));

function requireAuth(req, res, next) {
  if (!req.session.userId) return res.status(401).json({ error: '请先登录' });
  next();
}

function parseRow(row) { return row; }

// ── Auth routes ──

app.post('/api/register', (req, res) => {
  const { username, password } = req.body;
  if (!username || !password) return res.status(400).json({ error: '用户名和密码不能为空' });
  if (password.length < 4) return res.status(400).json({ error: '密码至少4位' });

  const db = getDB();
  const existing = db.exec('SELECT id FROM users WHERE username = ?', [username]);
  if (existing.length && existing[0].values.length) {
    return res.status(400).json({ error: '用户名已存在' });
  }

  const hash = bcrypt.hashSync(password, 10);
  db.run('INSERT INTO users (username, password_hash) VALUES (?, ?)', [username, hash]);
  saveDB();

  const result = db.exec('SELECT last_insert_rowid() as id');
  const id = result[0].values[0][0];
  req.session.userId = id;
  req.session.username = username;
  res.json({ id, username });
});

app.post('/api/login', (req, res) => {
  const { username, password } = req.body;
  if (!username || !password) return res.status(400).json({ error: '用户名和密码不能为空' });

  const db = getDB();
  const result = db.exec('SELECT id, password_hash FROM users WHERE username = ?', [username]);
  if (!result.length || !result[0].values.length) {
    return res.status(401).json({ error: '用户名或密码错误' });
  }

  const [id, hash] = result[0].values[0];
  if (!bcrypt.compareSync(password, hash)) {
    return res.status(401).json({ error: '用户名或密码错误' });
  }

  req.session.userId = id;
  req.session.username = username;
  res.json({ id, username });
});

app.post('/api/logout', (req, res) => {
  req.session.destroy();
  res.json({ ok: true });
});

app.get('/api/me', (req, res) => {
  if (!req.session.userId) return res.json(null);
  res.json({ id: req.session.userId, username: req.session.username });
});

// ── Route CRUD ──

function queryAll(sql, params = []) {
  const db = getDB();
  try {
    const stmt = db.prepare(sql);
    stmt.bind(params);
    const rows = [];
    while (stmt.step()) rows.push(stmt.getAsObject());
    stmt.free();
    return rows;
  } catch (e) { console.error('queryAll error:', e.message, sql); return []; }
}

function queryOne(sql, params = []) {
  const rows = queryAll(sql, params);
  return rows.length > 0 ? rows[0] : null;
}

app.get('/api/routes', requireAuth, (req, res) => {
  const search = req.query.search || '';
  let sql = `
    SELECT r.*, u.username as creator_name
    FROM routes r JOIN users u ON r.creator_id = u.id
  `;
  let params = [];
  if (search) {
    sql += ' WHERE r.name LIKE ? OR u.username LIKE ?';
    params = ['%' + search + '%', '%' + search + '%'];
  }
  sql += ' ORDER BY r.created_at DESC';
  res.json(queryAll(sql, params));
});

app.get('/api/routes/:id', requireAuth, (req, res) => {
  const route = queryOne(`
    SELECT r.*, u.username as creator_name
    FROM routes r JOIN users u ON r.creator_id = u.id
    WHERE r.id = ?
  `, [req.params.id]);
  if (!route) return res.status(404).json({ error: '路线不存在' });

  const points = queryAll('SELECT lat, lng, "order" FROM route_points WHERE route_id = ? ORDER BY "order"', [req.params.id]);
  const comments = queryAll(`
    SELECT c.*, u.username as author_name
    FROM comments c JOIN users u ON c.user_id = u.id
    WHERE c.route_id = ? ORDER BY c.created_at
  `, [req.params.id]);

  res.json({ ...route, points, comments });
});

app.post('/api/routes', requireAuth, (req, res) => {
  const { name, difficulty, duration, notes, points } = req.body;
  if (!name || !points || points.length < 2) {
    return res.status(400).json({ error: '路线名称和至少2个点位必填' });
  }

  const db = getDB();
  db.run('INSERT INTO routes (name, creator_id, difficulty, duration, notes) VALUES (?, ?, ?, ?, ?)',
    [name, req.session.userId, difficulty || 'medium', duration || '', notes || '']);
  const routeId = db.exec('SELECT last_insert_rowid() as id')[0].values[0][0];

  const stmt = db.prepare('INSERT INTO route_points (route_id, lat, lng, "order") VALUES (?, ?, ?, ?)');
  points.forEach((p, i) => { stmt.bind([routeId, p.lat, p.lng, i]); stmt.step(); stmt.reset(); });
  stmt.free();
  saveDB();

  const route = queryOne('SELECT r.*, u.username as creator_name FROM routes r JOIN users u ON r.creator_id = u.id WHERE r.id = ?', [routeId]);
  route.points = points;
  res.json(route);
});

app.put('/api/routes/:id', requireAuth, (req, res) => {
  const route = queryOne('SELECT * FROM routes WHERE id = ?', [req.params.id]);
  if (!route) return res.status(404).json({ error: '路线不存在' });
  if (route.creator_id !== req.session.userId) return res.status(403).json({ error: '只能编辑自己的路线' });

  const { name, difficulty, duration, notes, points } = req.body;
  const db = getDB();
  db.run('UPDATE routes SET name=?, difficulty=?, duration=?, notes=? WHERE id=?',
    [name, difficulty, duration, notes, req.params.id]);

  if (points && points.length >= 2) {
    db.run('DELETE FROM route_points WHERE route_id = ?', [req.params.id]);
    const stmt = db.prepare('INSERT INTO route_points (route_id, lat, lng, "order") VALUES (?, ?, ?, ?)');
    points.forEach((p, i) => { stmt.bind([req.params.id, p.lat, p.lng, i]); stmt.step(); stmt.reset(); });
    stmt.free();
  }
  saveDB();
  res.json({ ok: true });
});

app.delete('/api/routes/:id', requireAuth, (req, res) => {
  const route = queryOne('SELECT * FROM routes WHERE id = ?', [req.params.id]);
  if (!route) return res.status(404).json({ error: '路线不存在' });
  if (route.creator_id !== req.session.userId) return res.status(403).json({ error: '只能删除自己的路线' });

  const db = getDB();
  db.run('DELETE FROM route_points WHERE route_id = ?', [req.params.id]);
  db.run('DELETE FROM comments WHERE route_id = ?', [req.params.id]);
  db.run('DELETE FROM routes WHERE id = ?', [req.params.id]);
  saveDB();
  res.json({ ok: true });
});

// ── Comments ──

app.post('/api/routes/:id/comments', requireAuth, (req, res) => {
  const { content } = req.body;
  if (!content) return res.status(400).json({ error: '评论内容不能为空' });

  const route = queryOne('SELECT * FROM routes WHERE id = ?', [req.params.id]);
  if (!route) return res.status(404).json({ error: '路线不存在' });

  const db = getDB();
  db.run('INSERT INTO comments (route_id, user_id, content) VALUES (?, ?, ?)',
    [req.params.id, req.session.userId, content]);
  saveDB();

  const commentId = db.exec('SELECT last_insert_rowid() as id')[0].values[0][0];
  const comment = queryOne(`
    SELECT c.*, u.username as author_name
    FROM comments c JOIN users u ON c.user_id = u.id
    WHERE c.id = ?
  `, [commentId]);
  res.json(comment);
});

// SPA fallback
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// ── Start ──
initDB().then(() => {
  app.listen(PORT, () => {
    console.log(`骑行规划平台已启动: http://localhost:${PORT}`);
  });
});
