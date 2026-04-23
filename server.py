"""
会员周期管理系统 - Flask + SQLite
端口：5052
"""
import sqlite3
import os
from functools import wraps
from flask import Flask, request, jsonify, send_file, make_response, render_template_string

app = Flask(__name__, static_folder='.', static_url_path='')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'member.db')


def make_cors_json(data, status=200):
    resp = make_response(jsonify(data), status)
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return resp


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                level TEXT DEFAULT "普通",
                video_streams INTEGER DEFAULT 0,
                create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                update_time DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS recharge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id INTEGER NOT NULL,
                recharge_amount REAL NOT NULL DEFAULT 0,
                recharge_months INTEGER NOT NULL DEFAULT 0,
                gift_months INTEGER DEFAULT 0,
                gift_days INTEGER DEFAULT 0,
                video_streams INTEGER DEFAULT 0,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                remark TEXT DEFAULT "",
                recharge_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (member_id) REFERENCES members(id)
            );
            
            CREATE TABLE IF NOT EXISTS admin (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS query_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_username TEXT,
                ip TEXT,
                status TEXT,
                remaining_days TEXT,
                message TEXT,
                log_time DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        db.commit()
    print(f"[OK] DB initialized: {DB_PATH}")


def log_query(username, ip, status, remaining_days='', message=''):
    with get_db() as db:
        db.execute(
            'INSERT INTO query_log (query_username, ip, status, remaining_days, message) VALUES (?, ?, ?, ?, ?)',
            (username, ip, status, remaining_days, message)
        )
        db.commit()


def get_real_ip():
    if request.headers.get('X-Forwarded-For'):
        ip = request.headers.get('X-Forwarded-For').split(',')[0]
    elif request.headers.get('X-Real-IP'):
        ip = request.headers.get('X-Real-IP')
    else:
        ip = request.remote_addr or '未知IP'
    return ip.strip()


def calc_remaining_days(end_date):
    from datetime import datetime
    today = datetime.now().strftime('%Y-%m-%d')
    today_ts = datetime.strptime(today, '%Y-%m-%d').timestamp()
    end_ts = datetime.strptime(end_date, '%Y-%m-%d').timestamp()
    diff = int((end_ts - today_ts) / 86400)
    return diff


def get_latest_end_date(member_id):
    with get_db() as db:
        row = db.execute(
            'SELECT end_date FROM recharge WHERE member_id=? ORDER BY end_date DESC LIMIT 1',
            (member_id,)
        ).fetchone()
        return row['end_date'] if row else None


def get_member_status(member):
    if member['level'] == '钻石会员':
        return {'text': '永久有效', 'class': 'forever'}
    end_date = get_latest_end_date(member['id'])
    if not end_date:
        return {'text': '无记录', 'class': 'no-record'}
    diff = calc_remaining_days(end_date)
    if diff > 7:
        return {'text': f'剩余{diff}天', 'class': 'normal'}
    elif diff > 0:
        return {'text': f'剩余{diff}天', 'class': 'warning'}
    elif diff == 0:
        return {'text': '今日到期', 'class': 'expire-today'}
    else:
        return {'text': f'已到期({abs(diff)}天)', 'class': 'expired'}


# ==================== API 接口 ====================

@app.route('/api/members', methods=['GET', 'OPTIONS'])
def list_members():
    if request.method == 'OPTIONS':
        return make_cors_json({'ok': True})
    with get_db() as db:
        # 查询会员及其最新到期日，按到期日升序排列（最优先到期的排前面）
        rows = db.execute('''
            SELECT m.*, 
                (SELECT r.end_date FROM recharge r WHERE r.member_id = m.id ORDER BY r.end_date DESC LIMIT 1) as end_date,
                (SELECT r.end_date FROM recharge r WHERE r.member_id = m.id ORDER BY r.end_date DESC LIMIT 1) as latest_end_date
            FROM members m
            ORDER BY 
                CASE WHEN m.level = '钻石会员' THEN 1 ELSE 0 END ASC,
                CASE WHEN (SELECT r.end_date FROM recharge r WHERE r.member_id = m.id ORDER BY r.end_date DESC LIMIT 1) IS NULL THEN 1 ELSE 0 END ASC,
                (SELECT r.end_date FROM recharge r WHERE r.member_id = m.id ORDER BY r.end_date DESC LIMIT 1) ASC
        ''').fetchall()
    return make_cors_json([dict(r) for r in rows])


@app.route('/api/members', methods=['POST', 'OPTIONS'])
def add_member():
    if request.method == 'OPTIONS':
        return make_cors_json({'ok': True})
    data = request.json
    if not data.get('username'):
        return make_cors_json({'error': '用户名不能为空'}, 400)
    try:
        with get_db() as db:
            cur = db.execute(
                'INSERT INTO members (username, level, video_streams) VALUES (?, ?, ?)',
                (data['username'], data.get('level', '普通'), data.get('video_streams', 0))
            )
            db.commit()
        return make_cors_json({'id': cur.lastrowid}, 201)
    except sqlite3.IntegrityError:
        return make_cors_json({'error': '用户名已存在'}, 400)


@app.route('/api/members/<int:member_id>', methods=['PUT', 'OPTIONS'])
def update_member(member_id):
    if request.method == 'OPTIONS':
        return make_cors_json({'ok': True})
    data = request.json
    with get_db() as db:
        db.execute(
            'UPDATE members SET username=?, level=?, video_streams=?, update_time=CURRENT_TIMESTAMP WHERE id=?',
            (data.get('username'), data.get('level'), data.get('video_streams', 0), member_id)
        )
        db.commit()
    return make_cors_json({'ok': True})


@app.route('/api/members/<int:member_id>', methods=['DELETE', 'OPTIONS'])
def delete_member(member_id):
    if request.method == 'OPTIONS':
        return make_cors_json({'ok': True})
    with get_db() as db:
        db.execute('DELETE FROM recharge WHERE member_id=?', (member_id,))
        db.execute('DELETE FROM members WHERE id=?', (member_id,))
        db.commit()
    return make_cors_json({'ok': True})


@app.route('/api/members/<int:member_id>/recharges', methods=['GET', 'OPTIONS'])
def list_recharges(member_id):
    if request.method == 'OPTIONS':
        return make_cors_json({'ok': True})
    with get_db() as db:
        rows = db.execute(
            'SELECT * FROM recharge WHERE member_id=? ORDER BY recharge_time DESC',
            (member_id,)
        ).fetchall()
    return make_cors_json([dict(r) for r in rows])


@app.route('/api/recharges/<int:recharge_id>', methods=['DELETE', 'OPTIONS'])
def delete_recharge(recharge_id):
    if request.method == 'OPTIONS':
        return make_cors_json({'ok': True})
    with get_db() as db:
        db.execute('DELETE FROM recharge WHERE id=?', (recharge_id,))
        db.commit()
    return make_cors_json({'ok': True})


@app.route('/api/members/<int:member_id>/recharge', methods=['POST', 'OPTIONS'])
def add_recharge(member_id):
    if request.method == 'OPTIONS':
        return make_cors_json({'ok': True})
    data = request.json
    required = ['start_date', 'end_date']
    if not all(k in data for k in required):
        return make_cors_json({'error': '缺少必填字段'}, 400)
    
    # 计算结束日期（基于开始日期 + 月份）
    from datetime import datetime, timedelta
    start = datetime.strptime(data['start_date'], '%Y-%m-%d')
    
    total_months = int(data.get('recharge_months', 0)) + int(data.get('gift_months', 0))
    total_days = int(data.get('gift_days', 0))
    
    if total_months > 0:
        # 按月计算
        year = start.year + (start.month - 1 + total_months) // 12
        month = (start.month - 1 + total_months) % 12 + 1
        day = min(start.day, [31,28,31,30,31,30,31,31,30,31,30,31][month-1])
        end = datetime(year, month, day)
    elif total_days > 0:
        end = start + timedelta(days=total_days)
    else:
        end = start
    
    end_date_str = data['end_date'] if not (total_months > 0 or total_days > 0) else end.strftime('%Y-%m-%d')
    
    with get_db() as db:
        # 更新视频流数
        if data.get('video_streams'):
            db.execute('UPDATE members SET video_streams=? WHERE id=?', 
                      (data['video_streams'], member_id))
        
        cur = db.execute('''
            INSERT INTO recharge (member_id, recharge_amount, recharge_months, gift_months, gift_days, video_streams, start_date, end_date, remark)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            member_id,
            data.get('recharge_amount', 0),
            data.get('recharge_months', 0),
            data.get('gift_months', 0),
            data.get('gift_days', 0),
            data.get('video_streams', 0),
            data['start_date'],
            end_date_str,
            data.get('remark', '')
        ))
        db.commit()
    return make_cors_json({'id': cur.lastrowid}, 201)


@app.route('/api/query', methods=['POST', 'OPTIONS'])
def query_member():
    if request.method == 'OPTIONS':
        return make_cors_json({'ok': True})
    data = request.json or {}
    username = data.get('username', '').strip()
    user_ip = get_real_ip()
    
    if not username:
        log_query(username, user_ip, '失败', '', '输入的用户名为空')
        return make_cors_json({'error': '请输入用户名！'}, 400)
    
    with get_db() as db:
        member = db.execute('SELECT * FROM members WHERE username=?', (username,)).fetchone()
        
        if not member:
            log_query(username, user_ip, '失败', '', '未找到该会员信息')
            return make_cors_json({'error': '未找到该会员信息！'}, 404)
        
        recharges = db.execute(
            'SELECT * FROM recharge WHERE member_id=? ORDER BY recharge_time DESC',
            (member['id'],)
        ).fetchall()
        
        total_recharge = sum(r['recharge_amount'] for r in recharges)
        total_gift_months = sum(r['gift_months'] for r in recharges)
        total_gift_days = sum(r['gift_days'] for r in recharges)
        latest_end_date = get_latest_end_date(member['id'])
        
        status = get_member_status(member)
        
        log_query(username, user_ip, '成功', status['text'], f'查询到会员信息，等级：{member["level"]}')
        
        return make_cors_json({
            'member': dict(member),
            'recharges': [dict(r) for r in recharges],
            'total_recharge': round(total_recharge, 2),
            'total_gift_months': total_gift_months,
            'total_gift_days': total_gift_days,
            'latest_end_date': latest_end_date,
            'status': status
        })


@app.route('/api/warnings', methods=['GET', 'OPTIONS'])
def get_warnings():
    if request.method == 'OPTIONS':
        return make_cors_json({'ok': True})
    from datetime import datetime, timedelta
    today = datetime.now().strftime('%Y-%m-%d')
    warning_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
    
    with get_db() as db:
        rows = db.execute('''
            SELECT m.username, m.level, m.video_streams, r.end_date,
            (julianday(r.end_date) - julianday(?)) as remaining_days
            FROM members m
            JOIN recharge r ON m.id = r.member_id
            WHERE r.end_date BETWEEN ? AND ?
            AND m.level != '钻石会员'
            ORDER BY remaining_days ASC
        ''', (today, today, warning_date)).fetchall()
    
    return make_cors_json([dict(r) for r in rows])


@app.route('/api/admin/login', methods=['POST', 'OPTIONS'])
def admin_login():
    if request.method == 'OPTIONS':
        return make_cors_json({'ok': True})
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        return make_cors_json({'error': '账号密码不能为空'}, 400)
    
    with get_db() as db:
        admin = db.execute('SELECT * FROM admin WHERE username=?', (username,)).fetchone()
        if not admin:
            return make_cors_json({'error': '账号或密码错误'}, 401)
        
        # 简单密码验证（生产环境应使用 bcrypt）
        if admin['password'] != password:
            return make_cors_json({'error': '账号或密码错误'}, 401)
        
    return make_cors_json({'ok': True, 'username': username})


@app.route('/api/admin/init', methods=['POST', 'OPTIONS'])
def admin_init():
    if request.method == 'OPTIONS':
        return make_cors_json({'ok': True})
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        return make_cors_json({'error': '账号密码不能为空'}, 400)
    
    with get_db() as db:
        exists = db.execute('SELECT COUNT(*) FROM admin WHERE username=?', (username,)).fetchone()[0]
        if exists > 0:
            return make_cors_json({'error': '管理员账号已存在'}, 400)
        
        db.execute('INSERT INTO admin (username, password) VALUES (?, ?)', (username, password))
        db.commit()
    
    return make_cors_json({'ok': True})


@app.route('/api/admin/check', methods=['GET', 'OPTIONS'])
def admin_check():
    if request.method == 'OPTIONS':
        return make_cors_json({'ok': True})
    with get_db() as db:
        admins = db.execute('SELECT COUNT(*) FROM admin').fetchone()[0]
    return make_cors_json({'exists': admins > 0})


@app.route('/api/stats', methods=['GET', 'OPTIONS'])
def get_stats():
    """获取收入和会员数统计"""
    if request.method == 'OPTIONS':
        return make_cors_json({'ok': True})
    with get_db() as db:
        # 会员总数
        total_members = db.execute('SELECT COUNT(*) FROM members').fetchone()[0]
        
        # 各等级会员数
        level_stats = db.execute('''
            SELECT level, COUNT(*) as count FROM members GROUP BY level
        ''').fetchall()
        
        # 总收入（充值金额总和）
        total_revenue = db.execute('SELECT COALESCE(SUM(recharge_amount), 0) FROM recharge').fetchone()[0]
        
        # 本月收入
        from datetime import datetime
        first_day_of_month = datetime.now().strftime('%Y-%m') + '-01'
        monthly_revenue = db.execute(
            'SELECT COALESCE(SUM(recharge_amount), 0) FROM recharge WHERE recharge_time >= ?',
            (first_day_of_month,)
        ).fetchone()[0]
        
        # 总充值记录数
        total_recharges = db.execute('SELECT COUNT(*) FROM recharge').fetchone()[0]
        
        # 即将到期人数（30天内）
        from datetime import datetime as dt, timedelta as td
        today = dt.now().strftime('%Y-%m-%d')
        warning_date = (dt.now() + td(days=30)).strftime('%Y-%m-%d')
        expiring_soon = db.execute('''
            SELECT COUNT(DISTINCT member_id) FROM recharge 
            WHERE end_date BETWEEN ? AND ? AND member_id NOT IN (
                SELECT m.id FROM members m WHERE m.level = '钻石会员'
            )
        ''', (today, warning_date)).fetchone()[0]
        
    return make_cors_json({
        'total_members': total_members,
        'level_stats': [dict(r) for r in level_stats],
        'total_revenue': round(total_revenue, 2),
        'monthly_revenue': round(monthly_revenue, 2),
        'total_recharges': total_recharges,
        'expiring_soon': expiring_soon
    })


@app.route('/api/export', methods=['GET', 'OPTIONS'])
def export_data():
    """导出所有会员数据和充值记录"""
    if request.method == 'OPTIONS':
        return make_cors_json({'ok': True})
    
    with get_db() as db:
        members = db.execute('SELECT * FROM members ORDER BY id').fetchall()
        recharges = db.execute('SELECT * FROM recharge ORDER BY recharge_time DESC').fetchall()
    
    data = {
        'export_time': str(sqlite3.connect(DB_PATH).execute("SELECT datetime('now', 'localtime')").fetchone()[0]),
        'version': '1.0',
        'members': [dict(m) for m in members],
        'recharges': [dict(r) for r in recharges]
    }
    
    return make_cors_json(data)


@app.route('/api/import', methods=['POST', 'OPTIONS'])
def import_data():
    """批量导入会员数据（支持追加和覆盖）"""
    if request.method == 'OPTIONS':
        return make_cors_json({'ok': True})
    
    data = request.json
    if not data or 'members' not in data:
        return make_cors_json({'error': '无效的导入数据'}, 400)
    
    members = data.get('members', [])
    recharges = data.get('recharges', [])
    overwrite = data.get('overwrite', False)
    
    imported_members = 0
    imported_recharges = 0
    
    with get_db() as db:
        if overwrite:
            db.execute('DELETE FROM recharge')
            db.execute('DELETE FROM members')
            db.commit()
        
        # 导入会员
        for m in members:
            if not m.get('username'):
                continue
            try:
                db.execute('''
                    INSERT INTO members (username, level, video_streams, create_time, update_time)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    m['username'],
                    m.get('level', '普通'),
                    m.get('video_streams', 0),
                    m.get('create_time', ''),
                    m.get('update_time', '')
                ))
                imported_members += 1
            except sqlite3.IntegrityError:
                continue
        
        # 导入充值记录
        for r in recharges:
            if not r.get('member_id') or not r.get('start_date') or not r.get('end_date'):
                continue
            try:
                db.execute('''
                    INSERT INTO recharge (member_id, recharge_amount, recharge_months, gift_months, gift_days, video_streams, start_date, end_date, remark, recharge_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    r['member_id'],
                    r.get('recharge_amount', 0),
                    r.get('recharge_months', 0),
                    r.get('gift_months', 0),
                    r.get('gift_days', 0),
                    r.get('video_streams', 0),
                    r['start_date'],
                    r['end_date'],
                    r.get('remark', ''),
                    r.get('recharge_time', '')
                ))
                imported_recharges += 1
            except Exception:
                continue
        
        db.commit()
    
    return make_cors_json({
        'ok': True,
        'imported_members': imported_members,
        'imported_recharges': imported_recharges
    })


# ==================== 前台页面 ====================

@app.route('/')
def index():
    return send_file(os.path.join(BASE_DIR, 'public', 'index.html'))


@app.route('/admin')
def admin():
    return send_file(os.path.join(BASE_DIR, 'public', 'admin.html'))


@app.route('/init')
def init_page():
    return send_file(os.path.join(BASE_DIR, 'public', 'init.html'))


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5052, debug=False, threaded=True)