import sqlite3
import hashlib
import sqlite3
import uuid
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from flask_socketio import SocketIO, send, emit, join_room, leave_room
from werkzeug.utils import secure_filename
import os
from werkzeug.security import generate_password_hash, check_password_hash
app = Flask(__name__)



socketio = SocketIO(app)
app.config['SECRET_KEY'] = 'secret!'
# 데이터베이스 파일 경로
DATABASE = 'market.db'

# 업로드 파일 경로 설정
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 파일 확장자 확인 함수
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# DB 연결 함수
def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row  # 결과를 dict처럼 사용
    return db

# 테이블 생성
def init_db():
    db = get_db()
    with open('Data.sql', 'r',encoding="UTF-8") as f:  # SQL 스크립트 파일을 읽어서 실행
        db.executescript(f.read())
    db.commit()

# main 실행
@app.route('/')
def index():
    db = get_db()
    cursor = db.cursor()
    # 등록된 상품 목록 조회
    cursor.execute("SELECT * FROM items")
    items = cursor.fetchall()
    return render_template("index.html", items=items)


@socketio.on("private_message")
def handle_private_message(data):
    sender_id = data["sender_id"]
    receiver_id = data["receiver_id"]
    message = data["message"]

    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO private_messages (sender_id, receiver_id, message)
        VALUES (?, ?, ?)
    """, (sender_id, receiver_id, message))
    db.commit()

    # 양쪽에게 메시지 전송
    emit("receive_private_message", data, broadcast=True)
    
from werkzeug.security import generate_password_hash, check_password_hash

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        cursor = db.cursor()

        # 아이디 중복 체크
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            flash('이미 존재하는 사용자명입니다.')
            return redirect(url_for('register'))

        # 비밀번호 해싱
        hashed_password = generate_password_hash(password)

        # 프로필 사진 처리
        profile_pic_url = None
        if 'profile_pic' in request.files:
            profile_pic = request.files['profile_pic']
            if profile_pic and allowed_file(profile_pic.filename):
                filename = secure_filename(profile_pic.filename)
                profile_pic.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                profile_pic_url = url_for('static', filename='uploads/' + filename)

        # 고유 ID 생성 및 사용자 정보 DB에 저장
        user_id = str(uuid.uuid4())
        cursor.execute("INSERT INTO users (id, username, password, profile_pic) VALUES (?, ?, ?, ?)",
                       (user_id, username, hashed_password, profile_pic_url))
        db.commit()
        flash('회원가입 완료! 로그인 해주세요.')
        return redirect(url_for('login'))
    
    return render_template('register.html')

from time import time

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # 로그인 시도 횟수와 타임아웃 체크
        if 'login_attempts' in session and session['login_attempts'] >= 3:
            if time() - session['last_attempt_time'] < 300:  # 300초 (5분)
                flash('로그인 시도 횟수가 초과되었습니다. 5분 후에 다시 시도해주세요.')
                return redirect(url_for('login'))
            else:
                # 5분이 경과하면 시도 횟수 초기화
                session.pop('login_attempts', None)
                session.pop('last_attempt_time', None)

        db = get_db()
        cursor = db.cursor()

        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()

        if user and check_password_hash(user['password'], password):  # 해시값과 비교
            session['user_id'] = user['username']
            session['log_id'] = user['id']
            session.pop('login_attempts', None)  # 로그인 성공 시 시도 횟수 초기화
            flash('로그인 성공!')
            return redirect(url_for('index'))
        else:
            # 로그인 실패 시 시도 횟수 증가
            if 'login_attempts' in session:
                session['login_attempts'] += 1
            else:
                session['login_attempts'] = 1

            # 로그인 실패 시간 기록
            session['last_attempt_time'] = time()

            flash('아이디나 비밀번호가 잘못되었습니다.')
            return redirect(url_for('login'))

    return render_template('login.html')


# 로그아웃
@app.route('/logout')
def logout():
    session.clear()
    flash('로그아웃 완료!')
    return redirect(url_for('index'))


# 마이페이지
@app.route('/mypage', methods=['GET', 'POST'])
def mypage():
    if 'user_id' not in session:
        flash('로그인이 필요합니다.')
        return redirect(url_for('login'))

    db = get_db()
    cursor = db.cursor()

    if request.method == 'POST':
        new_intro = request.form['intro']
        new_password = request.form['password']
        cursor.execute("UPDATE users SET intro = ?, password = ? WHERE id = ?",
                       (new_intro, new_password, session['user_id']))
        db.commit()
        flash('정보가 업데이트되었습니다.')

    cursor.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],))
    user = cursor.fetchone()
    return render_template('mypage.html', user=user)


# 사용자 프로필 확인
@app.route('/profile/<user_id>', methods=['GET', 'POST'])
def profile(user_id):
    db = get_db()
    cursor = db.cursor()

    # 사용자 정보 가져오기 - user_id로 사용자를 조회
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    print(user)

    if request.method == 'POST':
        # 프로필 사진 처리
        if 'profile_pic' in request.files:
            profile_pic = request.files['profile_pic']
            if profile_pic and allowed_file(profile_pic.filename):
                filename = secure_filename(profile_pic.filename)
                profile_pic.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                profile_pic_url = filename  # 파일 이름만 저장
                # 데이터베이스에서 프로필 사진 업데이트
                cursor.execute("UPDATE users SET profile_pic = ? WHERE id = ?", (profile_pic_url, user_id))
                db.commit()

                flash('프로필 사진이 업데이트되었습니다.')
                return redirect(url_for('profile', user_id=user_id))  # 리다이렉트하여 새로 고침

    if user:
        return render_template('profile.html', user=user)
    else:
        flash("사용자를 찾을 수 없습니다.")
        return redirect(url_for('index'))


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    # 로그인 체크
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        price = request.form['price']
        user_id = session['log_id']

        # 사진 업로드 처리
        if 'photo' in request.files:
            photo = request.files['photo']
            if photo and allowed_file(photo.filename):
                filename = secure_filename(photo.filename)
                photo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                photo_url = url_for('static', filename='uploads/' + filename)
            else:
                photo_url = None
        else:
            photo_url = None

        db = get_db()
        cursor = db.cursor()
        cursor.execute("INSERT INTO items (title, description, price, photo, owner_id) VALUES (?, ?, ?, ?, ?)",
                       (title, description, price, photo_url, user_id))
        db.commit()
        flash('상품이 등록되었습니다.')
        return redirect(url_for('index'))

    return render_template('upload.html')

@app.route('/my_items')
def my_items():
    user_id = session.get('user_id')
    if not user_id:
        flash('로그인이 필요합니다.')
        return redirect(url_for('login'))

    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM items WHERE owner_id = ?", (user_id,))
    items = cursor.fetchall()
    return render_template('my_items.html', items=items)

@app.route('/item/<item_id>')
def item_detail(item_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    db = get_db()
    
    # 상품 정보 조회
    item = db.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    
    # item이 None인 경우 체크
    if item is None:
        flash('존재하지 않는 상품입니다.')
        return redirect(url_for('index'))
    
    # 해당 상품에 대한 신고 수 조회
    report_count = db.execute(
        "SELECT COUNT(DISTINCT reporter_id) FROM product_report WHERE product_id = ? AND status = 'visible'",
        (item_id,)
    ).fetchone()[0]
    
    # 신고 수가 3명 이상인 경우 해당 상품을 숨김 처리
    if report_count >= 3:
        db.execute("UPDATE product_report SET status = 'hidden' WHERE product_id = ?", (item_id,))
        db.commit()
        flash('해당 상품은 신고로 인해 숨김 처리되었습니다.')
        return redirect(url_for('index'))
    
    # 상품의 숨김 상태 확인 (신고로 숨김 처리된 경우)
    hidden_report = db.execute(
        "SELECT * FROM product_report WHERE product_id = ? AND status = 'hidden'",
        (item_id,)
    ).fetchone()
    
    if hidden_report:
        flash('숨김 처리된 상품입니다.')
        return redirect(url_for('index'))
    
    # 상품의 소유자 이름 조회
    owner = db.execute("SELECT username FROM users WHERE id = ?", (item['owner_id'],)).fetchone()
    print(item['owner_id'])
    print(owner)
    # 상품 상세 페이지 렌더링
    return render_template('item_detail.html', item=item, owner_name=owner['username'])

@app.route('/chat')
def chat():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT username, message FROM chat_messages ORDER BY id ASC")
    messages = cursor.fetchall()

    return render_template('chat.html', username=session['user_id'], messages=messages)

@socketio.on('send_message')
def handle_message(data):
    username = session.get('user_id', 'Anonymous')
    message = data['message']
    # DB 저장
    db = get_db()
    cursor = db.cursor()
    cursor.execute("INSERT INTO chat_messages (username, message) VALUES (?, ?)", (username, message))
    db.commit()

    # 모든 사용자에게 메시지 전송
    emit('receive_message', {'username': username, 'message': message}, broadcast=True)

@app.route('/chat_list')
def chat_list():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    db = get_db()
    cursor = db.cursor()

    # 사용자가 참여한 채팅방 리스트 조회
    cursor.execute("""
        SELECT room_id, username 
        FROM user_rooms
        JOIN users ON users.id = user_rooms.user_id
        WHERE user_rooms.user_id = ?
    """, (user_id,))
    rooms = cursor.fetchall()

    return render_template('chat_list.html', rooms=rooms)

@app.route('/report_reason/<user_id>', methods=['GET'])
def report_reason(user_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('report_reason.html', user_id=user_id)

@app.route('/report/<user_id>', methods=['POST'])
def report_user(user_id):
    reporter_id = session.get('log_id')
    reason = request.form.get('reason')
    print(request.form.get('reason'))
    db = get_db()

    # 이미 신고한 적 있는지 확인
    existing = db.execute(
        "SELECT 1 FROM report WHERE reporter_id = ? AND reported_id = ?",
        (reporter_id, user_id)
    ).fetchone()
    if existing:
        flash('이미 이 사용자를 신고하셨습니다.')
        return redirect(url_for('profile', user_id=user_id))

    # 신고 기록 저장
    db.execute("INSERT INTO report (reporter_id, reported_id, reason) VALUES (?, ?, ?)",
               (reporter_id, user_id, reason))
    db.commit()

    # 서로 다른 사용자 수 기준으로 신고 수 계산
    report_count = db.execute(
        "SELECT COUNT(DISTINCT reporter_id) as cnt FROM report WHERE reported_id = ?",
        (user_id,)
    ).fetchone()['cnt']

    if report_count >= 3:
        db.execute("UPDATE users SET status = 'dormant' WHERE id = ?", (user_id,))
        db.commit()
        flash('신고가 누적되어 해당 계정이 휴면 처리되었습니다.')
    else:
        flash('신고가 접수되었습니다.')

    return redirect(url_for('profile', user_id=user_id))


@app.route('/report_product/<int:product_id>', methods=['GET', 'POST'])
def report_product(product_id):
    if 'user_id' not in session:
        flash('로그인이 필요합니다.')
        return redirect(url_for('login'))

    reporter_id = session['log_id']

    if request.method == 'POST':
        reason = request.form.get('reason', '').strip()
        if not reason:
            flash('신고 사유를 입력해주세요.')
            return redirect(url_for('report_product', product_id=product_id))

        db = get_db()

        # 중복 신고 방지
        existing = db.execute(
            "SELECT 1 FROM product_report WHERE reporter_id = ? AND product_id = ?",
            (reporter_id, product_id)
        ).fetchone()
        if existing:
            flash('이미 신고한 상품입니다.')
            return redirect(url_for('item_detail', item_id=product_id))

        db.execute(
            "INSERT INTO product_report (reporter_id, product_id, reason) VALUES (?, ?, ?)",
            (reporter_id, product_id, reason)
        )
        db.commit()

        # 서로 다른 사람 3명 이상 신고했는지 확인
        count = db.execute(
            "SELECT COUNT(DISTINCT reporter_id) as cnt FROM product_report WHERE product_id = ?",
            (product_id,)
        ).fetchone()['cnt']

        if count >= 3:
            db.execute("UPDATE product SET status = 'hidden' WHERE id = ?", (product_id,))
            db.commit()
            flash('신고가 누적되어 해당 게시물이 숨김 처리되었습니다.')
        else:
            flash('상품 신고가 접수되었습니다.')

        return redirect(url_for('item_detail', item_id=product_id))

    return render_template('report_product.html', product_id=product_id)

# # 채팅 방 고유 ID 생성 (sender_id, receiver_id 조합)
# def get_chat_room_id(sender_id, receiver_id):
#     return tuple(sorted([sender_id, receiver_id]))  # sender_id와 receiver_id를 정렬하여 고유한 ID를 생성


# @app.route('/private_chat/<room_id>', methods=['GET', 'POST'])
# def private_chat(room_id):
#     if 'user_id' not in session:
#         return redirect(url_for('login'))

#     db = get_db()
#     cursor = db.cursor()

#     sender_id = session['user_id']
    
#     # 상대방의 ID와 이름을 가져오기 위해 room_id에서 상대방 정보 추출
#     cursor.execute("""
#         SELECT sender_id, receiver_id 
#         FROM private_messages
#         WHERE room_id = ?
#         LIMIT 1
#     """, (room_id,))
#     users = cursor.fetchone()
    
#     if users:
#         receiver_id = users[0] if users[0] != sender_id else users[1]
        
#         cursor.execute("SELECT username FROM users WHERE id = ?", (receiver_id,))
#         user = cursor.fetchone()
#         receiver_name = user['username']
        
#         # 메시지 불러오기
#         cursor.execute("""
#             SELECT * FROM private_messages
#             WHERE room_id = ?
#             ORDER BY timestamp ASC
#         """, (room_id,))
#         messages = cursor.fetchall()

#         return render_template("private_chat.html",
#                                messages=messages,
#                                username=session.get('username'),
#                                receiver_name=receiver_name,
#                                room_id=room_id)
#     else:
#         flash("해당 방에 대한 정보가 없습니다.")
#         return redirect(url_for('index'))

# @socketio.on('join')
# def on_join(room_id):
#     join_room(room_id)
#     print(f'User has entered room {room_id}')

# @socketio.on('message')
# def handle_message(data):
#     room_id = data['room_id']
#     message = data['message']
#     sender_id = data['sender_id']
#     receiver_id = data['receiver_id']

#     # 메시지 저장
#     db = get_db()
#     cursor = db.cursor()
#     cursor.execute("""
#         INSERT INTO private_messages (room_id, sender_id, receiver_id, message, timestamp)
#         VALUES (?, ?, ?, ?, ?)
#     """, (room_id, sender_id, receiver_id, message, datetime.utcnow()))
#     db.commit()
#     cursor.execute("""
#         INSERT OR IGNORE INTO user_rooms (user_id, room_id)
#         VALUES (?, ?), (?, ?)
#     """, (sender_id, room_id, receiver_id, room_id))
#     db.commit()

#     # 메시지 전송
#     send(message, room=room_id)

# @socketio.on('leave')
# def on_leave(room_id):
#     leave_room(room_id)
#     print(f'User has left room {room_id}')

if __name__ == "__main__":
    init_db()
    socketio.run(app, debug=True)
    print("데이터베이스 초기화 완료!")