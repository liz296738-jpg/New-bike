require('dotenv').config({ path: require('path').join(__dirname, '.env') });
const express = require('express');
const session = require('express-session');
const bcrypt = require('bcryptjs');
const path = require('path');
const { initDB, queryAll, queryOne, execute } = require('./database/init');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(express.json({ limit: '10mb' }));
app.use(express.static(path.join(__dirname, 'public')));
app.use(session({
  secret: process.env.SESSION_SECRET || 'cycling-planner-secret-change-me',
  resave: false,
  saveUninitialized: false,
  cookie: { maxAge: 7 * 24 * 60 * 60 * 1000 }
}));

function requireAuth(req, res, next) {
  if (!req.session.userId) return res.status(401).json({ error: '请先登录' });
  next();
}

// ── Auth routes ──

app.post('/api/register', async (req, res) => {
  const { username, password } = req.body;
  if (!username || !password) return res.status(400).json({ error: '用户名和密码不能为空' });
  if (password.length < 4) return res.status(400).json({ error: '密码至少4位' });

  const existing = await queryOne('SELECT id FROM users WHERE username = ?', [username]);
  if (existing) {
    return res.status(400).json({ error: '用户名已存在' });
  }

  const hash = bcrypt.hashSync(password, 10);
  const result = await execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', [username, hash]);
  const userId = Number(result.lastInsertRowid);

  req.session.userId = userId;
  req.session.username = username;
  req.session.save();
  res.json({ id: userId, username });
});

app.post('/api/login', async (req, res) => {
  const { username, password } = req.body;
  if (!username || !password) return res.status(400).json({ error: '用户名和密码不能为空' });

  const user = await queryOne('SELECT id, password_hash FROM users WHERE username = ?', [username]);
  if (!user) {
    return res.status(401).json({ error: '用户名或密码错误' });
  }

  if (!bcrypt.compareSync(password, user.password_hash)) {
    return res.status(401).json({ error: '用户名或密码错误' });
  }

  req.session.userId = user.id;
  req.session.username = username;
  res.json({ id: user.id, username });
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

app.get('/api/routes', requireAuth, async (req, res) => {
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
  res.json(await queryAll(sql, params));
});

app.get('/api/routes/:id', requireAuth, async (req, res) => {
  const route = await queryOne(`
    SELECT r.*, u.username as creator_name
    FROM routes r JOIN users u ON r.creator_id = u.id
    WHERE r.id = ?
  `, [req.params.id]);
  if (!route) return res.status(404).json({ error: '路线不存在' });

  const points = await queryAll('SELECT lat, lng, "order" FROM route_points WHERE route_id = ? ORDER BY "order"', [req.params.id]);
  const comments = await queryAll(`
    SELECT c.*, u.username as author_name
    FROM comments c JOIN users u ON c.user_id = u.id
    WHERE c.route_id = ? ORDER BY c.created_at
  `, [req.params.id]);

  res.json({ ...route, points, comments });
});

app.post('/api/routes', requireAuth, async (req, res) => {
  const { name, difficulty, duration, notes, points } = req.body;
  if (!name || !points || points.length < 2) {
    return res.status(400).json({ error: '路线名称和至少2个点位必填' });
  }

  const result = await execute(
    'INSERT INTO routes (name, creator_id, difficulty, duration, notes) VALUES (?, ?, ?, ?, ?)',
    [name, req.session.userId, difficulty || 'medium', duration || '', notes || '']);
  const routeId = Number(result.lastInsertRowid);

  const stmts = points.map((p, i) => ({
    sql: 'INSERT INTO route_points (route_id, lat, lng, "order") VALUES (?, ?, ?, ?)',
    args: [routeId, p.lat, p.lng, i]
  }));
  await execute(`INSERT INTO route_points (route_id, lat, lng, "order") VALUES ${points.map((_, i) => `(?, ?, ?, ?)`).join(', ')}`,
    points.flatMap((p, i) => [routeId, p.lat, p.lng, i]));

  const route = await queryOne(
    'SELECT r.*, u.username as creator_name FROM routes r JOIN users u ON r.creator_id = u.id WHERE r.id = ?',
    [routeId]);
  route.points = points;
  res.json(route);
});

app.put('/api/routes/:id', requireAuth, async (req, res) => {
  const route = await queryOne('SELECT * FROM routes WHERE id = ?', [req.params.id]);
  if (!route) return res.status(404).json({ error: '路线不存在' });
  if (route.creator_id !== req.session.userId) return res.status(403).json({ error: '只能编辑自己的路线' });

  const { name, difficulty, duration, notes, points } = req.body;
  await execute('UPDATE routes SET name=?, difficulty=?, duration=?, notes=? WHERE id=?',
    [name, difficulty, duration, notes, req.params.id]);

  if (points && points.length >= 2) {
    await execute('DELETE FROM route_points WHERE route_id = ?', [req.params.id]);
    await execute(
      `INSERT INTO route_points (route_id, lat, lng, "order") VALUES ${points.map((_, i) => `(?, ?, ?, ?)`).join(', ')}`,
      points.flatMap((p, i) => [req.params.id, p.lat, p.lng, i]));
  }
  res.json({ ok: true });
});

app.delete('/api/routes/:id', requireAuth, async (req, res) => {
  const route = await queryOne('SELECT * FROM routes WHERE id = ?', [req.params.id]);
  if (!route) return res.status(404).json({ error: '路线不存在' });
  if (route.creator_id !== req.session.userId) return res.status(403).json({ error: '只能删除自己的路线' });

  await execute('DELETE FROM route_points WHERE route_id = ?', [req.params.id]);
  await execute('DELETE FROM comments WHERE route_id = ?', [req.params.id]);
  await execute('DELETE FROM routes WHERE id = ?', [req.params.id]);
  res.json({ ok: true });
});

// ── Comments ──

app.post('/api/routes/:id/comments', requireAuth, async (req, res) => {
  const { content } = req.body;
  if (!content) return res.status(400).json({ error: '评论内容不能为空' });

  const route = await queryOne('SELECT * FROM routes WHERE id = ?', [req.params.id]);
  if (!route) return res.status(404).json({ error: '路线不存在' });

  const result = await execute(
    'INSERT INTO comments (route_id, user_id, content) VALUES (?, ?, ?)',
    [req.params.id, req.session.userId, content]);

  const comment = await queryOne(`
    SELECT c.*, u.username as author_name
    FROM comments c JOIN users u ON c.user_id = u.id
    WHERE c.id = ?
  `, [Number(result.lastInsertRowid)]);
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
